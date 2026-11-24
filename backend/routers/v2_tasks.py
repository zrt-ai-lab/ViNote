"""Processing task views for the ViNote 2.0 task center."""
from fastapi import APIRouter
from backend.db.connection import get_db
from backend.repositories import jobs

router = APIRouter(prefix="/api/v2/tasks", tags=["v2 tasks"])

@router.get("")
async def list_tasks(limit: int = 50):
    limit = min(max(limit, 1), 200)
    async with get_db() as db:
        async with db.execute("SELECT * FROM processing_jobs ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
    return rows

@router.get("/{job_id}/events")
async def task_events(job_id: str, after_id: int = 0):
    return await jobs.list_events(job_id, after_id=after_id)
