"""2.0 source import and transcription job endpoints."""
from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.repositories import assets, content
from backend.services import v2_ingestion

router = APIRouter(prefix="/api/v2", tags=["v2 ingestion"])


@router.post("/assets/upload", status_code=201)
async def upload_asset(file: UploadFile = File(...)):
    try:
        asset, job = await v2_ingestion.create_upload_asset(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"asset": asset, "job": job}


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
