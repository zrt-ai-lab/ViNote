"""
文件处理工具函数
文件名清洗、验证、音频提取等
"""
import asyncio
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


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
