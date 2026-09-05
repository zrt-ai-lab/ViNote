"""Storage and regeneration regressions, using temporary SQLite/Markdown only."""
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from backend.db import connection, schema
from backend.core import state
from backend.routers import downloads, storage
from backend.services import note_regenerator as regeneration
from backend.services import note_repository as repository
from backend.services import note_search
from backend.utils.tool_arguments import parse_tool_arguments


class ToolArgumentTests(unittest.TestCase):
    def test_json_objects_are_parsed_without_python_evaluation(self):
        self.assertEqual(parse_tool_arguments('{"query":"demo", "page":1}'), {"query": "demo", "page": 1})

    def test_expression_is_rejected_without_execution(self):
        with patch("builtins.print") as execute_marker:
            with self.assertRaises(ValueError):
                parse_tool_arguments("__import__('builtins').print('executed')")
            execute_marker.assert_not_called()

    def test_non_object_json_is_rejected(self):
        for value in ("null", "[]", '"query"', "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_tool_arguments(value)


class StorageRegenerationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.patches = [
            patch.object(connection, "DB_PATH", self.root / "notes.db"),
            patch.object(schema, "TEMP_DIR", self.root),
            patch.object(storage, "TEMP_DIR", self.root),
            patch.object(storage, "tasks", {}),
            patch.object(storage, "active_tasks", {}),
            patch.object(storage, "save_tasks", Mock()),
            patch.object(regeneration, "TEMP_DIR", self.root),
            patch.object(note_search, "TEMP_DIR", self.root),
        ]
        for mocked in self.patches:
            mocked.start()
            self.addCleanup(mocked.stop)
        await schema.init_db()
        self.summarizer = SimpleNamespace(
            warnings=[],
            summarize=AsyncMock(return_value="new summary"),
            generate_mindmap=AsyncMock(return_value="# new mindmap"),
        )
        self.optimizer = SimpleNamespace(
            warnings=[], optimize_transcript=AsyncMock(return_value="new transcript")
        )
        for mocked in [
            patch.object(regeneration, "ContentSummarizer", return_value=self.summarizer),
            patch.object(regeneration, "TextOptimizer", return_value=self.optimizer),
        ]:
            mocked.start()
            self.addCleanup(mocked.stop)

    async def make_note(self, short_id="abcdef", ages=(30, 30, 30)):
        files = {}
        for kind, age in zip(("transcript", "summary", "mindmap"), ages):
            path = self.root / f"{kind}_demo_{short_id}.md"
            path.write_text(f"old {kind}", encoding="utf-8")
            old_time = time.time() - age * 86400
            os.utime(path, (old_time, old_time))
            files[f"{kind}_file"] = path.name
        await repository.save_note(short_id, title="Demo", safe_title="demo", **files)
        return {kind: self.root / filename for kind, filename in files.items()}

    async def cleanup_notes(self, days=7):
        return await storage.cleanup_storage(storage.CleanupRequest(
            clean_audio=False, clean_all_notes=True, older_than_days=days,
        ))

    async def test_age_cleanup_preserves_recent_note_and_its_relationships(self):
        old = await self.make_note("abcdef")
        recent = await self.make_note("bcdefa", (1, 1, 1))
        await repository.set_note_tags("bcdefa", ["keep"])
        result = await self.cleanup_notes()
        self.assertEqual(len(result["deleted_files"]), 3)
        self.assertTrue(all(not path.exists() for path in old.values()))
        self.assertTrue(all(path.exists() for path in recent.values()))
        self.assertIsNone(await repository.get_note("abcdef"))
        note = await repository.get_note("bcdefa")
        self.assertEqual(note["tags"], ["keep"])
        self.assertEqual(result["skipped_note_ids"], ["bcdefa"])

    async def test_markdown_download_rejects_sibling_prefix_symlink(self):
        allowed, outside = self.root / "notes", self.root / "notes-private"
        allowed.mkdir()
        outside.mkdir()
        target = outside / "demo.md"
        target.write_text("outside marker", encoding="utf-8")
        try:
            (allowed / "demo.md").symlink_to(target)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows runner does not grant symlink creation privileges")
            raise
        with patch.object(state, "TEMP_DIR", allowed), patch.object(downloads, "TEMP_DIR", allowed):
            with self.assertRaises(HTTPException) as raised:
                await downloads.download_file("demo.md")
        self.assertIn(raised.exception.status_code, (400, 403))

    async def test_markdown_download_keeps_normal_files_available(self):
        path = self.root / "demo.md"
        path.write_text("demo content", encoding="utf-8")
        with patch.object(state, "TEMP_DIR", self.root), patch.object(downloads, "TEMP_DIR", self.root):
            response = await downloads.download_file("demo.md")
        self.assertEqual(Path(response.path), path)

    async def test_video_download_rejects_outside_service_path(self):
        target = self.root / "outside.mp4"
        target.write_bytes(b"demo")
        service = SimpleNamespace(get_file_path=lambda _: str(target))
        with patch.object(downloads, "TEMP_DIR", self.root), patch.object(downloads, "get_video_download_service", return_value=service):
            with self.assertRaises(HTTPException) as raised:
                await downloads.get_download_file("demo-id")
        self.assertEqual(raised.exception.status_code, 403)

    async def test_video_download_keeps_normal_files_available(self):
        directory = self.root / "downloads"
        directory.mkdir()
        target = directory / "demo.mp4"
        target.write_bytes(b"demo")
        service = SimpleNamespace(get_file_path=lambda _: str(target))
        with patch.object(downloads, "TEMP_DIR", self.root), patch.object(downloads, "get_video_download_service", return_value=service):
            response = await downloads.get_download_file("demo-id")
        self.assertEqual(Path(response.path), target)

    async def test_one_recent_artifact_preserves_entire_note(self):
        files = await self.make_note(ages=(30, 1, 30))
        result = await self.cleanup_notes()
        self.assertEqual(result["deleted_count"], 0)
        self.assertTrue(all(path.exists() for path in files.values()))
        self.assertIsNotNone(await repository.get_note("abcdef"))

    async def test_file_delete_failure_restores_group_and_preserves_record(self):
        files = await self.make_note()
        previous = {path: path.read_bytes() for path in files.values()}
        real_unlink = Path.unlink

        def fail_transcript(path, *args, **kwargs):
            if path == files["transcript_file"]:
                raise PermissionError("simulated read-only artifact")
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", fail_transcript), self.assertLogs(storage.logger, level="ERROR"):
            result = await self.cleanup_notes()
        self.assertEqual(result["failed_note_ids"], ["abcdef"])
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual({path: path.read_bytes() for path in files.values()}, previous)
        self.assertIsNotNone(await repository.get_note("abcdef"))

    async def test_database_delete_failure_restores_files(self):
        files = await self.make_note()
        with patch.object(storage, "delete_note", AsyncMock(side_effect=OSError("database unavailable"))), self.assertLogs(storage.logger, level="ERROR"):
            with self.assertRaises(HTTPException) as raised:
                await storage.delete_task_files("abcdef")
        self.assertEqual(raised.exception.status_code, 500)
        self.assertTrue(all(path.exists() for path in files.values()))
        self.assertIsNotNone(await repository.get_note("abcdef"))

    async def test_running_task_blocks_bulk_note_cleanup(self):
        files = await self.make_note()
        storage.active_tasks["running-task"] = object()
        with self.assertRaises(HTTPException) as raised:
            await self.cleanup_notes(0)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertTrue(all(path.exists() for path in files.values()))

    async def test_missing_artifact_does_not_select_recent_row(self):
        await repository.save_note("abcdef", title="Recent missing artifact")
        result = await self.cleanup_notes()
        self.assertEqual(result["deleted_count"], 0)
        self.assertIsNotNone(await repository.get_note("abcdef"))

    async def test_full_cleanup_also_removes_missing_artifact_rows(self):
        await repository.save_note("abcdef", title="Missing artifact")
        result = await self.cleanup_notes(0)
        self.assertEqual(result["failed_note_ids"], [])
        self.assertIsNone(await repository.get_note("abcdef"))

    async def test_partial_cleanup_continues_with_other_notes(self):
        failed = await self.make_note("abcdef")
        succeeded = await self.make_note("bcdefa")
        real_delete = storage.delete_note

        async def fail_one(short_id):
            if short_id == "abcdef":
                raise OSError("simulated per-note database failure")
            return await real_delete(short_id)

        with patch.object(storage, "delete_note", side_effect=fail_one), self.assertLogs(storage.logger, level="ERROR"):
            result = await self.cleanup_notes()
        self.assertEqual(result["failed_note_ids"], ["abcdef"])
        self.assertEqual(result["deleted_count"], 3)
        self.assertTrue(all(path.exists() for path in failed.values()))
        self.assertTrue(all(not path.exists() for path in succeeded.values()))
        self.assertIsNotNone(await repository.get_note("abcdef"))
        self.assertIsNone(await repository.get_note("bcdefa"))

    async def test_generation_failure_does_not_overwrite_any_artifact(self):
        files = await self.make_note()
        self.summarizer.generate_mindmap.side_effect = RuntimeError("upstream unavailable")
        with self.assertRaises(RuntimeError):
            await regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh")
        self.assertEqual(files["summary_file"].read_text(), "old summary")
        self.assertEqual(files["mindmap_file"].read_text(), "old mindmap")

    async def test_degraded_summary_does_not_replace_saved_content(self):
        files = await self.make_note()
        self.summarizer.warnings.append("fallback output")
        with self.assertRaises(ValueError):
            await regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh")
        self.assertEqual(files["summary_file"].read_text(), "old summary")
        self.summarizer.generate_mindmap.assert_not_awaited()

    async def test_staging_write_failure_keeps_all_originals(self):
        files = await self.make_note()
        writer = regeneration._atomic_write

        def fail_second(path, content):
            if path.name.startswith(files["mindmap_file"].name):
                raise OSError("simulated write failure")
            writer(path, content)

        with patch.object(regeneration, "_atomic_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                await regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh")
        self.assertEqual(files["summary_file"].read_text(), "old summary")
        self.assertEqual(files["mindmap_file"].read_text(), "old mindmap")
        self.assertFalse(list(self.root.glob("*.restore")))

    async def test_replace_failure_rolls_back_previous_replacements(self):
        files = await self.make_note()
        replace = Path.replace

        def fail_install(path, target):
            if path.suffix == ".stage" and target == files["mindmap_file"]:
                raise OSError("simulated replacement failure")
            return replace(path, target)

        with patch.object(Path, "replace", fail_install):
            with self.assertRaises(OSError):
                await regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh")
        self.assertEqual(files["summary_file"].read_text(), "old summary")
        self.assertEqual(files["mindmap_file"].read_text(), "old mindmap")
        self.assertFalse(list(self.root.glob("*.backup")))

    async def test_database_update_failure_rolls_back_all_artifacts(self):
        files = await self.make_note()
        with patch.object(regeneration, "update_note_artifacts", AsyncMock(side_effect=OSError("database unavailable"))):
            with self.assertRaises(OSError):
                await regeneration.regenerate_note("abcdef", ["transcript", "summary", "mindmap"], "zh")
        for kind, path in files.items():
            self.assertEqual(path.read_text(), f"old {kind.removesuffix('_file')}")

    async def test_failed_commit_removes_newly_created_artifact(self):
        files = await self.make_note()
        files["mindmap_file"].unlink()
        await repository.update_note_artifacts("abcdef", mindmap_file=None)
        with patch.object(regeneration, "update_note_artifacts", AsyncMock(return_value=False)):
            with self.assertRaises(ValueError):
                await regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh")
        self.assertEqual(files["summary_file"].read_text(), "old summary")
        self.assertFalse(files["mindmap_file"].exists())
        self.assertIsNone((await repository.get_note("abcdef"))["mindmap_file"])

    async def test_success_replaces_all_requested_artifacts(self):
        files = await self.make_note()
        result = await regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh")
        self.assertEqual(result["updated"], ["mindmap", "summary"])
        self.assertIn("new summary", files["summary_file"].read_text())
        self.assertEqual(files["mindmap_file"].read_text(), "# new mindmap")
        self.assertEqual(files["transcript_file"].read_text(), "old transcript")
        self.assertEqual((await repository.list_notes(search="new summary"))["total"], 1)
        self.assertEqual((await repository.list_notes(search="old summary"))["total"], 0)

    async def test_index_failure_rolls_back_database_index_and_files(self):
        files = await self.make_note()
        refresh = repository.refresh_note_search

        async def fail_after_index_write(db, short_id):
            await refresh(db, short_id)
            raise OSError("simulated failure before transaction commit")

        with patch.object(repository, "refresh_note_search", side_effect=fail_after_index_write):
            with self.assertRaises(OSError):
                await regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh")
        self.assertEqual(files["summary_file"].read_text(), "old summary")
        self.assertEqual((await repository.list_notes(search="new summary"))["total"], 0)
        self.assertEqual((await repository.list_notes(search="old summary"))["total"], 1)

    async def test_delete_waits_for_regeneration_lock(self):
        files = await self.make_note()
        started, release = asyncio.Event(), asyncio.Event()

        async def generate(*args):
            started.set()
            await release.wait()
            return "new summary"

        self.summarizer.summarize.side_effect = generate
        generate_task = asyncio.create_task(regeneration.regenerate_note("abcdef", ["summary"], "zh"))
        await started.wait()
        delete_task = asyncio.create_task(storage.delete_task_files("abcdef"))
        await asyncio.sleep(0)
        self.assertFalse(delete_task.done())
        release.set()
        await asyncio.gather(generate_task, delete_task)
        self.assertIsNone(await repository.get_note("abcdef"))
        self.assertTrue(all(not path.exists() for path in files.values()))

    async def test_cancellation_during_generation_preserves_originals(self):
        files = await self.make_note()
        started = asyncio.Event()

        async def generate(*args):
            started.set()
            await asyncio.Event().wait()

        self.summarizer.summarize.side_effect = generate
        task = asyncio.create_task(regeneration.regenerate_note("abcdef", ["summary"], "zh"))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(files["summary_file"].read_text(), "old summary")

    async def test_cancellation_during_commit_waits_until_consistent(self):
        files = await self.make_note()
        started, release = asyncio.Event(), asyncio.Event()
        updater = regeneration.update_note_artifacts

        async def delayed_update(*args, **kwargs):
            started.set()
            await release.wait()
            return await updater(*args, **kwargs)

        with patch.object(regeneration, "update_note_artifacts", side_effect=delayed_update):
            task = asyncio.create_task(regeneration.regenerate_note("abcdef", ["summary", "mindmap"], "zh"))
            await started.wait()
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIn("new summary", files["summary_file"].read_text())
        self.assertEqual(files["mindmap_file"].read_text(), "# new mindmap")


if __name__ == "__main__":
    unittest.main()
