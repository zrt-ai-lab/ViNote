"""Search-session persistence uses isolated SQLite databases, never user data."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid

from backend.db import connection, schema
from backend.services import search_session_repository as repository


class SearchSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for target, name, value in (
            (connection, "DB_PATH", self.root / "sessions.db"),
            (schema, "DB_PATH", self.root / "sessions.db"),
            (schema, "TEMP_DIR", self.root),
        ):
            mocked = patch.object(target, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        await schema.init_db()

    async def test_create_reuses_random_runtime_identity_across_connections(self):
        self.assertIsNone(await repository.get("browser-session"))
        created = await repository.get_or_create("browser-session")
        self.assertEqual(created["session_id"], "browser-session")
        self.assertEqual(uuid.UUID(created["runtime_session_id"]).version, 4)
        self.assertNotEqual(created["runtime_session_id"], created["session_id"])
        self.assertEqual(created["messages"], [])
        self.assertEqual(created["videos"], [])
        self.assertTrue(created["updated_at"])
        self.assertEqual(await repository.get_or_create("browser-session"), created)
        self.assertEqual(await repository.get("browser-session"), created)

    async def test_save_creates_and_persists_display_history(self):
        messages = [{"role": "user", "content": "搜索 Python 视频"},
                    {"role": "assistant", "content": "找到了一个视频。"}]
        videos = [{"title": "Python 入门", "url": "https://example.com/video", "platform": "other"}]
        saved = await repository.save("new-session", messages, videos)
        self.assertEqual(saved["messages"], messages)
        self.assertEqual(saved["videos"], videos)
        self.assertEqual(await repository.get("new-session"), saved)
        updated = await repository.save("new-session", messages[:1], [])
        self.assertEqual(updated["runtime_session_id"], saved["runtime_session_id"])

    async def test_reset_clears_messages_and_video_indexes_and_rotates_runtime(self):
        saved = await repository.save("reset-me", [{"role": "user", "content": "old"}],
                                      [{"title": "old", "url": "https://example.com/old"}])
        reset = await repository.reset("reset-me")
        self.assertNotEqual(reset["runtime_session_id"], saved["runtime_session_id"])
        self.assertEqual(reset["messages"], [])
        self.assertEqual(reset["videos"], [])
        self.assertEqual(await repository.get("reset-me"), reset)
        self.assertNotEqual((await repository.reset("reset-me"))["runtime_session_id"],
                            reset["runtime_session_id"])

    async def test_reset_can_create_a_new_empty_session(self):
        reset = await repository.reset("missing-session")
        self.assertEqual(reset["messages"], [])
        self.assertEqual(reset["videos"], [])
        self.assertEqual(await repository.get("missing-session"), reset)

    async def test_concurrent_creation_has_one_persisted_runtime_identity(self):
        sessions = await asyncio.gather(*(repository.get_or_create("shared") for _ in range(8)))
        self.assertEqual(len({session["runtime_session_id"] for session in sessions}), 1)

    async def test_invalid_session_ids_are_rejected_by_every_operation(self):
        for session_id in ("", "a" * 129, "a/b", "../path", "中文", "id\n", "a b", "x'; DROP TABLE notes;--", None, 1):
            for operation in (repository.get, repository.get_or_create, repository.reset):
                with self.subTest(session_id=session_id, operation=operation.__name__), self.assertRaises(ValueError):
                    await operation(session_id)
            with self.subTest(session_id=session_id, operation="save"), self.assertRaises(ValueError):
                await repository.save(session_id, [], [])
        for session_id in ("a", "A0_-", "a" * 128):
            self.assertEqual((await repository.get_or_create(session_id))["session_id"], session_id)

    async def test_only_user_assistant_text_and_video_display_fields_are_stored(self):
        saved = await repository.save("filtered", [
            {"role": "system", "content": "system marker"},
            {"role": "tool", "content": "tool marker"},
            {"role": "user", "content": "Search", "api_key": "example-key"},
            {"role": "assistant", "content": "Found", "tool_calls": [{"internal": True}]},
            {"role": "assistant", "content": None},
            "not a message",
        ], [{"title": "Fixture", "url": "https://example.com/video", "platform": "other",
             "credential": "example-key", "config": {"api_key": "example-key"},
             "isStreaming": True, "description": "internal marker"}])
        self.assertEqual(saved["messages"], [{"role": "user", "content": "Search"},
                                              {"role": "assistant", "content": "Found"}])
        self.assertEqual(saved["videos"], [{"title": "Fixture", "url": "https://example.com/video", "platform": "other"}])
        async with connection.get_db() as db:
            row = await (await db.execute(
                "SELECT messages_json, videos_json FROM search_agent_sessions WHERE session_id = ?", ("filtered",),
            )).fetchone()
        serialized = " ".join(row)
        for marker in ("system marker", "tool marker", "example-key", "internal marker", "tool_calls", "isStreaming"):
            self.assertNotIn(marker, serialized)

    async def test_latest_forty_messages_are_kept_without_mutating_inputs(self):
        messages = [{"role": "user", "content": f"turn-{index}"} for index in range(55)]
        original = json.dumps(messages)
        saved = await repository.save("recent", messages, [])
        self.assertEqual(saved["messages"], messages[-repository.MAX_MESSAGES:])
        self.assertEqual(json.dumps(messages), original)

    async def test_message_and_total_history_character_budgets_are_enforced(self):
        messages = [{"role": "user", "content": f"turn-{index}:" + "文" * 20_000} for index in range(50)]
        saved = await repository.save("bounded", messages, [])
        self.assertLessEqual(len(saved["messages"]), repository.MAX_MESSAGES)
        self.assertLessEqual(sum(len(message["content"]) for message in saved["messages"]), repository.MAX_HISTORY_CHARS)
        self.assertTrue(all(len(message["content"]) <= repository.MAX_MESSAGE_CHARS for message in saved["messages"]))
        self.assertTrue(saved["messages"][-1]["content"].startswith("turn-49:"))

    async def test_video_count_fields_and_order_are_bounded(self):
        videos = [{"title": f"video-{index}", "url": f"https://example.com/{index}",
                   "author": "a" * 1000, "nested": {"large": "ignored"}} for index in range(120)]
        saved = await repository.save("videos", [], videos)
        self.assertEqual(len(saved["videos"]), repository.MAX_VIDEOS)
        self.assertEqual(saved["videos"][0]["title"], "video-0")
        self.assertEqual(saved["videos"][-1]["title"], "video-99")
        self.assertEqual(len(saved["videos"][0]["author"]), repository.VIDEO_FIELD_LIMITS["author"])
        self.assertNotIn("nested", saved["videos"][0])

    async def test_invalid_or_oversized_records_do_not_replace_saved_data(self):
        original = await repository.save("keep", [{"role": "user", "content": "retained"}], [])
        for messages, videos in ((None, []), ([], {})):
            with self.assertRaises(ValueError):
                await repository.save("keep", messages, videos)
        control_text = "\x00" * 3000
        oversized_videos = [{field: control_text for field in repository.VIDEO_FIELD_LIMITS}
                            for _ in range(repository.MAX_VIDEOS)]
        with self.assertRaisesRegex(ValueError, "storage limit"):
            await repository.save("keep", [], oversized_videos)
        self.assertEqual(await repository.get("keep"), original)

    async def test_sql_content_is_parameterized_and_schema_initialization_preserves_existing_data(self):
        content = "video'); DROP TABLE notes; --"
        async with connection.get_db() as db:
            await db.execute("INSERT INTO notes (short_id, title) VALUES (?, ?)", ("old-note", "Existing note"))
            await db.commit()
        saved = await repository.save("quotes", [{"role": "user", "content": content}], [])
        await schema.init_db()
        self.assertEqual(await repository.get("quotes"), saved)
        async with connection.get_db() as db:
            row = await (await db.execute("SELECT title FROM notes WHERE short_id = ?", ("old-note",))).fetchone()
        self.assertEqual(row[0], "Existing note")


if __name__ == "__main__":
    unittest.main()
