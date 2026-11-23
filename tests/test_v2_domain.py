import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.db import connection, schema
from backend.domain import JobStatus
from backend.repositories import assets, content, jobs


class V2DomainTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.db_patch = patch.object(connection, 'DB_PATH', self.root / 'vinote.db')
        self.schema_db_patch = patch.object(schema, 'DB_PATH', self.root / 'vinote.db')
        self.db_patch.start()
        self.schema_db_patch.start()
        self.addAsyncCleanup(self.cleanup)
        await schema.init_db()

    async def cleanup(self):
        self.schema_db_patch.stop()
        self.db_patch.stop()
        self.directory.cleanup()

    async def test_schema_is_idempotent_and_only_v2_tables_are_created(self):
        await schema.init_db()
        async with connection.get_db() as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            names = {row[0] for row in await cursor.fetchall()}
        self.assertTrue({'media_assets', 'processing_jobs', 'job_events', 'artifacts', 'transcript_segments', 'highlights', 'flashcards'} <= names)
        self.assertNotIn('notes', names)

    async def test_job_transition_and_source_integrity(self):
        asset = await assets.create('Lesson', 'upload')
        job = await jobs.create(asset['id'], 'transcribe')
        running = await jobs.transition(job['id'], JobStatus.QUEUED, JobStatus.RUNNING, stage='asr')
        self.assertEqual(running['status'], 'running')
        failed = await jobs.transition(job['id'], JobStatus.RUNNING, JobStatus.FAILED, error='interrupted')
        self.assertEqual(failed['error'], 'interrupted')
        retried = await jobs.transition(job['id'], JobStatus.FAILED, JobStatus.QUEUED)
        self.assertEqual(retried['attempt'], 2)
        segment = await content.create_segment(asset['id'], 100, 500, 'Source')
        highlight = await content.create_highlight(asset['id'], 100, 500, 'Source', segment_id=segment['id'])
        self.assertEqual((await content.list_highlights(asset['id']))[0]['id'], highlight['id'])
