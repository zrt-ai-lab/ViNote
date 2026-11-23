"""Controlled source ingestion for the ViNote 2.0 asset workflow."""
import hashlib
import re
import uuid
import asyncio
import os
from pathlib import Path

from fastapi import UploadFile

from backend.config.settings import PROJECT_ROOT
from backend.repositories import assets, content, jobs
from backend.domain import JobStatus

UPLOAD_DIR = PROJECT_ROOT / "temp" / "uploads"
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".mkv", ".webm", ".srt", ".vtt", ".txt"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


async def save_upload(upload: UploadFile) -> dict:
    filename = Path(upload.filename or "upload.bin").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported media type: {suffix or 'unknown'}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    target = UPLOAD_DIR / f"{digest.hexdigest()}{suffix}"
    temp = UPLOAD_DIR / f".upload-{uuid.uuid4().hex}.part"
    try:
        with temp.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError("Upload exceeds the 2 GiB limit")
                digest.update(chunk)
                output.write(chunk)
        target = UPLOAD_DIR / f"{digest.hexdigest()}{suffix}"
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return {"filename": filename, "path": str(target), "size": size, "content_hash": digest.hexdigest()}


async def create_upload_asset(upload: UploadFile) -> tuple[dict, dict]:
    saved = await save_upload(upload)
    asset = await assets.create(upload.filename or "Uploaded media", "upload", source_uri=saved["path"], content_hash=saved["content_hash"])
    job = await jobs.create(asset["id"], "transcribe")
    return asset, job


def parse_subtitle_file(path: str) -> list[dict]:
    """Parse common SRT/VTT blocks into timestamped transcript rows."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows: list[dict] = []
    pattern = re.compile(r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    def ms(value: str) -> int:
        h, m, rest = value.replace(',', '.').split(':')
        s, fraction = rest.split('.')
        return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(fraction.ljust(3, '0')[:3])
    for block in blocks:
        match = pattern.search(block)
        if not match:
            continue
        lines = block[match.end():].strip().splitlines()
        cleaned = " ".join(line.strip() for line in lines if line.strip() and not line.strip().startswith(('WEBVTT', 'NOTE')))
        if cleaned:
            rows.append({"start_ms": ms(match.group('start')), "end_ms": ms(match.group('end')), "text": cleaned})
    return rows


async def create_transcription_job(asset_id: str) -> dict:
    segments = await content.list_segments(asset_id)
    if segments:
        raise ValueError("Transcript already exists for this asset")
    return await jobs.create(asset_id, "transcribe")


async def process_media_job(job_id: str, asset_id: str, source: str, *, is_url: bool = False) -> None:
    claimed = await jobs.transition(job_id, JobStatus.QUEUED, JobStatus.RUNNING, stage="transcribing")
    if claimed is None: return
    audio_path = source; temporary_audio = False
    try:
        if is_url:
            import yt_dlp
            output = UPLOAD_DIR / f"{asset_id}.%(ext)s"
            options = {"format": "bestaudio/best", "outtmpl": str(output), "noplaylist": True, "quiet": True, "no_warnings": True, "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]}
            await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(options).download([source]))
            candidates = sorted(UPLOAD_DIR.glob(f"{asset_id}.*"))
            if not candidates: raise RuntimeError("media download produced no audio file")
            audio_path = str(candidates[0]); temporary_audio = True
        from backend.services.audio_transcriber import AudioTranscriber
        from backend.core.ai_client import get_asr_model
        segments, info = await asyncio.to_thread(AudioTranscriber()._do_whisper_transcribe, get_asr_model(), audio_path, None)
        rows = [{"start_ms": int(s.start * 1000), "end_ms": int(s.end * 1000), "text": s.text.strip(), "language": getattr(info, "language", None)} for s in segments if getattr(s, "text", "").strip() and s.end > s.start]
        if not rows: raise RuntimeError("transcriber returned no segments")
        for row in rows: await content.create_segment(asset_id, **row)
        artifact_path = UPLOAD_DIR / f"{asset_id}.transcript.json"
        artifact_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        await content.create_artifact(asset_id, "transcript", path=str(artifact_path), job_id=job_id)
        await jobs.transition(job_id, JobStatus.RUNNING, JobStatus.COMPLETED, stage="persisted")
    except Exception as exc: await jobs.transition(job_id, JobStatus.RUNNING, JobStatus.FAILED, error=str(exc))
    finally:
        if temporary_audio:
            try: os.unlink(audio_path)
            except OSError: pass
