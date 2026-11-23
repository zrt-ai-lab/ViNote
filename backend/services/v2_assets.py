"""Compose v2 asset and job reads from the SQLite repositories."""
from backend.repositories import assets, content, jobs


async def get_asset_detail(asset_id: str) -> dict | None:
    asset = await assets.get(asset_id)
    if asset is None:
        return None
    return {
        **asset,
        "artifacts": await content.list_artifacts(asset_id),
        "segments": await content.list_segments(asset_id),
        "highlights": await content.list_highlights(asset_id),
        "flashcards": await content.list_flashcards(asset_id),
        "jobs": await jobs.list_jobs(asset_id),
    }


async def get_visible_job(job_id: str) -> dict | None:
    job = await jobs.get(job_id)
    if job is None or await assets.get(job["asset_id"]) is None:
        return None
    return job


async def get_job_events(job_id: str, *, after_id: int) -> list[dict] | None:
    if await get_visible_job(job_id) is None:
        return None
    return await jobs.list_events(job_id, after_id=after_id)
