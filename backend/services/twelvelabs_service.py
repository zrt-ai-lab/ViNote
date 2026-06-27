"""
TwelveLabs 服务（可选）

提供两项基于视频本身（而非转录文本）的能力，作为现有功能的**可选增强**：

1. ``TwelveLabsVideoQAService`` —— 使用 Pegasus 直接对视频画面进行问答。
   与 ``VideoQAService`` 接口一致（``answer_question_stream`` / ``is_available``），
   因此可作为视频问答的可选 provider 无缝替换；未配置时不影响默认的
   "转录文本 + OpenAI" 路径。

2. ``embed_text`` / ``embed_video`` —— 使用 Marengo 生成 512 维多模态向量，
   可用于对抽取出的视频片段做语义检索。

依赖可选包 ``twelvelabs``（``pip install "twelvelabs>=1.2.8"`` 或
``uv sync --extra twelvelabs``）以及环境变量 ``TWELVELABS_API_KEY``。
免费额度可在 https://twelvelabs.io 获取。

设计说明：
- Pegasus 1.5 不接受裸 ``video_id``，需要可公开访问的 URL 或已上传的
  ``asset_id``。本服务对带有公开 URL 的视频直接走 URL 路径；
  对本地文件可由调用方先上传为 asset（``upload_asset``，direct 上传上限 200MB）。
- Pegasus 要求被分析的视频时长 >= 4 秒。
- Marengo REST 接口的原始向量字段名为 ``float``，Python SDK 暴露为 ``float_``。
"""
import asyncio
import logging
from typing import List, Optional

from backend.config.ai_config import get_twelvelabs_config

logger = logging.getLogger(__name__)


def _get_client():
    """惰性创建 TwelveLabs 客户端；缺少依赖或 key 时返回 None。"""
    config = get_twelvelabs_config()
    if not config.is_configured:
        return None
    try:
        from twelvelabs import TwelveLabs
    except ImportError:
        logger.warning(
            "未安装 twelvelabs 依赖，TwelveLabs 功能不可用。"
            "请执行: pip install \"twelvelabs>=1.2.8\""
        )
        return None
    try:
        return TwelveLabs(api_key=config.api_key)
    except Exception as e:  # pragma: no cover - 依赖外部 SDK
        logger.error(f"TwelveLabs 客户端初始化失败: {e}")
        return None


class TwelveLabsVideoQAService:
    """基于 Pegasus 的视频问答服务（直接理解视频画面）。

    与 ``VideoQAService`` 接口保持一致，可作为视频问答的可选 provider。
    """

    def __init__(self):
        self.config = get_twelvelabs_config()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _get_client()
        return self._client

    def is_available(self) -> bool:
        """key 已配置且依赖已安装时返回 True。"""
        return self.client is not None

    async def answer_question_stream(
        self,
        question: str,
        transcript: str = "",
        video_url: str = "",
    ):
        """基于视频画面回答问题（流式输出）。

        Args:
            question: 用户问题
            transcript: 转录文本（可选，作为补充上下文）
            video_url: 视频的公开 URL（Pegasus 必需）

        Yields:
            回答文本片段
        """
        if not self.client:
            raise Exception("TwelveLabs API 不可用")
        if not question.strip():
            raise ValueError("问题不能为空")
        if not video_url.strip():
            raise ValueError("TwelveLabs 视频问答需要可公开访问的视频 URL")

        from twelvelabs.types.video_context import VideoContext_Url

        prompt = (
            "你是一个专业的视频内容分析助手。请基于视频画面与音频，"
            "准确、详细且有帮助地回答用户的问题；若视频中没有相关信息，请诚实说明。\n\n"
            f"用户问题：{question}"
        )
        if transcript.strip():
            prompt += f"\n\n（参考转录文本）：\n{transcript[:4000]}"

        logger.info(f"Pegasus 视频问答: {question[:50]}...")

        # SDK 为同步调用，放到线程池避免阻塞事件循环
        def _analyze():
            resp = self.client.analyze(
                model_name=self.config.pegasus_model,
                video=VideoContext_Url(url=video_url),
                prompt=prompt,
                max_tokens=self.config.qa_max_tokens,
            )
            return resp.data or ""

        try:
            answer = await asyncio.to_thread(_analyze)
        except Exception as e:
            logger.error(f"Pegasus 问答异常: {e}")
            raise Exception(f"问答失败: {str(e)}")

        # Pegasus 返回完整文本，按句子切分以模拟流式体验
        for chunk in _chunk_text(answer):
            yield chunk

    def upload_asset(self, file_path: str) -> str:
        """将本地视频上传为 TwelveLabs asset，返回 asset_id。

        direct 上传上限约 200MB；更大的文件请改用公开 URL。
        """
        if not self.client:
            raise Exception("TwelveLabs API 不可用")
        with open(file_path, "rb") as f:
            asset = self.client.assets.create(
                method="direct", file=f, filename=file_path.split("/")[-1]
            )
        return asset.id

    def embed_text(self, text: str) -> List[float]:
        """用 Marengo 生成查询文本的 512 维向量（用于片段语义检索）。"""
        if not self.client:
            raise Exception("TwelveLabs API 不可用")
        resp = self.client.embed.create(model_name=self.config.marengo_model, text=text)
        return resp.text_embedding.segments[0].float_


def _chunk_text(text: str) -> List[str]:
    """将整段文本切成小片段，用于 SSE 流式输出。"""
    if not text:
        return []
    import re
    parts = re.split(r"(?<=[。！？.!?\n])", text)
    return [p for p in parts if p]
