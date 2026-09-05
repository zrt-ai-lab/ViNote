"""Optional reasoning effort never changes requests unless explicitly configured."""
import os
from types import SimpleNamespace
from typing import get_args
import unittest
from unittest.mock import patch

from openai.types.shared import ReasoningEffort
from test_asr_config import load_module
from test_text_quality import load_offline_service


def load_config_module():
    with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv", return_value=False):
        return load_module("backend/config/ai_config.py", "offline_reasoning_config")


class ReasoningEffortConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_config_module()

    def config(self, **environment):
        with patch.dict(os.environ, environment, clear=True):
            return self.module.OpenAIConfig()

    def test_unset_and_blank_preserve_unspecified_default(self):
        self.assertIsNone(self.config().reasoning_effort)
        for value in ("", "   "):
            self.assertIsNone(self.config(OPENAI_REASONING_EFFORT=value).reasoning_effort)

    def test_explicit_low_is_loaded_and_trimmed(self):
        self.assertEqual(self.config(OPENAI_REASONING_EFFORT=" low ").reasoning_effort, "low")

    def test_only_installed_sdk_declared_values_are_accepted(self):
        def values(annotation):
            for item in get_args(annotation):
                if isinstance(item, str):
                    yield item
                else:
                    yield from values(item)

        expected = set(values(ReasoningEffort))
        self.assertTrue(expected)
        self.assertEqual(self.module._REASONING_EFFORT_VALUES, expected)
        for effort in expected:
            self.assertEqual(self.config(OPENAI_REASONING_EFFORT=effort).reasoning_effort, effort)

    def test_invalid_environment_value_fails_without_echoing_it(self):
        value = "invalid-private-value"
        with self.assertRaises(ValueError) as raised:
            self.config(OPENAI_REASONING_EFFORT=value)
        self.assertIn("OPENAI_REASONING_EFFORT", str(raised.exception))
        self.assertNotIn(value, str(raised.exception))


class ReasoningEffortRequestTests(unittest.IsolatedAsyncioTestCase):
    async def verify_all_content_paths(self, effort):
        config_module = load_config_module()
        environment = {"OPENAI_REASONING_EFFORT": effort} if effort is not None else {}
        with patch.dict(os.environ, environment, clear=True):
            config = config_module.OpenAIConfig()
        requests = []
        phase = ""

        def create(**kwargs):
            requests.append((phase, kwargs))
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content="Source content.")
            )])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        module = load_offline_service("text_optimizer.py")
        with patch.object(module, "is_openai_available", return_value=True), patch.object(module, "get_openai_client", return_value=client):
            service = module.TextOptimizer()
            service.config = config
            phase = "optimizer"
            await service.optimize_transcript("Source content.")

        module = load_offline_service("text_translator.py")
        with patch.object(module, "is_openai_available", return_value=True), patch.object(module, "get_openai_client", return_value=client):
            service = module.TextTranslator()
            service.config = config
            phase = "single_translation"
            await service.translate_text("Source content.", "zh", "en")
            phase = "chunk_translation"
            with patch.object(module, "smart_chunk_text", return_value=["First fact.", "Last fact."]):
                await service._translate_with_chunks("Source content.", "中文", "English")

        module = load_offline_service("content_summarizer.py")
        service = module.ContentSummarizer()
        service.config, service.client = config, client
        phase = "single_summary"
        await service.summarize("Source content.", "zh")
        phase = "chunk_summary_and_merge"
        with patch.object(service, "_smart_chunk_text", return_value=["First fact.", "Last fact."]):
            await service._summarize_with_chunks("Source content.", "zh", None, 4000)
        phase = "merge"
        await service._integrate_chunk_summaries("First fact. Last fact.", "zh")
        phase = "mindmap"
        await service.generate_mindmap("Source content.", "zh")

        self.assertEqual(len(requests), 10)
        self.assertEqual({name for name, _ in requests}, {
            "optimizer", "single_translation", "chunk_translation", "single_summary",
            "chunk_summary_and_merge", "merge", "mindmap",
        })
        for name, request in requests:
            with self.subTest(path=name, effort=effort):
                if effort is None:
                    self.assertNotIn("reasoning_effort", request)
                else:
                    self.assertEqual(request.get("reasoning_effort"), effort)

    async def test_low_reaches_every_content_service_api_request(self):
        await self.verify_all_content_paths("low")

    async def test_unset_does_not_send_reasoning_effort_to_any_content_api(self):
        await self.verify_all_content_paths(None)


class IncompleteContentWarningTests(unittest.IsolatedAsyncioTestCase):
    async def test_truncation_has_actionable_warning_in_each_content_service(self):
        for filename, class_name in (("text_optimizer.py", "TextOptimizer"),
                                      ("text_translator.py", "TextTranslator"),
                                      ("content_summarizer.py", "ContentSummarizer")):
            with self.subTest(service=class_name):
                calls = []

                def create(**kwargs):
                    calls.append(kwargs)
                    return SimpleNamespace(choices=[SimpleNamespace(
                        finish_reason="length", message=SimpleNamespace(content="Partial content.")
                    )])

                module = load_offline_service(filename)
                client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
                with patch.object(module, "get_openai_client", return_value=client):
                    service = getattr(module, class_name)()
                    if class_name == "ContentSummarizer":
                        result = await service.summarize("Complete source content.", "zh")
                    else:
                        with patch.object(module, "is_openai_available", return_value=True):
                            result = await (service.optimize_transcript("Complete source content.")
                                            if class_name == "TextOptimizer" else
                                            service.translate_text("Complete source content.", "zh", "en"))
                        self.assertEqual(result, "Complete source content.")
                self.assertTrue(result)
                self.assertEqual(len(calls), 1)
                self.assertTrue(any("输出被截断或预算耗尽" in warning for warning in service.warnings))


if __name__ == "__main__":
    unittest.main()
