import logging
import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import requests

from backend.services.search_providers.base import SearchProvider

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
BILIBILI_COOKIES = PROJECT_ROOT / "bilibili_cookies.txt"


class LocalSearchProvider(SearchProvider):

    name = "local"

    def __init__(self):
        self._yt_dlp_available = False
        self._bilibili_cookies: Dict[str, str] = {}

    async def initialize(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            self._yt_dlp_available = proc.returncode == 0
            if self._yt_dlp_available:
                logger.info("LocalSearchProvider initialized — yt-dlp available")
        except FileNotFoundError:
            logger.warning("yt-dlp not found — LocalSearchProvider disabled")
            return False

        self._bilibili_cookies = self._load_bilibili_cookies()
        if self._bilibili_cookies:
            logger.info(f"Bilibili cookies loaded ({len(self._bilibili_cookies)} entries)")

        return self._yt_dlp_available

    def is_available(self) -> bool:
        return self._yt_dlp_available

    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        if not self._yt_dlp_available:
            return {"success": False, "error": "yt-dlp not available", "results": [], "count": 0, "provider": self.name}

        platform = kwargs.pop("platform", "bilibili")

        if platform == "bilibili":
            return await self._search_bilibili(query, **kwargs)
        return await self._search_ytdlp(query, platform, **kwargs)

    async def _search_bilibili(self, query: str, **kwargs) -> Dict[str, Any]:
        page = kwargs.get("page", 1)
        max_results = kwargs.get("max_results", 10)

        try:
            resp = await asyncio.to_thread(
                requests.get,
                "https://api.bilibili.com/x/web-interface/search/type",
                params={"keyword": query, "search_type": "video", "page": page, "page_size": max_results},
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Referer": "https://www.bilibili.com",
                },
                cookies=self._bilibili_cookies if self._bilibili_cookies else None,
                timeout=10,
            )
            data = resp.json()

            if data.get("code") != 0:
                return {"success": False, "error": f"Bilibili API error: {data.get('message', 'unknown')}", "results": [], "count": 0, "provider": self.name}

            videos = []
            for item in data.get("data", {}).get("result", []):
                title = re.sub(r"<[^>]+>", "", item.get("title", ""))
                pic = item.get("pic", "")
                if pic.startswith("//"):
                    pic = "https:" + pic
                videos.append({
                    "title": title,
                    "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
                    "cover": pic,
                    "thumbnail": pic,
                    "description": item.get("description", ""),
                    "platform": "bilibili",
                    "duration": item.get("duration", ""),
                    "author": item.get("author", ""),
                    "play": item.get("play", 0),
                    "views": item.get("play", 0),
                })

            return {"success": True, "results": videos, "count": len(videos), "provider": self.name}

        except Exception as e:
            logger.error(f"Bilibili search failed: {e}")
            return {"success": False, "error": str(e), "results": [], "count": 0, "provider": self.name}

    async def _search_ytdlp(self, query: str, platform: str, **kwargs) -> Dict[str, Any]:
        max_results = kwargs.get("max_results", 10)
        search_prefix = f"ytsearch{max_results}:"

        try:
            cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "--no-warnings", f"{search_prefix}{query}"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            videos = []
            for line in stdout.decode("utf-8", errors="ignore").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    thumbnail = item.get("thumbnail", "")
                    if not thumbnail and item.get("thumbnails"):
                        thumbnail = item["thumbnails"][-1].get("url", "")
                    videos.append({
                        "title": item.get("title", ""),
                        "url": item.get("url") or item.get("webpage_url", ""),
                        "cover": thumbnail,
                        "thumbnail": thumbnail,
                        "description": item.get("description", ""),
                        "platform": platform,
                        "duration": self._format_duration(item.get("duration")),
                        "author": item.get("uploader") or item.get("channel", ""),
                        "play": item.get("view_count", 0),
                        "views": item.get("view_count", 0),
                    })
                except json.JSONDecodeError:
                    continue

            return {"success": True, "results": videos, "count": len(videos), "provider": self.name}

        except asyncio.TimeoutError:
            logger.error("yt-dlp search timed out")
            return {"success": False, "error": "Search timed out", "results": [], "count": 0, "provider": self.name}
        except Exception as e:
            logger.error(f"Local search failed: {e}")
            return {"success": False, "error": str(e), "results": [], "count": 0, "provider": self.name}

    def get_tools(self) -> List[Dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": "video_search",
                "description": "Search for videos on YouTube and Bilibili.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords"},
                        "platform": {
                            "type": "string",
                            "enum": ["youtube", "bilibili"],
                            "description": "Platform to search. Defaults to bilibili.",
                        },
                        "page": {"type": "integer", "description": "Page number for pagination (default 1)"},
                    },
                    "required": ["query"],
                },
            },
        }]

    @staticmethod
    def _load_bilibili_cookies() -> Dict[str, str]:
        cookies = {}
        if not BILIBILI_COOKIES.exists():
            return cookies
        try:
            with open(BILIBILI_COOKIES) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        cookies[parts[5]] = parts[6]
        except Exception as e:
            logger.warning(f"Failed to load bilibili cookies: {e}")
        return cookies

    @staticmethod
    def _format_duration(seconds) -> str:
        if not seconds:
            return ""
        s = int(seconds)
        h, remainder = divmod(s, 3600)
        m, sec = divmod(remainder, 60)
        if h > 0:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"
