import asyncio
import html
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit

import requests

from backend.services.search_providers.base import SearchProvider

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
BILIBILI_COOKIES = PROJECT_ROOT / "bilibili_cookies.txt"


class _QuietLogger:
    """Do not expose upstream URLs, cookies or response bodies in logs."""

    def debug(self, _message):
        pass

    info = warning = error = debug


class _SearchFailure(Exception):
    def __init__(self, message: str, code: str = "upstream_error"):
        super().__init__(message)
        self.code = code


class LocalSearchProvider(SearchProvider):
    """Keyword search, not an arbitrary URL extractor or downloader."""

    name = "local"
    SUPPORTED_PLATFORMS = ("youtube", "bilibili")
    MAX_QUERY_LENGTH = 200
    MAX_PAGE = 20
    MAX_RESULTS = 20
    SEARCH_TIMEOUT = 30
    SOCKET_TIMEOUT = 10
    BILIBILI_PAGE_SIZE = 20
    BILIBILI_HEADERS = {
        # An incomplete browser UA can return an error page instead of JSON.
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }

    def __init__(self):
        self._yt_dlp_available = YoutubeDL is not None
        self._bilibili_cookies: Dict[str, str] = {}
        # A timed-out SDK thread retains its slot until it actually finishes.
        self._workers = asyncio.Semaphore(2)

    async def initialize(self) -> bool:
        self._yt_dlp_available = YoutubeDL is not None
        self._bilibili_cookies = self._load_bilibili_cookies()
        logger.info("Local search ready; YouTube SDK available: %s", self._yt_dlp_available)
        return True  # Bilibili's metadata API does not require the SDK executable.

    def is_available(self) -> bool:
        return True

    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        platform = kwargs.get("platform", "bilibili")
        page = kwargs.get("page", 1)
        max_results = kwargs.get("max_results", 10)
        if not isinstance(platform, str) or platform not in self.SUPPORTED_PLATFORMS:
            return self._failure("目前仅支持 YouTube 和 Bilibili 关键词搜索", "unsupported_platform")
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= self.MAX_QUERY_LENGTH:
            return self._failure("搜索关键词长度须为 1–200 个字符", "invalid_query")
        query = query.strip()
        if re.search(r"(?:[a-z][a-z\d+.-]*://|www\.|\b(?:[a-z\d-]+\.)+[a-z]{2,}(?:/|\?))", query, re.I):
            return self._failure("搜索只接受关键词；视频链接请使用视频笔记入口", "invalid_query")
        if any(ord(char) < 32 for char in query):
            return self._failure("搜索关键词不能包含控制字符", "invalid_query")
        if type(page) is not int or not 1 <= page <= self.MAX_PAGE:
            return self._failure("页码须为 1–20 的整数", "invalid_page")
        if type(max_results) is not int or not 1 <= max_results <= self.MAX_RESULTS:
            return self._failure("每页条数须为 1–20 的整数", "invalid_limit")
        if platform == "youtube" and not self._yt_dlp_available:
            return self._failure("YouTube 搜索依赖 yt-dlp，请先安装项目依赖", "dependency_unavailable")

        function = self._search_bilibili if platform == "bilibili" else self._search_youtube
        try:
            videos = await self._run_blocking(function, query, page, max_results)
            return {
                "success": True, "results": videos, "count": len(videos),
                "provider": self.name, "platform": platform, "page": page,
            }
        except (asyncio.TimeoutError, requests.Timeout):
            return self._failure("视频搜索超时，请稍后重试", "timeout")
        except _SearchFailure as exc:
            return self._failure(str(exc), exc.code)
        except Exception as exc:
            logger.warning("Video search failed (%s, %s)", platform, type(exc).__name__)
            return self._failure("视频搜索服务暂时不可用，请检查网络后重试", "upstream_error")

    async def _run_blocking(self, function, *args):
        async def run():
            await self._workers.acquire()
            try:
                task = asyncio.create_task(asyncio.to_thread(function, *args))
            except BaseException:
                self._workers.release()
                raise

            def finished(completed):
                self._workers.release()
                if not completed.cancelled():
                    completed.exception()  # Retrieve errors after caller timeout/cancellation.

            task.add_done_callback(finished)
            return await asyncio.shield(task)

        return await asyncio.wait_for(run(), timeout=self.SEARCH_TIMEOUT)

    def _search_youtube(self, query: str, page: int, max_results: int) -> List[Dict[str, Any]]:
        first = (page - 1) * max_results + 1
        last = page * max_results
        options = {
            "extract_flat": True, "skip_download": True, "quiet": True,
            "no_warnings": True, "logger": _QuietLogger(), "cachedir": False,
            "socket_timeout": self.SOCKET_TIMEOUT, "retries": 0, "extractor_retries": 0,
            "playliststart": first, "playlistend": last, "ignoreerrors": False,
            "cookiefile": None, "cookiesfrombrowser": None, "usenetrc": False,
        }
        # The Python API does not load CLI config files. No shell/PATH lookup.
        with YoutubeDL(options) as ydl:
            result = ydl.extract_info(f"ytsearch{last}:{query}", download=False)
            if not isinstance(result, dict) or not isinstance(result.get("entries"), (list, tuple)):
                raise _SearchFailure("YouTube 未返回有效的搜索结果")
            videos = []
            for item in result["entries"][:max_results]:
                if not isinstance(item, dict):
                    continue
                url = item.get("webpage_url") or item.get("url") or ""
                if not self._safe_url(url, {"www.youtube.com", "youtube.com", "youtu.be"}):
                    continue
                title = self._text(item.get("title"))
                if not title:
                    continue
                thumbnail = item.get("thumbnail") or next((
                    entry.get("url") for entry in reversed(item.get("thumbnails") or [])
                    if isinstance(entry, dict) and entry.get("url")
                ), "")
                videos.append(self._video(
                    title, url, thumbnail, "youtube", item.get("description"),
                    self._format_duration(item.get("duration")),
                    item.get("uploader") or item.get("channel"), item.get("view_count"),
                ))
            if result["entries"] and not videos:
                raise _SearchFailure("YouTube 搜索结果格式异常，请更新 yt-dlp 后重试")
            return videos

    def _search_bilibili(self, query: str, page: int, max_results: int) -> List[Dict[str, Any]]:
        # Bilibili may ignore page_size; slice fixed 20-entry upstream pages.
        cookies = self._get_bilibili_search_cookies()
        offset = (page - 1) * max_results
        first_page, skip = divmod(offset, self.BILIBILI_PAGE_SIZE)
        remaining = max_results
        videos = []
        for upstream_page in range(first_page + 1, first_page + 3):
            response = requests.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params={"keyword": query, "search_type": "video", "page": upstream_page,
                        "page_size": self.BILIBILI_PAGE_SIZE},
                headers=self.BILIBILI_HEADERS,
                cookies=cookies or None, timeout=self.SOCKET_TIMEOUT,
            )
            if response.status_code in (401, 403, 412, 429):
                raise _SearchFailure("Bilibili 请求被平台限制，请稍后重试或配置有效 Cookie", "platform_restricted")
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                raise _SearchFailure(
                    "Bilibili 返回了非数据页面，请检查网络或 Cookie 后重试", "invalid_response",
                ) from None
            if not isinstance(data, dict) or data.get("code") != 0:
                code = data.get("code") if isinstance(data, dict) else None
                if code in (-101, -111, -352, -412, -401):
                    raise _SearchFailure("Bilibili 请求被平台限制，请稍后重试或配置有效 Cookie", "platform_restricted")
                raise _SearchFailure("Bilibili 搜索接口暂时不可用")
            payload = data.get("data")
            if not isinstance(payload, dict):
                raise _SearchFailure("Bilibili 未返回有效的搜索结果")
            entries = payload.get("result") or []
            if not isinstance(entries, list):
                raise _SearchFailure("Bilibili 搜索结果格式异常")
            window = entries[skip:skip + remaining]
            previous_count = len(videos)
            for item in window:
                if not isinstance(item, dict):
                    continue
                bvid = item.get("bvid", "")
                if not isinstance(bvid, str) or not re.fullmatch(r"BV[a-zA-Z\d]+", bvid):
                    continue
                title = self._text(item.get("title"))
                if not title:
                    continue
                videos.append(self._video(
                    title, f"https://www.bilibili.com/video/{bvid}", item.get("pic"),
                    "bilibili", item.get("description"), item.get("duration"),
                    item.get("author"), item.get("play"),
                ))
            if window and len(videos) == previous_count:
                raise _SearchFailure("Bilibili 搜索结果格式异常", "invalid_response")
            remaining -= len(window)
            if remaining <= 0 or len(entries) < self.BILIBILI_PAGE_SIZE:
                break
            skip = 0
        return videos

    def _get_bilibili_search_cookies(self) -> Dict[str, str]:
        if self._bilibili_cookies:
            return dict(self._bilibili_cookies)
        # A normal homepage visit establishes Bilibili's public visitor session.
        # Do not load browser cookies or persist visitor identifiers to disk.
        with requests.Session() as session:
            response = session.get(
                "https://www.bilibili.com/", headers=self.BILIBILI_HEADERS, timeout=5,
            )
            if response.status_code in (401, 403, 412, 429):
                raise _SearchFailure("Bilibili 请求被平台限制，请稍后重试或配置有效 Cookie", "platform_restricted")
            response.raise_for_status()
            cookies = {
                cookie.name: cookie.value for cookie in session.cookies
                if cookie.domain.lstrip(".").lower() in ("bilibili.com", "www.bilibili.com", "api.bilibili.com")
            }
        if not cookies:
            raise _SearchFailure("Bilibili 访客会话初始化失败，请稍后重试或配置有效 Cookie", "platform_restricted")
        return cookies

    def _failure(self, message: str, code: str) -> Dict[str, Any]:
        return {"success": False, "error": message, "error_code": code,
                "results": [], "count": 0, "provider": self.name}

    @staticmethod
    def _safe_url(value, hosts=None) -> bool:
        if not isinstance(value, str):
            return False
        try:
            parsed = urlsplit(value)
            return (parsed.scheme in ("https", "http") and bool(parsed.hostname)
                    and not parsed.username and not parsed.password
                    and (hosts is None or parsed.hostname.lower() in hosts))
        except ValueError:
            return False

    @staticmethod
    def _text(value) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", value)).strip() if isinstance(value, str) else ""

    @classmethod
    def _video(cls, title, url, thumbnail, platform, description, duration, author, views):
        thumbnail = "https:" + thumbnail if isinstance(thumbnail, str) and thumbnail.startswith("//") else thumbnail
        thumbnail = thumbnail if cls._safe_url(thumbnail) else ""
        views = views if isinstance(views, (int, float)) and not isinstance(views, bool) and math.isfinite(views) and views >= 0 else 0
        return {"title": title, "url": url, "cover": thumbnail, "thumbnail": thumbnail,
                "description": cls._text(description), "platform": platform,
                "duration": str(duration or ""), "author": cls._text(author),
                "play": views, "views": views}

    @staticmethod
    def _load_bilibili_cookies() -> Dict[str, str]:
        cookies = {}
        if not BILIBILI_COOKIES.exists():
            return cookies
        try:
            with BILIBILI_COOKIES.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line.startswith("#HttpOnly_"):
                        line = line[len("#HttpOnly_"):]
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7 and parts[0].lstrip(".").lower() in ("bilibili.com", "www.bilibili.com", "api.bilibili.com"):
                        cookies[parts[5]] = parts[6]
        except (OSError, UnicodeError) as exc:
            logger.warning("Could not load configured Bilibili cookies (%s)", type(exc).__name__)
        return cookies

    @staticmethod
    def _format_duration(seconds) -> str:
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
            return ""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
