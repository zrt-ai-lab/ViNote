"""Agent-generated files enter the real SQLite library and full-text index."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from backend.db import connection, schema
from backend.services import note_repository, note_search
from backend.services import video_search_agent as agent_module


class AgentNoteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for target, name, value in (
            (connection, "DB_PATH", self.root / "notes.db"),
            (schema, "DB_PATH", self.root / "notes.db"),
            (schema, "TEMP_DIR", self.root),
            (note_search, "TEMP_DIR", self.root),
            (agent_module, "TEMP_DIR", self.root),
        ):
            mocked = patch.object(target, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        await schema.init_db()
        self.short_id = "1234567890abcdef1234567890abcdef"
        self.url = "https://www.youtube.com/watch?v=fixture-note"
        self.result = {
            "short_id": self.short_id, "safe_title": "fixture",
            "video_title": "Fixture video", "optimized_transcript": "Transcript marker",
            "raw_transcript": "原始转录独特检索词", "summary": "Summary marker",
            "detected_language": "en", "summary_language": "zh", "warnings": [], "files": {},
        }
        for kind, prefix, content in (
            ("transcript", "transcript", "Transcript marker"),
            ("raw_transcript", "raw", "原始转录独特检索词"),
            ("summary", "summary", "Summary marker"),
        ):
            filename = f"{prefix}_fixture_{self.short_id}.md"
            path = self.root / filename
            path.write_text(content, encoding="utf-8")
            self.result["files"][kind + "_filename"] = filename
            self.result["files"][kind + "_path"] = path
        self.generator = SimpleNamespace(generate_note=AsyncMock(return_value=self.result))
        factory = patch.object(agent_module, "NoteGenerator", return_value=self.generator)
        factory.start()
        self.addCleanup(factory.stop)
        with patch.object(
            agent_module, "HarnessRuntime",
        ), patch.object(agent_module, "get_openai_config", return_value=SimpleNamespace(is_configured=True)):
            self.agent = agent_module.VideoSearchAgent(SimpleNamespace())
        self.addAsyncCleanup(self.agent.aclose)

    async def test_concurrent_notes_have_independent_generator_state(self):
        created = []
        ready = asyncio.Event()
        root, result = self.root, self.result
        class Generator:
            def __init__(self):
                self.index = len(created) + 1
                self.warnings = []
                created.append(self)
            async def generate_note(self, **kwargs):
                if self.index == 1:
                    self.warnings.append('First request warning')
                if len(created) == 2:
                    ready.set()
                await ready.wait()
                short_id = str(self.index) * 32
                files = {}
                for kind, prefix in (('transcript', 'transcript'), ('summary', 'summary'), ('raw_transcript', 'raw')):
                    filename = f'{prefix}_fixture_{short_id}.md'
                    (root / filename).write_text('Generated request content')
                    files[kind + '_filename'] = filename
                return {**result, 'short_id': short_id, 'files': files, 'warnings': self.warnings}
        with patch.object(agent_module, 'NoteGenerator', Generator):
            first, second = await asyncio.wait_for(asyncio.gather(self.collect('first'), self.collect('second')), 3)
        self.assertEqual(len(created), 2)
        first_note = next(event['data'] for event in first if event['type'] == 'notes_complete')
        second_note = next(event['data'] for event in second if event['type'] == 'notes_complete')
        self.assertEqual(first_note['warnings'], ['First request warning'])
        self.assertEqual(second_note['warnings'], [])
        self.assertTrue(first_note['persisted'] and second_note['persisted'])

    async def collect(self, generation_id="fixture-generation"):
        return [event async for event in self.agent.generate_notes_for_video(
            self.url, self.root, generation_id=generation_id,
        )]

    async def test_complete_event_follows_real_library_and_fulltext_persistence(self):
        stream = self.agent.generate_notes_for_video(self.url, self.root, generation_id="saved-generation")
        try:
            event = await anext(stream)
            self.assertEqual(event["type"], "notes_complete")
            self.assertTrue(event["data"]["persisted"])
            saved = await note_repository.get_note(self.short_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["id"], event["data"]["note_id"])
            self.assertEqual(saved["task_id"], "saved-generation")
            self.assertEqual(saved["url"], self.url)
            self.assertEqual(saved["safe_title"], "fixture")
            self.assertEqual(saved["source"], "url")
            self.assertEqual(saved["status"], "completed")
            self.assertTrue(saved["completed_at"])
            self.assertTrue(saved["has_summary"])
            self.assertTrue(saved["has_transcript"])
            for field, artifact in (("summary_file", "summary"), ("transcript_file", "transcript"),
                                    ("raw_transcript_file", "raw_transcript")):
                self.assertEqual(saved[field], self.result["files"][artifact + "_filename"])
            matches = await note_repository.list_notes(search="独特检索词")
            self.assertEqual(matches["total"], 1)
            self.assertEqual(matches["tasks"][0]["task_id"], self.short_id)
            async with connection.get_db() as db:
                row = await (await db.execute("SELECT body FROM note_search WHERE note_id = ?", (saved["id"],))).fetchone()
            self.assertIn("原始转录独特检索词", row[0])
        finally:
            await stream.aclose()
        self.assertEqual(self.agent.active_generation_tasks, {})
        self.assertEqual(self.agent.generation_cancel_flags, {})

    async def test_degraded_generation_warnings_reach_database_and_ui(self):
        self.result["warnings"] = ["LLM 整理失败，完整笔记使用基础清理", "LLM 整理失败，完整笔记使用基础清理"]
        events = await self.collect()
        complete = next(event["data"] for event in events if event["type"] == "notes_complete")
        self.assertTrue(complete["persisted"])
        self.assertEqual(complete["warnings"], ["LLM 整理失败，完整笔记使用基础清理"])
        self.assertEqual((await note_repository.get_note(self.short_id))["warnings"], complete["warnings"])

    async def test_optional_mindmap_and_translation_artifacts_are_saved(self):
        for kind in ("mindmap", "translation"):
            filename = f"{kind}_fixture_{self.short_id}.md"
            (self.root / filename).write_text(kind + " content", encoding="utf-8")
            self.result["files"][kind + "_filename"] = filename
            self.result[kind] = kind + " content"
        events = await self.collect()
        complete = next(event["data"] for event in events if event["type"] == "notes_complete")
        saved = await note_repository.get_note(self.short_id)
        self.assertEqual(saved["mindmap_file"], self.result["files"]["mindmap_filename"])
        self.assertEqual(saved["translation_file"], self.result["files"]["translation_filename"])
        self.assertEqual(complete["translation"], "translation content")

    async def test_database_failure_preserves_downloads_but_never_claims_saved(self):
        private_detail = "synthetic-password database-internal-url"
        with patch.object(agent_module, "save_note", AsyncMock(side_effect=RuntimeError(private_detail))), self.assertLogs(
            agent_module.__name__, level="WARNING",
        ) as logs:
            events = await self.collect()
        self.assertEqual([event["type"] for event in events], ["notes_complete", "error"])
        self.assertFalse(events[0]["data"]["persisted"])
        self.assertIn("未能保存到笔记库", events[0]["data"]["warnings"][-1])
        self.assertNotIn(private_detail, str(events) + str(logs.output))
        self.assertEqual(events[0]["data"]["files"]["summary_filename"], self.result["files"]["summary_filename"])
        self.assertTrue(self.result["files"]["summary_path"].is_file())
        self.assertIsNone(await note_repository.get_note(self.short_id))

    async def test_missing_or_mismatched_artifacts_do_not_create_library_entries(self):
        for filename in ("../outside.md", "other-note.md", self.result["files"]["summary_filename"]):
            with self.subTest(filename=filename):
                self.result["files"]["summary_filename"] = filename
                if filename.startswith("summary_"):
                    self.result["files"]["summary_path"].unlink()
                events = await self.collect()
                self.assertEqual([event["type"] for event in events], ["error"])
                self.assertIsNone(await note_repository.get_note(self.short_id))

    async def test_completed_generator_cannot_be_reported_cancelled_before_delivery(self):
        async def generate(**kwargs):
            await kwargs["progress_callback"](100, "生成完成")
            return self.result

        self.generator.generate_note.side_effect = generate
        stream = self.agent.generate_notes_for_video(self.url, self.root, generation_id="already-finished")
        try:
            self.assertEqual((await anext(stream))["type"], "progress")
            self.assertTrue(self.agent.active_generation_tasks["already-finished"].done())
            self.assertFalse(self.agent.cancel_generation("already-finished"))
            remaining = [event async for event in stream]
            self.assertEqual(remaining[-1]["type"], "notes_complete")
            self.assertTrue(remaining[-1]["data"]["persisted"])
        finally:
            await stream.aclose()

    async def test_closing_unfinished_stream_cancels_and_awaits_owned_generation(self):
        stopped = asyncio.Event()

        async def generate(**kwargs):
            try:
                await kwargs["progress_callback"](10, "处理中")
                await asyncio.Event().wait()
            finally:
                stopped.set()

        self.generator.generate_note.side_effect = generate
        stream = self.agent.generate_notes_for_video(self.url, self.root, generation_id="unfinished")
        self.assertEqual((await anext(stream))["type"], "progress")
        await asyncio.wait_for(stream.aclose(), timeout=1)
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.agent.active_generation_tasks, {})
        self.assertEqual(self.agent.generation_cancel_flags, {})
        self.assertIsNone(await note_repository.get_note(self.short_id))


if __name__ == "__main__":
    unittest.main()
