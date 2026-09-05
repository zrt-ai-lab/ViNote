"""Real SQLite and artifact contracts; no network or user content."""
from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.db import connection, schema
from backend.routers import tasks as task_routes
from backend.services import note_repository as notes, note_search


class SearchDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        for item in [
            patch.object(connection, "DB_PATH", self.root / "test.db"),
            patch.object(schema, "TEMP_DIR", self.root),
            patch.object(note_search, "TEMP_DIR", self.root),
            patch.object(task_routes, "TEMP_DIR", self.root),
            patch.object(task_routes, "tasks", {}),
        ]:
            item.start()
            self.addCleanup(item.stop)
        await schema.init_db()

    async def make_note(self, short_id="abc123", title="演示笔记", body="正文后段有量子纠错知识"):
        filename = f"transcript_demo_{short_id}.md"
        (self.root / filename).write_text(body, encoding="utf-8")
        summary = f"summary_demo_{short_id}.md"
        (self.root / summary).write_text("摘要仅提到光学芯片", encoding="utf-8")
        await notes.save_note(short_id, title=title, task_id=f"uuid-{short_id}",
                              transcript_file=filename, summary_file=summary,
                              has_transcript=True, has_summary=True)
        return filename, summary

    async def ids(self, query, **kwargs):
        result = await notes.list_notes(search=query, **kwargs)
        return [row["task_id"] for row in result["tasks"]]

    async def test_search_title_body_summary_and_short_chinese(self):
        await self.make_note()
        for query in ("演示", "量子纠错", "光学芯片", "纠错", "芯"):
            with self.subTest(query=query):
                self.assertEqual(await self.ids(query), ["abc123"])
        self.assertEqual(await self.ids("不存在"), [])

    async def test_literal_query_and_case(self):
        await self.make_note(body='SQLite supports "quoted" strings, 100% and a_b, and %%%.')
        for query in ("sqlite", '"quoted"', "100%", "a_b", "%%%", "%"):
            with self.subTest(query=query):
                self.assertEqual(await self.ids(query), ["abc123"])
        self.assertEqual(await self.ids("%wrong%"), [])

    async def test_raw_transcript_is_searchable(self):
        await self.make_note()
        filename = "raw_demo_abc123.md"
        (self.root / filename).write_text("原始发言特有内容", encoding="utf-8")
        await notes.update_note_artifacts("abc123", raw_transcript_file=filename)
        self.assertEqual(await self.ids("特有内容"), ["abc123"])

    async def test_artifact_update_replaces_stale_index(self):
        filename, _ = await self.make_note()
        (self.root / filename).write_text("全新植物学材料", encoding="utf-8")
        await notes.update_note_artifacts("abc123", transcript_file=filename)
        self.assertEqual(await self.ids("植物学"), ["abc123"])
        self.assertEqual(await self.ids("量子纠错"), [])

    async def test_delete_cascades_search_and_retains_other_note(self):
        await self.make_note()
        await self.make_note("def456")
        await notes.delete_note("abc123")
        self.assertEqual(await self.ids("量子纠错"), ["def456"])
        await notes.delete_all_notes()
        self.assertEqual(await self.ids("量子纠错"), [])

    async def test_filters_counts_and_stable_pagination(self):
        await self.make_note()
        await self.make_note("def456")
        await notes.set_note_tags("abc123", ["selected"])
        self.assertEqual(await self.ids("量子纠错", tag="selected"), ["abc123"])
        first = await notes.list_notes(search="量子纠错", page_size=1, page=1)
        second = await notes.list_notes(search="量子纠错", page_size=1, page=2)
        self.assertEqual((first["total"], second["total"]), (2, 2))
        self.assertNotEqual(first["tasks"][0]["task_id"], second["tasks"][0]["task_id"])

    async def test_old_rows_backfill_is_idempotent(self):
        filename, _ = await self.make_note()
        async with connection.get_db() as db:
            await db.execute("DELETE FROM note_search")
            await db.commit()
        self.assertEqual(await self.ids("量子纠错"), [])
        await note_search.backfill_note_search()
        await note_search.backfill_note_search()
        self.assertEqual(await self.ids("量子纠错"), ["abc123"])
        self.assertEqual((self.root / filename).read_text(encoding="utf-8"), "正文后段有量子纠错知识")

    async def test_fallback_without_fts_has_same_result(self):
        await self.make_note()
        async with connection.get_db() as db:
            for trigger in ("note_search_ai", "note_search_ad", "note_search_au"):
                await db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            await db.execute("DROP TABLE IF EXISTS note_search_fts")
            await db.commit()
        self.assertEqual(await self.ids("量子纠错"), ["abc123"])

    async def test_unsafe_filename_is_not_read(self):
        await self.make_note()
        await notes.update_note_artifacts("abc123", transcript_file="../outside.md")
        self.assertEqual(await self.ids("量子纠错"), [])
        self.assertEqual(await self.ids("光学芯片"), ["abc123"])

    async def test_restored_task_returns_actual_download_filenames(self):
        transcript, summary = await self.make_note()
        for task_id in ("abc123", "uuid-abc123"):
            result = await task_routes.get_task_status(task_id)
            self.assertEqual(result["transcript_filename"], transcript)
            self.assertEqual(result["summary_filename"], summary)
            self.assertIn("量子纠错", result["script"])
            self.assertIn("光学芯片", result["summary"])

    async def test_missing_artifact_does_not_invent_download(self):
        transcript, _ = await self.make_note()
        (self.root / transcript).unlink()
        result = await task_routes.get_task_status("abc123")
        self.assertNotIn("transcript_filename", result)
        self.assertNotIn("script", result)

    async def test_content_route_rejects_sibling_directory_symlink(self):
        from fastapi import HTTPException
        with TemporaryDirectory(prefix=self.root.name) as outside:
            target = Path(outside) / "outside.md"
            target.write_text("private external data", encoding="utf-8")
            link = self.root / "summary_demo_abc123.md"
            try:
                link.symlink_to(target)
            except OSError as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows runner does not grant symlink creation privileges")
                raise
            with self.assertRaises(HTTPException) as raised:
                await task_routes.get_task_content("abc123")
            self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
