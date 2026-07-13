"""Shared helpers for video cookies and subtitle formatting."""

import logging
from pathlib import Path
from typing import Optional


BILIBILI_COOKIES_PATH = Path(__file__).parent.parent.parent / "bilibili_cookies.txt"


def get_cookies_for_url(
    url: str,
    cookies_path: Path,
    caller_logger: logging.Logger,
) -> Optional[str]:
    """Return the Bilibili cookies path for supported URLs when it exists."""
    if 'bilibili.com' in url or 'b23.tv' in url:
        if cookies_path.exists():
            caller_logger.info(f"使用 B站 cookies: {cookies_path}")
            return str(cookies_path)

    return None


def timestamp_to_seconds(timestamp: str) -> float:
    """Convert HH:MM:SS.mmm, MM:SS.mmm, or seconds to seconds."""
    try:
        parts = timestamp.replace(',', '.').split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        else:
            return float(parts[0])
    except (ValueError, IndexError):
        return 0.0


def merge_and_format_segments(segments: list[tuple[float, float, str]]) -> str:
    """Deduplicate, merge adjacent subtitle segments, and format Markdown."""
    if not segments:
        return ""

    deduped: list[tuple[float, float, str]] = []
    prev_text = ""
    for start, end, text in segments:
        if text != prev_text:
            deduped.append((start, end, text))
            prev_text = text

    if not deduped:
        return ""

    merged: list[tuple[float, float, str]] = []
    current_start = deduped[0][0]
    current_end = deduped[0][1]
    current_texts: list[str] = []
    merge_interval = 30.0

    for start, end, text in deduped:
        if start - current_start > merge_interval and current_texts:
            merged.append((current_start, current_end, " ".join(current_texts)))
            current_start = start
            current_texts = []
        current_end = end
        current_texts.append(text)

    if current_texts:
        merged.append((current_start, current_end, " ".join(current_texts)))

    lines: list[str] = []
    for start, end, text in merged:
        start_fmt = format_time_display(start)
        end_fmt = format_time_display(end)
        lines.append(f"**{start_fmt} - {end_fmt}**  ")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def format_time_display(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
