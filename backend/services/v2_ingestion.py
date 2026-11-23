"""Controlled source ingestion for the ViNote 2.0 asset workflow."""
import hashlib
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
    temp = UPLOAD_DIR / f".upload-{digest.hexdigest()}.part"
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


async def create_transcription_job(asset_id: str) -> dict:
    segments = await content.list_segments(asset_id)
    if segments:
        raise ValueError("Transcript already exists for this asset")
    return await jobs.create(asset_id, "transcribe")
