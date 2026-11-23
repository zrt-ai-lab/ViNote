"""Exercise the v2 repositories against a real, isolated SQLite database."""
import asyncio
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.db import connection, schema


class V2DomainTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for target, name, value in (
            (connection, "DB_PATH", self.root / "vinote.db"),
            (schema, "DB_PATH", self.root / "vinote.db"),
            (schema, "TEMP_DIR", self.root),
        ):
            mocked = patch.object(target, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)

    async def test_init_is_additive_and_idempotent(self):
        async with connection.get_db() as db:
            await db.executescript("""
                CREATE TABLE notes (
                    id INTEGER PRIMARY KEY, short_id TEXT NOT NULL UNIQUE,
                    category_id INTEGER, created_at TEXT, title TEXT
                );
                INSERT INTO notes (short_id, title) VALUES ('legacy', 'Legacy note');
                CREATE TABLE search_agent_sessions (session_id TEXT PRIMARY KEY);
            """)
        (self.root / "raw_sample_legacy.md").write_text("original", encoding="utf-8")
        await schema.init_db()
        await schema.init_db()
        async with connection.get_db() as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            names = {row[0] for row in await cursor.fetchall()}
            self.assertTrue({
                "media_assets", "processing_jobs", "job_events", "artifacts",
                "transcript_segments", "highlights", "flashcards", "note_search",
            } <= names)
            cursor = await db.execute("SELECT title, raw_transcript_file, warnings_json FROM notes")
            self.assertEqual(tuple(await cursor.fetchone()), ("Legacy note", "raw_sample_legacy.md", "[]"))
            cursor = await db.execute("SELECT COUNT(*) FROM categories")
            self.assertEqual((await cursor.fetchone())[0], len(schema.PREDEFINED_CATEGORIES))
            cursor = await db.execute("PRAGMA table_info(search_agent_sessions)")
            self.assertIn("search_state_json", {row[1] for row in await cursor.fetchall()})

    async def test_jobs_record_atomic_transitions_and_retry_history(self):
        from backend.domain import JobStatus
        from backend.repositories import assets, jobs

        await schema.init_db()
        asset = await assets.create("Lesson", "url", source_uri="https://example.com/video")
        job = await jobs.create(asset["id"], "transcribe")
        claims = await asyncio.gather(*(
            jobs.transition(job["id"], JobStatus.QUEUED, JobStatus.RUNNING, stage="asr")
            for _ in range(2)
        ))
        self.assertEqual(sum(claim is not None for claim in claims), 1)
        with self.assertRaises(ValueError):
            await jobs.transition(job["id"], JobStatus.RUNNING, JobStatus.QUEUED)
        failed = await jobs.transition(
            job["id"], JobStatus.RUNNING, JobStatus.FAILED, error="worker interrupted"
        )
        self.assertEqual((failed["stage"], failed["error"]), ("asr", "worker interrupted"))
        retried = await jobs.transition(job["id"], JobStatus.FAILED, JobStatus.QUEUED)
        self.assertEqual((retried["attempt"], retried["stage"], retried["error"]), (2, None, None))
        events = await jobs.list_events(job["id"])
        self.assertEqual([event["status"] for event in events], ["queued", "running", "failed", "queued"])
        self.assertEqual(await jobs.list_events(job["id"], after_id=events[2]["id"]), events[3:])
        async with connection.get_db() as db:
            await db.execute("""CREATE TRIGGER reject_event BEFORE INSERT ON job_events
                BEGIN SELECT RAISE(ABORT, 'event write rejected'); END""")
            await db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            await jobs.transition(job["id"], JobStatus.QUEUED, JobStatus.RUNNING)
        self.assertEqual((await jobs.get(job["id"]))["status"], "queued")
        async with connection.get_db() as db:
            await db.execute("DROP TRIGGER reject_event")
            await db.commit()
        await jobs.transition(job["id"], JobStatus.QUEUED, JobStatus.RUNNING, expected_attempt=2)
        self.assertIsNone(await jobs.transition(
            job["id"], JobStatus.RUNNING, JobStatus.COMPLETED, expected_attempt=1,
        ))
        await jobs.set_stage(job["id"], "persisting", expected_attempt=2)
        event = (await jobs.list_events(job["id"]))[-1]
        self.assertEqual((event["status"], event["stage"], event["attempt"]), ("running", "persisting", 2))

    async def test_artifacts_and_user_annotations_keep_their_source(self):
        from backend.repositories import assets, content, jobs

        await schema.init_db()
        asset = await assets.create("Lesson", "upload")
        other = await assets.create("Lesson", "upload")
        asset_id = asset["id"]
        job = await jobs.create(asset_id, "summarize")
        with self.assertRaises(sqlite3.IntegrityError):
            await content.create_artifact(other["id"], "summary", path="wrong.md", job_id=job["id"])
        first = await content.create_artifact(asset_id, "summary", path="first.md", job_id=job["id"])
        second = await content.create_artifact(asset_id, "summary", path="second.md", version=2)
        with self.assertRaises(sqlite3.IntegrityError):
            await content.create_artifact(asset_id, "summary", path="duplicate.md", version=2)
        self.assertEqual(await content.list_artifacts(asset_id), [first, second])
        with self.assertRaises(sqlite3.IntegrityError):
            await content.create_segment(asset_id, 2000, 1000, "Invalid range")
        segment = await content.create_segment(asset_id, 1000, 2000, "Original words")
        with self.assertRaises(sqlite3.IntegrityError):
            await content.create_highlight(other["id"], 1000, 2000, "Wrong source", segment_id=segment["id"])
        highlight = await content.create_highlight(asset_id, 1000, 2000, "Original words", segment_id=segment["id"])
        card = await content.create_flashcard(asset_id, "Question?", "Answer", segment_id=segment["id"])
        edited = await content.correct_segment(segment["id"], "Corrected words")
        self.assertEqual((edited["text"], edited["edited_text"]), ("Original words", "Corrected words"))
        annotated = await content.update_highlight(highlight["id"], "Check again")
        self.assertEqual((annotated["text_snapshot"], annotated["user_note"]), ("Original words", "Check again"))
        reviewed = await content.review_flashcard(card["id"], "remembered", next_review_at="2026-11-24T08:00:00Z")
        self.assertEqual((reviewed["review_state"], reviewed["next_review_at"]), ("remembered", "2026-11-24T08:00:00Z"))
        with self.assertRaises(sqlite3.IntegrityError):
            await content.delete_segment(segment["id"])
        self.assertTrue(await assets.delete(asset_id))
        self.assertIsNone(await assets.get(asset_id))
        self.assertEqual([row["id"] for row in await assets.list_assets()], [other["id"]])
        self.assertIsNotNone(await assets.restore(asset_id))
        self.assertEqual(await content.list_highlights(asset_id), [annotated])
        self.assertEqual(await content.list_flashcards(asset_id), [reviewed])
        self.assertTrue(await content.delete_highlight(highlight["id"]))
        self.assertTrue(await content.delete_flashcard(card["id"]))
        self.assertTrue(await content.delete_segment(segment["id"]))
        self.assertTrue(await content.delete_artifact(first["id"]))
        self.assertEqual(await content.list_artifacts(asset_id), [second])
