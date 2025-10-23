"""
视频问答服务
基于视频转录文本的智能问答
"""
import logging
import asyncio
from typing import Optional

from openai import AsyncOpenAI

from backend.core.ai_client import get_openai_client, is_openai_available
from backend.config.ai_config import get_openai_config

logger = logging.getLogger(__name__)


class VideoQAService:
    """视频问答服务"""
    
    def __init__(self):
        """初始化问答服务"""
        self.config = get_openai_config()
        self.client = get_openai_client()
    
    async def answer_question_stream(
        self,
        question: str,
        transcript: str,
        video_url: str = ""
    ):
        """
        基于转录文本回答问题（流式输出）
        
        Args:
            question: 用户问题
            transcript: 转录文本
            video_url: 视频URL（可选）
            
        Yields:
            回答的文本片段
        """
        if not self.client:
            raise Exception("OpenAI API不可用")
        
        if not question.strip():
            raise ValueError("问题不能为空")
        
        if not transcript.strip():
            raise ValueError("转录文本不能为空")

        # 构建问答prompt
        system_prompt = """你是一个专业的视频内容分析助手。基于提供的视频转录内容，准确、详细且有帮助地回答用户的问题。

回答要求：
1. 直接针对问题，提供清晰的答案
2. 严格基于转录内容，不要编造信息
3. 语言清晰易懂，结构合理
4. 如果转录中没有相关信息，请诚实说明
5. 可以适当引用原文支持你的答案
"""

        user_prompt = f"""视频核心内容：
{transcript}

用户问题：
{question}

请基于上述转录内容回答问题。"""
        
        logger.info(f"正在处理问答流: {question[:50]}...")
        async_client = AsyncOpenAI()
        try:
            stream = await async_client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.6,
                stream=True
            )

            chunk_count = 0
            async for chunk in stream:  # 注意: async for
                if chunk.choices[0].delta.content:
                    chunk_count += 1
                    yield chunk.choices[0].delta.content

                    # 然后检查是否结束（但不在这里break，让循环自然结束）
                if chunk.choices[0].finish_reason:
                    logger.info(f"问答完成，原因: {chunk.choices[0].finish_reason}, 共{chunk_count}个片段")
                    if chunk.choices[0].finish_reason == "length":
                        logger.warning("回答因达到长度限制而截断")
            
        except Exception as e:
            logger.error(f"问答流异常: {e}")
            raise Exception(f"问答失败: {str(e)}")
    
    def is_available(self) -> bool:
        """检查问答服务是否可用"""
        return is_openai_available()
