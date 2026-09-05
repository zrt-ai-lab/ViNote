"""Source grounding, bounded empty-result recovery, and honest content fallback."""
import importlib.util
from pathlib import Path
import sys
import threading
from tempfile import TemporaryDirectory
import types
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from backend.services.content_completion import ContentRefusalError, EmptyContentError, IncompleteContentError, SOURCE_RULES, request_text_content
from test_text_quality import load_offline_service


def response(content, refusal=None, finish_reason=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, refusal=refusal), finish_reason=finish_reason)])


def client_for(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


class ContentCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_empty_response_retries_with_identical_parameters(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            return response(None if len(calls) == 1 else "source-grounded text")

        result = await request_text_content(client_for(create), model="offline-test", max_tokens=4000)
        self.assertEqual(result, "source-grounded text")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])

    async def test_empty_and_malformed_results_stop_after_two_requests(self):
        for item in (response(" \n"), response(None), SimpleNamespace(choices=[])):
            with self.subTest(item=item):
                calls = []
                client = client_for(lambda **kw: calls.append(kw) or item)
                with self.assertRaises(EmptyContentError):
                    await request_text_content(client, model="offline-test")
                self.assertEqual(len(calls), 2)

    async def test_refusal_is_not_retried(self):
        for content in (None, "Refusal explanation"):
            calls = []
            with self.assertRaises(ContentRefusalError):
                await request_text_content(client_for(lambda **kw: calls.append(kw) or response(content, "refusal")))
            self.assertEqual(len(calls), 1)

    async def test_transport_exception_does_not_add_another_retry_layer(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("offline upstream failure")

        with self.assertRaises(RuntimeError):
            await request_text_content(client_for(create))
        self.assertEqual(len(calls), 1)

    async def test_truncated_and_filtered_content_are_not_successful_or_retried(self):
        for finish_reason, error_type in (("length", IncompleteContentError), ("content_filter", ContentRefusalError)):
            for content in (None, "Incomplete or filtered fragment."):
                with self.subTest(finish_reason=finish_reason, content=content):
                    calls = []
                    client = client_for(lambda **kw: calls.append(kw) or response(content, finish_reason=finish_reason))
                    with self.assertRaises(error_type):
                        await request_text_content(client)
                    self.assertEqual(len(calls), 1)

    async def test_reasoning_option_is_opt_in_and_does_not_grow_token_budget(self):
        for effort in (None, "low"):
            calls = []
            client = client_for(lambda **kw: calls.append(kw) or response("Complete source."))
            await request_text_content(client, reasoning_effort=effort, max_tokens=4000)
            self.assertEqual(calls[0]["max_tokens"], 4000)
            if effort:
                self.assertEqual(calls[0]["reasoning_effort"], effort)
            else:
                self.assertNotIn("reasoning_effort", calls[0])

    async def test_reasoning_exhaustion_never_silently_increases_cost(self):
        item = response(None, finish_reason="length")
        item.usage = SimpleNamespace(completion_tokens=4000,
                                     completion_tokens_details=SimpleNamespace(reasoning_tokens=4000))
        calls = []
        with self.assertRaises(IncompleteContentError):
            await request_text_content(client_for(lambda **kw: calls.append(kw) or item), max_tokens=4000)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["max_tokens"], 4000)

    async def test_cancelled_first_request_cannot_start_an_empty_retry(self):
        import asyncio
        started, released, finished = threading.Event(), threading.Event(), threading.Event()
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            started.set()
            released.wait(5)
            finished.set()
            return response(None)
        client = client_for(create)
        task = asyncio.create_task(request_text_content(client, max_tokens=4000))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            released.set()
            await asyncio.to_thread(finished.wait, 2)
        self.assertEqual(len(calls), 1)


class SourceGroundingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.summary_module = load_offline_service("content_summarizer.py")
        self.summary = self.summary_module.ContentSummarizer()
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return response("Only the supplied source is summarized.")

    def assert_grounded(self, request):
        system = request["messages"][0]["content"]
        self.assertIn(SOURCE_RULES, system)
        self.assertIn("Keep distinct names/spellings", system)
        self.assertIn("source explicitly spells out or corrects a name", system)
        self.assertIn("Do not reinterpret ambiguous or garbled source text", system)
        self.assertIn("Do not attribute unlabelled sounds", system)
        self.assertNotIn("600-1200", system)
        self.assertNotIn("120-220", system)

    async def test_short_summary_has_no_minimum_length_or_outside_background(self):
        self.summary.client = client_for(self.create)
        await self.summary.summarize("The speaker is standing near elephants.", "zh")
        self.assertEqual(len(self.requests), 1)
        self.assert_grounded(self.requests[0])
        self.assertIn("one to three sentences", self.requests[0]["messages"][0]["content"])
        self.assertIn("no minimum word count", self.requests[0]["messages"][0]["content"])
        self.assertIn("standing near elephants", self.requests[0]["messages"][1]["content"])

    async def test_chunk_and_merge_stages_use_the_same_source_constraints(self):
        self.summary.client = client_for(self.create)
        with patch.object(self.summary, "_estimate_tokens", return_value=5000), patch.object(
            self.summary, "_smart_chunk_text", return_value=["First distinct source fact.", "Last distinct source fact."]
        ):
            await self.summary.summarize("long source", "en")
        self.assertEqual(len(self.requests), 3)
        for request in self.requests:
            self.assert_grounded(request)
        self.assertTrue(any("First distinct source fact." in r["messages"][1]["content"] for r in self.requests))
        self.assertTrue(any("Last distinct source fact." in r["messages"][1]["content"] for r in self.requests))
        self.assertIn("Do not invent connections", self.requests[-1]["messages"][0]["content"])

    async def test_mindmap_does_not_demand_unsupported_branches(self):
        self.summary.client = client_for(self.create)
        await self.summary.generate_mindmap("Only one stated fact.", "zh")
        self.assert_grounded(self.requests[0])
        self.assertIn("Every node must be supported", self.requests[0]["messages"][0]["content"])
        self.assertIn("no minimum depth or node count", self.requests[0]["messages"][0]["content"])

    async def test_optimizer_preserves_compared_spellings_without_global_replacement(self):
        module = load_offline_service("text_optimizer.py")
        source = "AsterIDE is the editor. AsterIdE is the different spelling being compared."

        def create(**kwargs):
            self.requests.append(kwargs)
            return response(source)

        with patch.object(module, "is_openai_available", return_value=True), patch.object(
            module, "get_openai_client", return_value=client_for(create)
        ):
            result = await module.TextOptimizer().optimize_transcript(source)
        self.assert_grounded(self.requests[0])
        self.assertIn("AsterIDE", result)
        self.assertIn("AsterIdE", result)
        self.assertIn("without filling in facts", self.requests[0]["messages"][1]["content"])

    async def test_single_translation_preserves_names_and_calls_off_event_loop(self):
        module = load_offline_service("text_translator.py")
        thread_ids = []

        def create(**kwargs):
            self.requests.append(kwargs)
            thread_ids.append(threading.get_ident())
            return response("AsterIDE 是编辑器；AsterIdE 是被比较的另一种拼写。")

        with patch.object(module, "is_openai_available", return_value=True), patch.object(
            module, "get_openai_client", return_value=client_for(create)
        ):
            service = module.TextTranslator()
            result = await service.translate_text("AsterIDE is an editor, unlike the spelling AsterIdE.", "zh", "en")
        self.assert_grounded(self.requests[0])
        self.assertIn("AsterIDE", result)
        self.assertIn("AsterIdE", result)
        self.assertNotEqual(thread_ids[0], threading.get_ident())
        self.assertEqual(service.warnings, [])


class ContentFallbackTests(unittest.IsolatedAsyncioTestCase):
    def test_basic_cleanup_preserves_source_punctuation_without_extra_periods(self):
        module = load_offline_service("text_optimizer.py")
        service = module.TextOptimizer()
        for source in ("First fact. Final question?", "这是事实。 这是问题？ 保留感叹！", "".join(["精确事实！" * 100])):
            result = service._basic_transcript_cleanup(source)
            self.assertEqual("".join(result.split()), "".join(source.split()))

    async def test_truncation_and_filter_keep_full_optimizer_and_translation_source(self):
        for filename, class_name in (("text_optimizer.py", "TextOptimizer"), ("text_translator.py", "TextTranslator")):
            for finish_reason in ("length", "content_filter"):
                with self.subTest(service=class_name, finish_reason=finish_reason):
                    module = load_offline_service(filename)
                    calls = []
                    client = client_for(lambda **kw: calls.append(kw) or response("Partial.", finish_reason=finish_reason))
                    source = "The complete source includes the final essential fact."
                    with patch.object(module, "is_openai_available", return_value=True), patch.object(
                        module, "get_openai_client", return_value=client
                    ):
                        service = getattr(module, class_name)()
                        result = await (service.optimize_transcript(source) if class_name == "TextOptimizer"
                                        else service.translate_text(source, "zh", "en"))
                    self.assertEqual(result.strip(), source)
                    self.assertTrue(service.warnings)
                    self.assertEqual(len(calls), 1)

    async def test_optimizer_empty_then_success_is_not_marked_degraded(self):
        module = load_offline_service("text_optimizer.py")
        calls = []
        client = client_for(lambda **kw: calls.append(kw) or response(None if len(calls) == 1 else "Source content."))
        with patch.object(module, "is_openai_available", return_value=True), patch.object(module, "get_openai_client", return_value=client):
            service = module.TextOptimizer()
            result = await service.optimize_transcript("Source content.")
        self.assertIn("Source content.", result)
        self.assertEqual(len(calls), 2)
        self.assertEqual(service.warnings, [])

    async def test_optimizer_repeated_empty_retains_source_and_warns(self):
        module = load_offline_service("text_optimizer.py")
        with patch.object(module, "is_openai_available", return_value=True), patch.object(
            module, "get_openai_client", return_value=client_for(lambda **kw: response(None))
        ):
            service = module.TextOptimizer()
            result = await service.optimize_transcript("Source content.")
        self.assertIn("Source content.", result)
        self.assertTrue(service.warnings)

    async def test_summary_and_mindmap_repeated_empty_are_explicit_fallbacks(self):
        module = load_offline_service("content_summarizer.py")
        service = module.ContentSummarizer()
        service.client = client_for(lambda **kw: response(None))
        self.assertTrue(await service.summarize("Source content."))
        self.assertTrue(service.warnings)
        self.assertEqual(await service.generate_mindmap("Source content."), "")
        self.assertTrue(any("思维导图" in warning for warning in service.warnings))

    async def test_single_and_chunk_translation_preserve_source_and_warn_on_empty(self):
        module = load_offline_service("text_translator.py")
        with patch.object(module, "is_openai_available", return_value=True), patch.object(
            module, "get_openai_client", return_value=client_for(lambda **kw: response(None))
        ):
            for source in ("Source content.", "Long source fact. " * 500):
                service = module.TextTranslator()
                result = await service.translate_text(source, "zh", "en")
                self.assertEqual("".join(result.split()), "".join(source.split()))
                self.assertTrue(service.warnings)

    async def test_provider_payload_is_not_logged_or_included_in_warnings(self):
        module = load_offline_service("text_translator.py")

        def create(**kwargs):
            raise RuntimeError("synthetic-secret-provider-payload")

        with patch.object(module, "is_openai_available", return_value=True), patch.object(
            module, "get_openai_client", return_value=client_for(create)
        ), self.assertLogs(module.__name__, level="ERROR") as logs:
            service = module.TextTranslator()
            self.assertEqual(await service.translate_text("Source.", "zh", "en"), "Source.")
        self.assertNotIn("synthetic-secret-provider-payload", str(logs.output) + str(service.warnings))


class NoteTranslationWarningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.optimizer = SimpleNamespace(warnings=[], optimize_transcript=AsyncMock(return_value="The device is blue."))
        self.summarizer = SimpleNamespace(warnings=[], summarize=AsyncMock(return_value="设备是蓝色的。"),
                                          generate_mindmap=AsyncMock(return_value="# 设备\n- 蓝色"))
        self.translator = SimpleNamespace(warnings=[], translate_text=AsyncMock(return_value="设备是蓝色的。"),
                                         should_translate=lambda source, target: source != target)
        modules = {}
        for name, class_name, instance in (
            ("video_downloader", "VideoDownloader", SimpleNamespace()),
            ("audio_transcriber", "AudioTranscriber", SimpleNamespace()),
            ("text_optimizer", "TextOptimizer", self.optimizer),
            ("content_summarizer", "ContentSummarizer", self.summarizer),
            ("text_translator", "TextTranslator", self.translator),
        ):
            module = types.ModuleType("backend.services." + name)
            setattr(module, class_name, lambda instance=instance: instance)
            modules[module.__name__] = module
        ingestion = types.ModuleType("backend.services.media_ingestion")
        ingestion.cleanup_downloaded_audio = lambda *_: None
        modules[ingestion.__name__] = ingestion
        path = Path(__file__).resolve().parents[1] / "backend/services/note_generator.py"
        spec = importlib.util.spec_from_file_location("offline_note_translation_warnings", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
            self.generator = module.NoteGenerator()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    async def generate(self, target="zh"):
        return await self.generator.generate_note(
            "https://www.youtube.com/watch?v=fixture", self.root,
            summary_language=target, subtitle_text_override="The device is blue.",
            video_title_override="Fixture video",
        )

    async def test_degraded_translation_reaches_result_and_saved_artifact(self):
        async def fallback(text, *_):
            self.translator.warnings.append("LLM 翻译失败，已保留原文")
            return text

        self.translator.translate_text.side_effect = fallback
        result = await self.generate()
        self.assertIn("LLM 翻译失败，已保留原文", result["warnings"])
        self.assertIn("翻译已降级，部分或全部内容保留原文", result["translation"])
        self.assertNotIn("由 ViNote AI 自动生成", result["translation"])
        self.assertEqual(result["files"]["translation_path"].read_text(), result["translation"])

    async def test_sequential_same_language_run_does_not_inherit_old_translation_warning(self):
        async def fallback(text, *_):
            self.translator.warnings.append("LLM 翻译失败，已保留原文")
            return text

        self.translator.translate_text.side_effect = fallback
        self.assertTrue((await self.generate())["warnings"])
        result = await self.generate(target="en")
        self.assertEqual(result["warnings"], [])
        self.assertNotIn("translation", result)
        self.assertEqual(self.translator.translate_text.await_count, 1)

    async def test_successful_translation_retains_normal_footer(self):
        result = await self.generate()
        self.assertEqual(result["warnings"], [])
        self.assertIn("由 ViNote AI 自动生成", result["translation"])
        self.assertNotIn("翻译已降级", result["translation"])


if __name__ == "__main__":
    unittest.main()
