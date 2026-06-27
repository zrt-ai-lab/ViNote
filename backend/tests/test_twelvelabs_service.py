"""TwelveLabs 服务测试。

- 无网络单元测试：验证配置开关、provider 选择、文本切分等纯逻辑。
- 实时契约测试：仅在设置了 TWELVELABS_API_KEY 时运行，验证 Marengo 返回 512 维向量。

运行: uv run --extra dev --extra twelvelabs pytest backend/tests/test_twelvelabs_service.py
"""
import asyncio
import os

import pytest


# ──────────────────────────────────────────────────────────
# 无网络单元测试
# ──────────────────────────────────────────────────────────
def test_chunk_text_splits_on_sentence_boundaries():
    from backend.services.twelvelabs_service import _chunk_text

    out = _chunk_text("第一句。第二句！第三句？")
    assert "".join(out) == "第一句。第二句！第三句？"
    assert len(out) == 3
    assert _chunk_text("") == []


def test_config_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TWELVELABS_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_QA_PROVIDER", raising=False)
    from backend.config.ai_config import TwelveLabsConfig

    cfg = TwelveLabsConfig()
    assert cfg.is_configured is False
    assert cfg.use_for_qa is False


def test_config_enabled_via_env(monkeypatch):
    monkeypatch.setenv("TWELVELABS_API_KEY", "test-key")
    monkeypatch.setenv("VIDEO_QA_PROVIDER", "twelvelabs")
    monkeypatch.setenv("TWELVELABS_QA_MAX_TOKENS", "100")  # < 512 应被钳制
    from backend.config.ai_config import TwelveLabsConfig

    cfg = TwelveLabsConfig()
    assert cfg.is_configured is True
    assert cfg.use_for_qa is True
    assert cfg.qa_max_tokens == 512  # 钳制到模型下限


def test_qa_requires_video_url(monkeypatch):
    """未配置 key 时 is_available 为 False；空 video_url 抛 ValueError。"""
    monkeypatch.setenv("TWELVELABS_API_KEY", "test-key")
    from backend.services.twelvelabs_service import TwelveLabsVideoQAService

    svc = TwelveLabsVideoQAService()

    async def run():
        gen = svc.answer_question_stream(question="hi", video_url="")
        with pytest.raises(ValueError):
            await gen.__anext__()

    asyncio.run(run())


# ──────────────────────────────────────────────────────────
# 实时契约测试（需 TWELVELABS_API_KEY）
# ──────────────────────────────────────────────────────────
@pytest.mark.skipif(
    not os.getenv("TWELVELABS_API_KEY"),
    reason="需要 TWELVELABS_API_KEY 才能运行实时测试",
)
def test_marengo_embedding_is_512_dim():
    from backend.services.twelvelabs_service import TwelveLabsVideoQAService

    svc = TwelveLabsVideoQAService()
    assert svc.is_available()
    vec = svc.embed_text("a person riding a bicycle")
    assert len(vec) == 512
    assert all(isinstance(x, float) for x in vec[:8])
