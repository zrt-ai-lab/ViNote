"""字幕优先的媒体转录入口，并负责清理自己创建的临时音频。"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional

from backend.services.audio_transcriber import AudioTranscriber
from backend.services.video_downloader import VideoDownloader
from backend.utils.file_handler import (
    cleanup_temp_audio,
    extract_audio_from_file,
    extract_embedded_subtitles,
)

logger = logging.getLogger(__name__)

MediaStage = Literal[
    "checking_subtitles", "subtitle_ready", "extracting_audio",
    "downloading_audio", "transcribing_audio",
]
StageCallback = Callable[[MediaStage], Awaitable[None]]


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    video_title: str
    used_subtitles: bool


async def _notify(callback: Optional[StageCallback], stage: MediaStage) -> None:
    if callback:
        await callback(stage)


def _result(transcript: str, title: Optional[str], used_subtitles: bool) -> TranscriptionResult:
    if not transcript or not transcript.strip():
        raise ValueError("未提取到有效的转录内容")
    return TranscriptionResult(transcript, title or "unknown", used_subtitles)


def cleanup_downloaded_audio(audio_path: str, temp_dir: Path) -> None:
    candidate = Path(audio_path).resolve()
    if not candidate.is_relative_to(temp_dir.resolve()):
        logger.error("拒绝清理临时目录外的音频: %s", candidate)
        return
    try:
        candidate.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("清理远程临时音频失败 %s: %s", candidate.name, exc)


async def transcribe_remote_media(
    url: str,
    temp_dir: Path,
    on_stage: Optional[StageCallback] = None,
    *,
    include_metadata: bool = False,
    downloader: Optional[VideoDownloader] = None,
    transcriber: Optional[AudioTranscriber] = None,
) -> TranscriptionResult:
    downloader = downloader or VideoDownloader()
    transcriber = transcriber or AudioTranscriber()
    await _notify(on_stage, "checking_subtitles")
    try:
        subtitle, title = await downloader.extract_subtitles(url, temp_dir)
    except Exception as exc:
        logger.warning("远程字幕提取失败，回退音频转录: %s", exc)
        subtitle, title = None, None
    if subtitle:
        await _notify(on_stage, "subtitle_ready")
        return _result(subtitle, title, True)

    await _notify(on_stage, "downloading_audio")
    audio_path: Optional[str] = None
    try:
        audio_path, title = await downloader.download_video_audio(url, temp_dir)
        await _notify(on_stage, "transcribing_audio")
        kwargs = {"video_title": title, "video_url": url} if include_metadata else {}
        transcript = await transcriber.transcribe_audio(audio_path, **kwargs)
        return _result(transcript, title, False)
    finally:
        if audio_path:
            cleanup_downloaded_audio(audio_path, temp_dir)


async def transcribe_local_media(
    file_path: str,
    temp_dir: Path,
    task_id: str,
    on_stage: Optional[StageCallback] = None,
    *,
    include_metadata: bool = False,
    transcriber: Optional[AudioTranscriber] = None,
) -> TranscriptionResult:
    title = Path(file_path).stem
    await _notify(on_stage, "checking_subtitles")
    try:
        subtitle = await extract_embedded_subtitles(file_path)
    except Exception as exc:
        logger.warning("本地字幕提取失败，回退音频转录: %s", exc)
        subtitle = None
    if subtitle:
        await _notify(on_stage, "subtitle_ready")
        return _result(subtitle, title, True)

    await _notify(on_stage, "extracting_audio")
    audio_path, needs_cleanup = await extract_audio_from_file(file_path, temp_dir, task_id)
    try:
        await _notify(on_stage, "transcribing_audio")
        transcriber = transcriber or AudioTranscriber()
        kwargs = {"video_title": title} if include_metadata else {}
        transcript = await transcriber.transcribe_audio(audio_path, **kwargs)
        return _result(transcript, title, False)
    finally:
        cleanup_temp_audio(audio_path, needs_cleanup)
