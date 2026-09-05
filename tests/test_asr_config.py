"""ASR 配置与按需导入回归；所有模型构造均使用离线 mock。"""
import builtins
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(relative_path, name, replacements=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {name: module, **(replacements or {})}):
        spec.loader.exec_module(module)
    return module


class ASRConfigurationTests(unittest.TestCase):
    def setUp(self):
        # 隔离真实环境和 .env，只加载待测配置代码。
        with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv", return_value=False):
            self.config_module = load_module("backend/config/ai_config.py", "offline_asr_config")
        self.client_module = load_module(
            "backend/core/ai_client.py", "offline_asr_client",
            {"backend.config.ai_config": self.config_module},
        )

    def config(self, **environment):
        with patch.dict(os.environ, environment, clear=True):
            return self.config_module.ASRConfig()

    def test_blank_model_uses_each_providers_default(self):
        for provider, expected in (
            ("whisper", "base"), ("funasr", "SenseVoiceSmall"), ("qwen3", "Qwen3-ASR-0.6B"),
        ):
            with self.subTest(provider=provider):
                config = self.config(ASR_PROVIDER=provider, ASR_MODEL="")
                self.assertEqual(config.model, expected)
                self.assertEqual(config.provider, provider)

    def test_example_allows_switching_only_the_provider(self):
        example = {}
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
            if line.startswith(("ASR_PROVIDER=", "ASR_MODEL=")):
                key, value = line.split("=", 1)
                example[key] = value
        for provider, expected in (("funasr", "SenseVoiceSmall"), ("qwen3", "Qwen3-ASR-0.6B")):
            with self.subTest(provider=provider):
                config = self.config(**{**example, "ASR_PROVIDER": provider})
                self.assertEqual(config.model, expected)

    def test_explicit_model_is_preserved_for_all_providers(self):
        for provider in ("whisper", "funasr", "qwen3"):
            with self.subTest(provider=provider):
                config = self.config(ASR_PROVIDER=provider, ASR_MODEL="community/custom-asr")
                self.assertEqual(config.model, "community/custom-asr")

    def test_legacy_whisper_override_does_not_change_other_providers(self):
        for provider in ("whisper", "funasr", "qwen3"):
            with self.subTest(provider=provider):
                config = self.config(ASR_PROVIDER=provider, ASR_MODEL="custom-model", WHISPER_MODEL_SIZE="tiny")
                self.assertEqual(config.model, "tiny" if provider == "whisper" else "custom-model")

    def test_whisper_local_directory_takes_priority_without_downloading(self):
        config = self.config(ASR_PROVIDER="whisper", ASR_MODEL="base", ASR_MODEL_DIR="models/offline-whisper")
        whisper = types.ModuleType("faster_whisper")
        whisper.WhisperModel = Mock(return_value=object())
        with patch.dict(sys.modules, {"faster_whisper": whisper}), patch.object(
            self.client_module, "_download_model", side_effect=AssertionError("不得下载模型"),
        ):
            self.client_module.ASRModelSingleton._load_model(config, "huggingface")
        whisper.WhisperModel.assert_called_once_with("models/offline-whisper", device="cpu", compute_type="int8")

    def test_whisper_without_local_directory_keeps_model_name(self):
        config = self.config(ASR_PROVIDER="whisper", ASR_MODEL="small")
        whisper = types.ModuleType("faster_whisper")
        whisper.WhisperModel = Mock(return_value=object())
        with patch.dict(sys.modules, {"faster_whisper": whisper}):
            self.client_module.ASRModelSingleton._load_model(config, "huggingface")
        whisper.WhisperModel.assert_called_once_with("small", device="cpu", compute_type="int8")

    def test_changing_local_directory_reloads_cached_model(self):
        config = self.config(ASR_PROVIDER="whisper", ASR_MODEL_DIR="models/first")
        whisper = types.ModuleType("faster_whisper")
        whisper.WhisperModel = Mock(side_effect=[object(), object()])
        with patch.dict(sys.modules, {"faster_whisper": whisper}), patch.object(
            self.client_module, "get_asr_config", return_value=config,
        ):
            first = self.client_module.ASRModelSingleton.get_instance()
            self.assertIs(first, self.client_module.ASRModelSingleton.get_instance())
            config.model_dir = "models/second"
            self.assertIsNot(first, self.client_module.ASRModelSingleton.get_instance())
        self.assertEqual([call.args[0] for call in whisper.WhisperModel.call_args_list], ["models/first", "models/second"])

    def test_client_import_does_not_import_any_asr_runtime(self):
        original_import = builtins.__import__
        optional_modules = {"faster_whisper", "torch", "torchaudio", "funasr", "qwen_asr", "modelscope", "anp"}
        attempts = []

        def guarded_import(name, *args, **kwargs):
            if name.split(".", 1)[0] in optional_modules:
                attempts.append(name)
                raise ImportError(f"Blocked optional runtime: {name}")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            module = load_module("backend/core/ai_client.py", "offline_lazy_asr_client", {
                "backend.config.ai_config": self.config_module,
            })
        self.assertEqual(attempts, [])
        self.assertIsNone(module.ASRModelSingleton._instance)

    def test_missing_optional_runtime_has_install_guidance(self):
        for provider, module_name in (("funasr", "funasr"), ("qwen3", "qwen_asr")):
            with self.subTest(provider=provider), patch.dict(sys.modules, {module_name: None}):
                with self.assertRaisesRegex(RuntimeError, f"--extra {provider}"):
                    self.client_module.ASRModelSingleton._load_model(self.config(ASR_PROVIDER=provider), "huggingface")


if __name__ == "__main__":
    unittest.main()
