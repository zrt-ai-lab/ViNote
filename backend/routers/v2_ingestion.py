"""2.0 source import and transcription job endpoints."""
import asyncio
import json
from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.repositories import assets, content
from backend.domain import JobStatus
from backend.repositories import jobs
from backend.services import v2_ingestion

router = APIRouter(prefix="/api/v2", tags=["v2 ingestion"])


@router.post("/assets/upload", status_code=201)
async def upload_asset(file: UploadFile = File(...)):
    try:
        asset, job = await v2_ingestion.create_upload_asset(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if (file.filename or '').lower().endswith(('.srt', '.vtt')):
        await _process_subtitle_job(job["id"], asset["id"], saved_path=asset["source_uri"])
    elif (file.filename or '').lower().endswith(('.mp3', '.wav', '.m4a', '.mp4', '.mov', '.mkv', '.webm')):
        import asyncio
        asyncio.create_task(v2_ingestion.process_media_job(job["id"], asset["id"], asset["source_uri"] or ""))
    return {"asset": asset, "job": job}


async def _process_subtitle_job(job_id: str, asset_id: str, *, saved_path: str | None):
    try:
        claimed = await jobs.transition(job_id, JobStatus.QUEUED, JobStatus.RUNNING, stage="parsing")
        if claimed is None or not saved_path:
            return
        rows = v2_ingestion.parse_subtitle_file(saved_path)
        for row in rows:
            await content.create_segment(asset_id, **row)
        artifact_path = v2_ingestion.UPLOAD_DIR / f"{asset_id}.transcript.json"
        artifact_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        await content.create_artifact(asset_id, "transcript", path=str(artifact_path), job_id=job_id)
        await jobs.transition(job_id, JobStatus.RUNNING, JobStatus.COMPLETED, stage="persisted")
    except Exception as exc:
        current = await jobs.get(job_id)
        if current and current["status"] == JobStatus.RUNNING.value:
            await jobs.transition(job_id, JobStatus.RUNNING, JobStatus.FAILED, error=str(exc))


@router.post("/assets/{asset_id}/jobs", status_code=201)
async def create_job(asset_id: str):
    if await assets.get(asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        return await v2_ingestion.create_transcription_job(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/segments")
async def list_segments(asset_id: str):
    if await assets.get(asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return await content.list_segments(asset_id)
