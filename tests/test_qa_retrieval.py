"""离线回归：长视频、多来源问答覆盖以及来源引用/历史预算。"""
import importlib.util
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.services.qa_retrieval import (
    MAX_CONTEXT_CHARS, MAX_HISTORY_CHARS,
    bounded_history, build_qa_context, retrieval_query,
)


class RetrievalTests(unittest.TestCase):
    def test_five_sources_remain_visible_when_first_exceeds_old_limit(self):
        sources = [{
            "short_id": "first", "title": "第一篇",
            "content": "无关背景材料。" * 12000 + "量子回滚窗口是三十秒。",
        }]
        sources += [{
            "short_id": f"note{index}", "title": f"课程{index}",
            "content": f"来源{index}的量子回滚证据与独有答案。",
        } for index in range(2, 6)]
        context = build_qa_context(sources, "量子回滚窗口是多少？")
        self.assertLessEqual(len(context), MAX_CONTEXT_CHARS)
        self.assertIn("量子回滚窗口是三十秒。", context)
        for index in range(1, 6):
            self.assertIn(f"## 来源{index}：", context)
            self.assertRegex(context, rf"\[来源{index}·片段\d+\]")
        for index in range(2, 6):
            self.assertIn(f"来源{index}的量子回滚证据与独有答案。", context)

    def test_no_keyword_match_samples_beginning_middle_and_end(self):
        text = "开头事实。" + "甲" * 16000 + "中间事实。" + "乙" * 16000 + "结尾事实。"
        context = build_qa_context([{"title": "课程", "content": text}], "总结")
        for marker in ("开头事实。", "中间事实。", "结尾事实。"):
            self.assertIn(marker, context)
        self.assertLessEqual(len(context), MAX_CONTEXT_CHARS)

    def test_specific_english_question_finds_a_late_passage(self):
        text = "General background material. " * 5000 + "The rollback deadline is exactly 47 seconds."
        context = build_qa_context([{"title": "Operations", "content": text}], "What is the rollback deadline?")
        self.assertIn("The rollback deadline is exactly 47 seconds.", context)

    def test_titles_and_labels_count_against_budget(self):
        sources = [{"title": "标题" * 1000, "short_id": "a" * 64, "content": "正文" * 10000} for _ in range(5)]
        context = build_qa_context(sources, "正文", max_chars=3000)
        self.assertLessEqual(len(context), 3000)
        self.assertEqual(context.count("## 来源"), 5)
        self.assertTrue(all(f"[来源{i}·片段" in context for i in range(1, 6)))

    def test_identical_source_chunks_keep_stable_ids_across_questions(self):
        sources = [{"title": "课程", "content": "开头证据。" + "甲" * 9000 + "最后证据。"}]
        first = build_qa_context(sources, "最后证据")
        second = build_qa_context(sources, "开头证据")
        self.assertEqual(set(re.findall(r"来源1·片段\d+", first)), set(re.findall(r"来源1·片段\d+", second)))
        self.assertNotRegex(first, r"\d{2}:\d{2}")

    def test_history_is_bounded_and_uses_only_conversation_roles(self):
        history = [{"role": "assistant" if i % 2 else "user", "content": f"turn{i}:" + "文" * 15000} for i in range(20)]
        history.append({"role": "system", "content": "不能成为系统指令"})
        selected = bounded_history(history)
        self.assertLessEqual(sum(len(message["content"]) for message in selected), MAX_HISTORY_CHARS)
        self.assertLessEqual(len(selected), 12)
        self.assertTrue(all(message["role"] in {"user", "assistant"} for message in selected))

    def test_followup_query_reuses_user_topic_but_not_prior_answer(self):
        query = retrieval_query("它的时间呢？", [
            {"role": "user", "content": "解释量子回滚"},
            {"role": "assistant", "content": "历史回答不是原文证据"},
        ])
        self.assertIn("量子回滚", query)
        self.assertNotIn("历史回答不是原文证据", query)


class QAServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepared_sources_are_not_retrieved_or_truncated_twice(self):
        config = types.ModuleType("backend.config.ai_config")
        config.get_openai_config = lambda: SimpleNamespace(model="offline-test")
        client_module = types.ModuleType("backend.core.ai_client")
        client_module.get_async_openai_client = lambda: None
        client_module.is_openai_available = lambda: True
        path = Path(__file__).resolve().parents[1] / "backend/services/video_qa_service.py"
        spec = importlib.util.spec_from_file_location("offline_video_qa", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"backend.config.ai_config": config, "backend.core.ai_client": client_module}):
            spec.loader.exec_module(module)
        requests = []

        async def create(**kwargs):
            requests.append(kwargs)

            async def stream():
                for fragment in ("原文结论 [来源5·片", "段8]，未知引用 [来源9", "·片段9]。"):
                    yield SimpleNamespace(choices=[SimpleNamespace(
                        delta=SimpleNamespace(content=fragment), finish_reason=None,
                    )])
            return stream()

        service = module.VideoQAService()
        service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        context = "## 来源5：保留来源\n[来源5·片段8]\n原文结论，时间 03:17。"
        with patch.object(module, "build_qa_context", side_effect=AssertionError("不得重复召回")):
            answer = "".join([part async for part in service.answer_question_stream("结论？", context, prepared_context=True)])
        self.assertIn("[来源5·片段8]", answer)
        self.assertNotIn("来源9", answer)
        self.assertIn(context, requests[0]["messages"][-1]["content"])
        self.assertIn("不编造编号、时间或出处", requests[0]["messages"][0]["content"])

    async def test_session_source_reader_retrieves_late_facts_from_real_files(self):
        """经过路由实际读取路径验证，避免纯召回函数通过但调用方仍截前缀。"""
        state = types.ModuleType("backend.core.state")
        for name, value in {
            "tasks": {}, "active_tasks": {}, "save_tasks": lambda *_: None,
            "broadcast_task_update": AsyncMock(), "get_video_qa_service": lambda: None,
        }.items():
            setattr(state, name, value)
        ingestion = types.ModuleType("backend.services.media_ingestion")
        ingestion.transcribe_local_media = AsyncMock()
        ingestion.transcribe_remote_media = AsyncMock()
        repository = types.ModuleType("backend.services.note_repository")
        repository.get_note = AsyncMock(side_effect=lambda note_id: {"raw_transcript_file": f"{note_id}.md"})
        path = Path(__file__).resolve().parents[1] / "backend/routers/qa.py"
        spec = importlib.util.spec_from_file_location("offline_qa_router", path)
        module = importlib.util.module_from_spec(spec)
        with tempfile.TemporaryDirectory() as directory:
            state.TEMP_DIR = Path(directory)
            (state.TEMP_DIR / "first.md").write_text("背景材料。" * 15000 + "回滚窗口为七秒。", encoding="utf-8")
            (state.TEMP_DIR / "second.md").write_text("第二篇回滚窗口为十秒。", encoding="utf-8")
            with patch.dict(sys.modules, {
                "backend.core.state": state,
                "backend.services.media_ingestion": ingestion,
                "backend.services.note_repository": repository,
            }):
                spec.loader.exec_module(module)
                context = await module._read_session_sources({"sources": [
                    {"short_id": "first", "title": "第一篇", "content_field": "transcript"},
                    {"short_id": "second", "title": "第二篇", "content_field": "transcript"},
                ], "messages": []}, "回滚窗口是多少？")
        self.assertIn("回滚窗口为七秒。", context)
        self.assertIn("第二篇回滚窗口为十秒。", context)
        self.assertLessEqual(len(context), MAX_CONTEXT_CHARS)


if __name__ == "__main__":
    unittest.main()
