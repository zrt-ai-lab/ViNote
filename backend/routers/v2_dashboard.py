"""Dashboard aggregates for the ViNote 2.0 workbench."""
from fastapi import APIRouter
from backend.repositories import assets
from backend.db.connection import get_db

router = APIRouter(prefix="/api/v2/dashboard", tags=["v2 dashboard"])

@router.get("")
async def dashboard():
    items = await assets.list_assets()
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM processing_jobs WHERE status = 'failed'") as cursor:
            failed_jobs = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM flashcards WHERE next_review_at IS NOT NULL AND next_review_at <= datetime('now')") as cursor:
            due_cards = (await cursor.fetchone())[0]
    return {"recent_assets": items[:3], "failed_jobs": failed_jobs, "due_cards": due_cards}
