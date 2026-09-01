"""播放列表/合集解析，只展开条目，不下载媒体。"""
import asyncio
import logging
import re
from urllib.parse import urlparse

import yt_dlp

from backend.utils.video_helpers import BILIBILI_COOKIES_PATH, get_cookies_for_url


ALLOWED_PLAYLIST_HOSTS = {
    "bilibili.com", "www.bilibili.com", "space.bilibili.com", "b23.tv",
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
}
logger = logging.getLogger(__name__)


def _validate_playlist_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅支持 http/https 合集链接")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname not in ALLOWED_PLAYLIST_HOSTS:
        raise ValueError("目前仅支持 Bilibili 和 YouTube 合集")
    return url.strip()


def _entry_url(entry: dict) -> str:
    for key in ("webpage_url", "original_url", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    entry_id = str(entry.get("id") or "")
    if entry_id.startswith("BV"):
        return f"https://www.bilibili.com/video/{entry_id}"
    extractor = str(entry.get("extractor_key") or entry.get("extractor") or "").lower()
    if "youtube" in extractor and re.fullmatch(r"[A-Za-z0-9_-]{11}", entry_id):
        return f"https://www.youtube.com/watch?v={entry_id}"
    return ""


async def resolve_playlist(url: str, limit: int = 100) -> dict:
    url = _validate_playlist_url(url)
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        "playlistend": limit,
    }
    cookies = get_cookies_for_url(url, BILIBILI_COOKIES_PATH, logger)
    if cookies:
        options["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(options) as ydl:
        info = await asyncio.to_thread(ydl.extract_info, url, False)

    raw_entries = list(info.get("entries") or [])[:limit]
    entries = []
    for index, entry in enumerate(raw_entries, start=1):
        if not entry:
            continue
        item_url = _entry_url(entry)
        if not item_url:
            continue
        entries.append({
            "id": str(entry.get("id") or index),
            "title": entry.get("title") or f"第 {index} 集",
            "url": item_url,
            "duration": entry.get("duration") or 0,
            "thumbnail": entry.get("thumbnail") or "",
            "index": index,
        })

    if len(entries) < 2:
        raise ValueError("未识别到包含多个视频的合集")
    return {
        "title": info.get("title") or "未命名合集",
        "uploader": info.get("uploader") or "",
        "entries": entries,
        "total": len(entries),
        "truncated": len(raw_entries) >= limit,
    }
