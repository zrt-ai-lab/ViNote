"""Versioned output metadata, timeline text and user annotations."""
from backend.domain import ReviewState

from ._sqlite import delete_row, insert, read_all, read_one, write_one


async def create_artifact(
    asset_id: str, kind: str, *, path: str, job_id: str | None = None,
    version: int = 1, content_hash: str | None = None,
) -> dict:
    return await insert(
        "artifacts", asset_id=asset_id, kind=kind, path=path, job_id=job_id,
        version=version, content_hash=content_hash,
    )


async def get_artifact(artifact_id: str) -> dict | None:
    return await read_one("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))


async def list_artifacts(asset_id: str) -> list[dict]:
    return await read_all("SELECT * FROM artifacts WHERE asset_id = ? ORDER BY kind, version", (asset_id,))


async def delete_artifact(artifact_id: str) -> bool:
    """Remove metadata only. File lifecycle belongs to the caller."""
    return await delete_row("artifacts", artifact_id)


async def create_segment(
    asset_id: str, start_ms: int, end_ms: int, text: str, *,
    speaker: str | None = None, language: str | None = None, confidence: float | None = None,
) -> dict:
    return await insert(
        "transcript_segments", asset_id=asset_id, start_ms=start_ms, end_ms=end_ms,
        text=text, speaker=speaker, language=language, confidence=confidence,
    )


async def get_segment(segment_id: str) -> dict | None:
    return await read_one("SELECT * FROM transcript_segments WHERE id = ?", (segment_id,))


async def list_segments(asset_id: str) -> list[dict]:
    return await read_all(
        "SELECT * FROM transcript_segments WHERE asset_id = ? ORDER BY start_ms, end_ms, id", (asset_id,),
    )


async def correct_segment(segment_id: str, edited_text: str | None) -> dict | None:
    return await write_one(
        "UPDATE transcript_segments SET edited_text = ? WHERE id = ? RETURNING *", (edited_text, segment_id),
    )


async def delete_segment(segment_id: str) -> bool:
    return await delete_row("transcript_segments", segment_id)


async def create_highlight(
    asset_id: str, start_ms: int, end_ms: int, text_snapshot: str, *,
    segment_id: str | None = None, user_note: str | None = None,
) -> dict:
    return await insert(
        "highlights", asset_id=asset_id, start_ms=start_ms, end_ms=end_ms,
        text_snapshot=text_snapshot, segment_id=segment_id, user_note=user_note,
    )


async def list_highlights(asset_id: str) -> list[dict]:
    return await read_all("SELECT * FROM highlights WHERE asset_id = ? ORDER BY start_ms, id", (asset_id,))


async def update_highlight(highlight_id: str, user_note: str | None) -> dict | None:
    return await write_one("UPDATE highlights SET user_note = ? WHERE id = ? RETURNING *", (user_note, highlight_id))


async def delete_highlight(highlight_id: str) -> bool:
    return await delete_row("highlights", highlight_id)


async def create_flashcard(
    asset_id: str, question: str, answer: str, *, segment_id: str | None = None,
) -> dict:
    return await insert("flashcards", asset_id=asset_id, question=question, answer=answer, segment_id=segment_id)


async def list_flashcards(asset_id: str) -> list[dict]:
    return await read_all("SELECT * FROM flashcards WHERE asset_id = ? ORDER BY created_at, id", (asset_id,))


async def update_flashcard(card_id: str, question: str, answer: str) -> dict | None:
    return await write_one(
        "UPDATE flashcards SET question = ?, answer = ? WHERE id = ? RETURNING *", (question, answer, card_id),
    )


async def review_flashcard(
    card_id: str, state: ReviewState, *, next_review_at: str | None = None,
) -> dict | None:
    return await write_one(
        "UPDATE flashcards SET review_state = ?, next_review_at = ? WHERE id = ? RETURNING *",
        (ReviewState(state).value, next_review_at, card_id),
    )


async def delete_flashcard(card_id: str) -> bool:
    return await delete_row("flashcards", card_id)
