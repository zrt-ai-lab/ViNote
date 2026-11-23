import asyncio
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from io import BytesIO
import time

from backend.db import connection, schema
from backend.domain import JobStatus
from backend.repositories import content, jobs
from backend.routers.v2_assets import router
from backend.routers.v2_ingestion import router as ingestion_router


class V2AssetAPITests(unittest.TestCase):
    def setUp(self):
        resources = ExitStack()
        self.addCleanup(resources.close)
        root = Path(resources.enter_context(TemporaryDirectory()))
        resources.enter_context(patch.object(connection, "DB_PATH", root / "vinote.db"))
        resources.enter_context(patch.object(schema, "DB_PATH", root / "vinote.db"))
        asyncio.run(schema.init_db())
        app = FastAPI()
        app.include_router(router)
        app.include_router(ingestion_router)
        self.client = resources.enter_context(TestClient(app))

    def create_asset(self):
        payload = {
            "title": "Video lesson", "source_type": "url",
            "source_uri": "https://example.com/video", "platform": "example",
            "platform_video_id": "vid-1", "content_hash": "digest-1", "duration_ms": 4500,
        }
        response = self.client.post("/api/v2/assets", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        asset = response.json()
        self.assertEqual({key: asset[key] for key in payload}, payload)
        return asset

    def test_asset_detail_and_recycle_bin(self):
        asset = self.create_asset()
        other = self.create_asset()  # Same title must not merge related records.
        asset_id = asset["id"]
        url = f"/api/v2/assets/{asset_id}"

        async def seed():
            job = await jobs.create(asset_id, "summarize")
            artifact = await content.create_artifact(asset_id, "summary", path="summary.md", job_id=job["id"])
            segment = await content.create_segment(asset_id, 100, 500, "Video transcript")
            highlight = await content.create_highlight(asset_id, 100, 500, "Video transcript", segment_id=segment["id"])
            card = await content.create_flashcard(asset_id, "Question?", "Answer", segment_id=segment["id"])
            await content.create_segment(other["id"], 100, 500, "Unrelated transcript")
            return {"artifacts": [artifact], "segments": [segment], "highlights": [highlight],
                    "flashcards": [card], "jobs": [job]}

        self.assertEqual(self.client.get(url).json(), {
            **asset, "artifacts": [], "segments": [], "highlights": [], "flashcards": [], "jobs": [],
        })
        related = asyncio.run(seed())
        self.assertEqual(self.client.get(url).json(), {**asset, **related})
        job_url = f"/api/v2/jobs/{related['jobs'][0]['id']}"
        deleted = self.client.delete(url)
        self.assertEqual((deleted.status_code, deleted.content), (204, b""))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(job_url).status_code, 404)
        self.assertEqual(self.client.get(f"{job_url}/events").status_code, 404)
        self.assertEqual(self.client.get("/api/v2/assets").json(), [other])
        all_assets = self.client.get("/api/v2/assets?include_deleted=true").json()
        self.assertIsNotNone(next(row for row in all_assets if row["id"] == asset_id)["deleted_at"])
        restored = self.client.post(f"{url}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json(), asset)
        self.assertEqual(self.client.get(url).json(), {**asset, **related})
        self.assertEqual(self.client.get(job_url).json(), related["jobs"][0])

    def test_job_event_cursor_is_exclusive_and_scoped_to_job(self):
        asset_id = self.create_asset()["id"]

        async def seed():
            job = await jobs.create(asset_id, "transcribe")
            await jobs.create(asset_id, "summarize")
            return await jobs.transition(job["id"], JobStatus.QUEUED, JobStatus.RUNNING, stage="asr")

        job = asyncio.run(seed())
        url = f"/api/v2/jobs/{job['id']}"
        self.assertEqual(self.client.get(url).json(), job)
        events = self.client.get(f"{url}/events").json()
        self.assertEqual([row["status"] for row in events], ["queued", "running"])
        self.assertTrue(all(row["job_id"] == job["id"] for row in events))
        self.assertEqual(self.client.get(f"{url}/events?after_id={events[0]['id']}").json(), events[1:])
        self.assertEqual(self.client.get(f"{url}/events?after_id={events[-1]['id']}").json(), [])
        for cursor in (-1, "invalid", 2**63):
            self.assertEqual(self.client.get(f"{url}/events?after_id={cursor}").status_code, 422)

    def test_invalid_input_and_missing_resources(self):
        for fields in ({"title": "  "}, {"source_type": "unknown"}, {"duration_ms": -1}, {"duration_ms": 2**63}):
            with self.subTest(fields=fields):
                payload = {"title": "Lesson", "source_type": "upload", **fields}
                self.assertEqual(self.client.post("/api/v2/assets", json=payload).status_code, 422)
        self.assertEqual(self.client.get("/api/v2/assets").json(), [])
        for method, path in (
            ("GET", "assets/missing"), ("DELETE", "assets/missing"), ("POST", "assets/missing/restore"),
            ("GET", "jobs/missing"), ("GET", "jobs/missing/events"),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.client.request(method, f"/api/v2/{path}").status_code, 404)

    def test_subtitle_upload_creates_asset_and_persists_segments(self):
        subtitle = b"1\n00:00:01,000 --> 00:00:02,500\nHello world\n"
        response = self.client.post("/api/v2/assets/upload", files={"file": ("lesson.srt", BytesIO(subtitle), "application/x-subrip")})
        self.assertEqual(response.status_code, 201, response.text)
        asset = response.json()["asset"]
        self.assertEqual(response.json()["job"]["kind"], "transcribe")
        deadline = time.time() + 2
        segments = []
        while time.time() < deadline:
            segments = self.client.get(f"/api/v2/assets/{asset['id']}/segments").json()
            if segments:
                break
            time.sleep(0.02)
        self.assertEqual(segments[0]["start_ms"], 1000)
        self.assertEqual(segments[0]["end_ms"], 2500)
        self.assertEqual(segments[0]["text"], "Hello world")
