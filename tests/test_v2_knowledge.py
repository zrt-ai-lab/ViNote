import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import connection, schema
from backend.repositories import assets, content
from backend.routers.v2_knowledge import router


class V2KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(connection, "DB_PATH", root / "vinote.db"), patch.object(schema, "DB_PATH", root / "vinote.db")]
        for item in self.patches: item.start()
        self.addCleanup(self._cleanup)
        asyncio.run(schema.init_db())
        app = FastAPI(); app.include_router(router); self.client = TestClient(app)

    def _cleanup(self):
        for item in reversed(self.patches): item.stop()
        self.tmp.cleanup()

    def test_question_returns_segment_citations(self):
        asset = asyncio.run(assets.create("Lesson", "upload"))
        asyncio.run(content.create_segment(asset["id"], 1000, 2000, "SQLite stores the transcript"))
        response = self.client.post(f"/api/v2/assets/{asset['id']}/questions", json={"question": "SQLite"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["citations"][0]["start_ms"], 1000)

    def test_summary_requires_transcript(self):
        asset = asyncio.run(assets.create("Lesson", "upload"))
        self.assertEqual(self.client.post(f"/api/v2/assets/{asset['id']}/artifacts/summary").status_code, 409)
