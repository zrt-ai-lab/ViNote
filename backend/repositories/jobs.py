"""Job state operations and a durable, cursor-based event history."""
from backend.db.connection import get_db
from backend.domain import JobStatus, validate_job_transition

from ._sqlite import fetch_one, new_id, read_all, read_one


async def _record_event(db, job: dict) -> None:
    async with db.execute(
        "INSERT INTO job_events (job_id, status, stage, error, attempt) VALUES (?, ?, ?, ?, ?)",
        (job["id"], job["status"], job["stage"], job["error"], job["attempt"]),
    ):
        pass


async def create(asset_id: str, kind: str) -> dict:
    async with get_db() as db:
        job = await fetch_one(
            db, "INSERT INTO processing_jobs (id, asset_id, kind) VALUES (?, ?, ?) RETURNING *",
            (new_id(), asset_id, kind),
        )
        await _record_event(db, job)
        await db.commit()
        return job


async def get(job_id: str) -> dict | None:
    return await read_one("SELECT * FROM processing_jobs WHERE id = ?", (job_id,))


async def list_jobs(asset_id: str) -> list[dict]:
    return await read_all(
        "SELECT * FROM processing_jobs WHERE asset_id = ? ORDER BY created_at, id", (asset_id,),
    )


async def list_events(job_id: str, *, after_id: int = 0) -> list[dict]:
    return await read_all(
        "SELECT * FROM job_events WHERE job_id = ? AND id > ? ORDER BY id", (job_id, after_id),
    )


async def transition(
    job_id: str, expected: JobStatus, target: JobStatus, *,
    stage: str | None = None, error: str | None = None, expected_attempt: int | None = None,
) -> dict | None:
    """Apply and record a transition; return None if the expected state no longer matches.

    Workers can also pass expected_attempt to guard writes after a retry.
    """
    expected, target = JobStatus(expected), JobStatus(target)
    validate_job_transition(expected, target)
    retry = target == JobStatus.QUEUED
    return await _update_state(job_id, expected, target, stage, error, retry, expected_attempt)


async def set_stage(job_id: str, stage: str, *, expected_attempt: int) -> dict | None:
    """Record a progress event for the current running attempt."""
    return await _update_state(
        job_id, JobStatus.RUNNING, JobStatus.RUNNING, stage, None, False, expected_attempt,
    )


async def _update_state(job_id, expected, target, stage, error, retry, expected_attempt):
    async with get_db() as db:
        job = await fetch_one(
            db, """UPDATE processing_jobs
                   SET status = ?, stage = CASE WHEN ? THEN NULL ELSE coalesce(?, stage) END,
                       error = ?, attempt = attempt + ?, updated_at = datetime('now')
                   WHERE id = ? AND status = ? AND (? IS NULL OR attempt = ?)
                   RETURNING *""",
            (target.value, retry, stage, None if retry else error, retry, job_id,
             expected.value, expected_attempt, expected_attempt),
        )
        if job is not None:
            await _record_event(db, job)
            await db.commit()
        return job
