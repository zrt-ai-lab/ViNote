"""Asset-bound knowledge outputs for ViNote 2.0."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.state import TEMP_DIR
from backend.repositories import assets, content, jobs
from backend.domain import JobStatus, ReviewState

router = APIRouter(prefix="/api/v2/assets", tags=["v2 knowledge"])


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class Highlight(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text_snapshot: str = Field(min_length=1, max_length=20000)
    segment_id: str | None = None
    user_note: str | None = Field(default=None, max_length=4000)


class Flashcard(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=10000)
    segment_id: str | None = None


def _source_rows(rows: list[dict], question: str) -> list[dict]:
    terms = {term.lower() for term in question.split() if len(term) > 1}
    ranked = sorted(rows, key=lambda row: sum(term in row["text"].lower() for term in terms), reverse=True)
    return [row for row in ranked if not terms or any(term in row["text"].lower() for term in terms)][:5] or rows[:3]


@router.post("/{asset_id}/questions")
async def ask_asset(asset_id: str, payload: Question):
    if await assets.get(asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    rows = await content.list_segments(asset_id)
    if not rows:
        raise HTTPException(status_code=409, detail="Transcript is not ready")
    cited = _source_rows(rows, payload.question)
    return {
        "answer": "根据视频原文，" + " ".join(row["text"] for row in cited),
        "citations": [{"segment_id": row["id"], "start_ms": row["start_ms"], "end_ms": row["end_ms"], "quote": row["text"]} for row in cited],
    }


@router.post("/{asset_id}/highlights", status_code=201)
async def create_highlight(asset_id: str, payload: Highlight):
    if await assets.get(asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if payload.end_ms <= payload.start_ms:
        raise HTTPException(status_code=422, detail="end_ms must be greater than start_ms")
    return await content.create_highlight(asset_id, **payload.model_dump())


@router.post("/{asset_id}/flashcards", status_code=201)
async def create_flashcard(asset_id: str, payload: Flashcard):
    if await assets.get(asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return await content.create_flashcard(asset_id, **payload.model_dump())


@router.post("/{asset_id}/artifacts/summary", status_code=201)
async def create_summary(asset_id: str):
    asset = await assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    rows = await content.list_segments(asset_id)
    if not rows:
        raise HTTPException(status_code=409, detail="Transcript is not ready")
    output_dir = TEMP_DIR / "artifacts" / asset_id
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary-v1.md"
    body = "# " + asset["title"] + "\n\n" + "\n\n".join(f"- [{row['start_ms']}ms] {row['text']}" for row in rows[:20])
    path.write_text(body, encoding="utf-8")
    return await content.create_artifact(asset_id, "summary", path=str(path), content_hash=None)
