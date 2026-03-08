"""
文件处理工具函数
文件名清洗、验证、音频提取、内嵌字幕提取等
"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# 图片字幕 codec，不可提取为文本
_IMAGE_SUBTITLE_CODECS = {"dvd_subtitle", "hdmv_pgs_subtitle", "dvb_subtitle", "xsub"}

# 语言偏好（越靠前越优先）
_LANG_PREFERENCE = ["zh", "chi", "cn", "en", "eng", "ja", "jpn", "ko", "kor"]


async def extract_audio_from_file(file_path: str, output_dir: Path, task_id: str) -> tuple[str, bool]:
    """
    从视频文件提取音频，音频文件直接返回原路径。

    Args:
        file_path: 源媒体文件路径
        output_dir: 临时输出目录
        task_id: 任务 ID（用于命名临时文件）

    Returns:
        (audio_path, needs_cleanup) — needs_cleanup=True 表示 audio_path 是临时文件，调用方用完需删除
    """
    ext = Path(file_path).suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        return file_path, False

    audio_path = str(output_dir / f"{task_id}.wav")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", file_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y",
        audio_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg 提取音频失败: {stderr.decode(errors='replace')[:500]}")

    return audio_path, True


def cleanup_temp_audio(audio_path: str, needs_cleanup: bool) -> None:
    """安全删除临时音频文件"""
    if needs_cleanup and os.path.exists(audio_path):
        try:
            os.remove(audio_path)
        except Exception:
            pass


async def extract_embedded_subtitles(file_path: str) -> Optional[str]:
    """
    从本地视频文件中提取内嵌字幕轨道。

    使用 ffprobe 探测字幕流 → 选择最佳文本字幕 → ffmpeg 提取为 SRT → 解析为 Markdown。

    Args:
        file_path: 本地视频文件路径

    Returns:
        解析后的 Markdown 文本，无可用字幕返回 None
    """
    ext = Path(file_path).suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        return None

    # 1. ffprobe 探测字幕流
    streams = await _probe_subtitle_streams(file_path)
    if not streams:
        logger.info(f"视频无内嵌字幕轨道: {Path(file_path).name}")
        return None

    # 2. 过滤图片字幕，只保留文本字幕
    text_streams = [
        s for s in streams
        if s.get("codec_name", "").lower() not in _IMAGE_SUBTITLE_CODECS
    ]
    if not text_streams:
        logger.info(f"视频仅含图片字幕（不可提取）: {Path(file_path).name}")
        return None

    # 3. 按语言偏好选择最佳字幕
    chosen = _pick_best_stream(text_streams)
    stream_index = chosen["index"]
    lang = chosen.get("tags", {}).get("language", "unknown")
    codec = chosen.get("codec_name", "unknown")
    logger.info(f"选择字幕轨道: index={stream_index}, codec={codec}, lang={lang}")

    # 4. ffmpeg 提取为 SRT
    srt_content = await _extract_stream_as_srt(file_path, stream_index)
    if not srt_content:
        return None

    # 5. 解析 SRT → Markdown
    result = _parse_srt_to_markdown(srt_content)
    if not result or len(result.strip()) < 10:
        logger.warning("提取的字幕内容过短，忽略")
        return None

    logger.info(f"成功提取内嵌字幕: {len(result)} 字符")
    return result


async def _probe_subtitle_streams(file_path: str) -> list[dict]:
    """用 ffprobe 获取视频中的字幕流信息"""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "quiet",
        "-select_streams", "s",
        "-show_streams",
        "-of", "json",
        file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(f"ffprobe 探测字幕失败: {stderr.decode(errors='replace')[:200]}")
        return []

    try:
        data = json.loads(stdout.decode("utf-8"))
        return data.get("streams", [])
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"ffprobe 输出解析失败: {e}")
        return []


def _pick_best_stream(streams: list[dict]) -> dict:
    """按语言偏好选择最佳字幕轨道"""
    for pref in _LANG_PREFERENCE:
        for s in streams:
            lang = s.get("tags", {}).get("language", "").lower()
            if lang.startswith(pref):
                return s
    return streams[0]


async def _extract_stream_as_srt(file_path: str, stream_index: int) -> Optional[str]:
    """用 ffmpeg 将指定字幕流提取为 SRT 文本"""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-i", file_path,
        "-map", f"0:{stream_index}",
        "-f", "srt",
        "-v", "quiet",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(f"ffmpeg 提取字幕失败: {stderr.decode(errors='replace')[:200]}")
        return None

    try:
        return stdout.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return stdout.decode("utf-8-sig")
        except Exception:
            logger.warning("字幕内容解码失败")
            return None


def _parse_srt_to_markdown(content: str) -> str:
    """解析 SRT 字幕内容为带时间段的 Markdown 文本"""
    segments: list[tuple[float, float, str]] = []

    pattern = re.compile(
        r'(\d+)\s*\n'
        r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n'
        r'((?:(?!\n\n|\d+\s*\n\d{2}:\d{2}:\d{2}).)+)',
        re.DOTALL,
    )

    for match in pattern.finditer(content):
        start_str = match.group(2).replace(",", ".")
        end_str = match.group(3).replace(",", ".")
        text = match.group(4).strip()
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("\n", " ").strip()
        if text:
            start_sec = _timestamp_to_seconds(start_str)
            end_sec = _timestamp_to_seconds(end_str)
            segments.append((start_sec, end_sec, text))

    return _merge_and_format_segments(segments)


def _timestamp_to_seconds(timestamp: str) -> float:
    """将 HH:MM:SS.mmm 或 MM:SS.mmm 转为秒"""
    try:
        parts = timestamp.replace(",", ".").split(":")
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


def _merge_and_format_segments(segments: list[tuple[float, float, str]]) -> str:
    """去重+合并相邻字幕段（每 30 秒），格式化为 Markdown"""
    if not segments:
        return ""

    # 去重：移除完全相同的连续文本
    deduped: list[tuple[float, float, str]] = []
    prev_text = ""
    for start, end, text in segments:
        if text != prev_text:
            deduped.append((start, end, text))
            prev_text = text

    if not deduped:
        return ""

    # 按 30 秒合并
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

    # 格式化
    lines: list[str] = []
    for start, end, text in merged:
        start_fmt = _format_time_display(start)
        end_fmt = _format_time_display(end)
        lines.append(f"**{start_fmt} - {end_fmt}**  ")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def _format_time_display(seconds: float) -> str:
    """秒数格式化为 HH:MM:SS 或 MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(filename: str, max_length: int = 80, default: str = "untitled") -> str:
    """
    清洗文件名，移除危险字符
    
    Args:
        filename: 原始文件名
        max_length: 最大长度
        default: 默认名称
    
    Returns:
        安全的文件名
    """
    if not filename or not filename.strip():
        return default
    
    # 移除危险字符，只保留字母数字、下划线、连字符、空格
    safe = re.sub(r"[^\w\-\s]", "", filename)
    
    # 压缩多个空格为单个下划线
    safe = re.sub(r"\s+", "_", safe)
    
    # 去除首尾的特殊字符
    safe = safe.strip("._-")
    
    # 限制长度
    if len(safe) > max_length:
        safe = safe[:max_length]
    
    return safe if safe else default


def sanitize_title_for_filename(title: str) -> str:
    """
    将视频标题清洗为安全的文件名片段（兼容原有函数）
    
    Args:
        title: 视频标题
        
    Returns:
        安全的文件名
    """
    return sanitize_filename(title, max_length=80, default="untitled")


def validate_filename(filename: str, allowed_extensions: list = None) -> bool:
    """
    验证文件名安全性
    
    Args:
        filename: 要验证的文件名
        allowed_extensions: 允许的扩展名列表，默认为['.md']
        
    Returns:
        True if 文件名安全，False otherwise
    """
    if allowed_extensions is None:
        allowed_extensions = ['.md']
    
    # 1. 检查文件扩展名白名单
    if not any(filename.endswith(ext) for ext in allowed_extensions):
        return False
    
    # 2. 检查危险字符
    dangerous_chars = ['..', '/', '\\', '\0', ':', '*', '?', '"', '<', '>', '|']
    if any(char in filename for char in dangerous_chars):
        return False
    
    # 3. 检查文件名长度
    if len(filename) > 255:
        return False
    
    # 4. 检查文件名不为空
    if not filename or filename.strip() == '':
        return False
    
    return True
