"""Controlled source ingestion for the ViNote 2.0 asset workflow."""
import hashlib
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from backend.core.state import TEMP_DIR
from backend.repositories import assets, content, jobs

UPLOAD_DIR = TEMP_DIR / "uploads"
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
