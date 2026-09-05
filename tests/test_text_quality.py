"""离线回归：正文完整性、摘要上下文预算、卡片全文节选。"""
import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.utils.text_processor import (
    enforce_paragraph_length, representative_excerpt, smart_chunk_text,
)


def load_offline_service(filename):
    """加载真实服务代码，仅隔离会读取本地配置的客户端依赖。"""
    config = types.ModuleType("backend.config.ai_config")
    config.get_openai_config = lambda: SimpleNamespace(model="offline-test")
    client = types.ModuleType("backend.core.ai_client")
    client.get_openai_client = lambda: None
    path = Path(__file__).resolve().parents[1] / "backend" / "services" / filename
    spec = importlib.util.spec_from_file_location(f"offline_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"backend.config.ai_config": config, "backend.core.ai_client": client}):
        spec.loader.exec_module(module)
    return module


def non_whitespace(text):
    return re.sub(r"\s+", "", text)


class TextIntegrityTests(unittest.TestCase):
    def test_chinese_paragraph_without_spaces_retains_every_character(self):
        text = "这是需要完整保留的课程知识点。" * 40
        output = enforce_paragraph_length(text)
        self.assertEqual(non_whitespace(output), non_whitespace(text))
        self.assertTrue(all(len(part) <= 400 for part in output.split("\n\n")))

    def test_short_intro_does_not_mask_deleted_long_paragraph(self):
        text = "开场说明。\n\n" + "正文细节不能丢失。" * 100 + "最后结论。"
        output = enforce_paragraph_length(text)
        self.assertEqual(non_whitespace(output), non_whitespace(text))
        self.assertIn("最后结论。", output)

    def test_english_final_sentence_and_punctuation_are_preserved(self):
        text = "First fact contains exact detail! " * 30 + "Final fact must be preserved?"
        output = enforce_paragraph_length(text)
        self.assertEqual(non_whitespace(output), non_whitespace(text))
        self.assertTrue(output.endswith("Final fact must be preserved?"))

    def test_unpunctuated_and_multilingual_chunks_are_bounded(self):
        for text in ("文" * 12001, "alpha: 3.14! 中文没有空格。終わり？" * 1000):
            for paragraphs in (True, False):
                with self.subTest(paragraphs=paragraphs, size=len(text)):
                    chunks = smart_chunk_text(text, 4000, paragraphs)
                    self.assertTrue(all(0 < len(chunk) <= 4000 for chunk in chunks))
                    self.assertEqual(non_whitespace("".join(chunks)), non_whitespace(text))

    def test_invalid_sizes_do_not_loop(self):
        for function in (enforce_paragraph_length, smart_chunk_text, representative_excerpt):
            with self.assertRaises(ValueError):
                function("content", 0)

    def test_representative_excerpt_covers_beginning_middle_end(self):
        text = "开头知识点" + "甲" * 15000 + "中间知识点" + "乙" * 15000 + "结尾知识点"
        excerpt = representative_excerpt(text, 8000)
        self.assertLessEqual(len(excerpt), 8000)
        for marker in ("开头知识点", "中间知识点", "结尾知识点"):
            self.assertIn(marker, excerpt)
        self.assertEqual(representative_excerpt("完整短文", 8000), "完整短文")


class SummaryBudgetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module = load_offline_service("content_summarizer.py")
        self.service = self.module.ContentSummarizer()

    async def test_large_summary_uses_multiple_bounded_merge_requests(self):
        requests = []

        def create(**kwargs):
            prompt = kwargs["messages"][1]["content"]
            requests.append(kwargs["messages"])
            markers = re.findall(r"唯一观点\d+", prompt)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="；".join(markers)))])

        self.service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        pieces = [f"唯一观点{i} " + "知识" * 500 for i in range(80)]
        result = await self.service._integrate_hierarchical_summaries(pieces, "zh")
        self.assertGreater(len(requests), 2)
        # 10000 字资料预算之外，提示词自身为固定长度。
        self.assertTrue(all(sum(len(m["content"]) for m in request) < 12000 for request in requests))
        for i in range(80):
            self.assertIn(f"唯一观点{i}", result)

    async def test_merge_failure_keeps_all_parts_without_unbounded_retry(self):
        requests = []

        def fail(**kwargs):
            requests.append(kwargs)
            raise RuntimeError("offline upstream failure")

        self.service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
        pieces = [f"第{i}段证据" + "文" * 4000 for i in range(12)]
        result = await self.service._integrate_hierarchical_summaries(pieces, "zh")
        self.assertLess(len(requests), 20)
        self.assertTrue(self.service.warnings)
        for i in range(12):
            self.assertIn(f"第{i}段证据", result)

    def test_summarizer_uses_bounded_lossless_chunks(self):
        text = "文" * 12000 + "最终结论"
        chunks = self.service._smart_chunk_text(text, 4000)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(chunk) <= 4000 for chunk in chunks))


class CardCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_card_prompt_includes_middle_and_end(self):
        module = load_offline_service("card_generator.py")
        service = module.CardGenerator()
        requests = []

        def create(**kwargs):
            requests.append(kwargs)
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=
                '{"term":"测试概念","definition":"定义","example":"例子","related":[]}\n'
            ))])])

        service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        text = "开头知识点" + "甲" * 15000 + "中间知识点" + "乙" * 15000 + "结尾知识点"
        events = [event async for event in service.generate_cards_stream(text, source="notes", style="concept")]
        self.assertEqual(events[-1], {"type": "done"})
        prompt = requests[0]["messages"][1]["content"]
        self.assertLess(len(prompt), 8200)
        for marker in ("开头知识点", "中间知识点", "结尾知识点"):
            self.assertIn(marker, prompt)


if __name__ == "__main__":
    unittest.main()
