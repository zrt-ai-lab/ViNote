"""Asset metadata, recycle bin, and durable job history endpoints."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.repositories import assets
from backend.services import v2_assets

router = APIRouter(prefix="/api/v2", tags=["v2 assets"])
SQLITE_INT_MAX = 2**63 - 1


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=512)
    source_type: Literal["url", "upload", "local"]
    source_uri: str | None = Field(default=None, max_length=4096)
    platform: str | None = Field(default=None, max_length=128)
    platform_video_id: str | None = Field(default=None, max_length=512)
    content_hash: str | None = Field(default=None, max_length=256)
    duration_ms: int | None = Field(default=None, strict=True, ge=0, le=SQLITE_INT_MAX)


@router.get("/assets")
async def list_assets(include_deleted: bool = False):
    return await assets.list_assets(include_deleted=include_deleted)


@router.post("/assets", status_code=201)
async def create_asset(payload: AssetCreate):
    # The source URI is metadata. Registration never fetches or opens it.
    return await assets.create(**payload.model_dump())


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    detail = await v2_assets.get_asset_detail(asset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return detail


@router.delete("/assets/{asset_id}", status_code=204, response_class=Response)
async def delete_asset(asset_id: str):
    if not await assets.delete(asset_id):
        raise HTTPException(status_code=404, detail="Asset not found")


@router.post("/assets/{asset_id}/restore")
async def restore_asset(asset_id: str):
    asset = await assets.restore(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found in recycle bin")
    return asset


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = await v2_assets.get_visible_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/events")
async def list_job_events(job_id: str, after_id: Annotated[int, Query(ge=0, le=SQLITE_INT_MAX)] = 0):
    events = await v2_assets.get_job_events(job_id, after_id=after_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return events
