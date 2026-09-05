"""
文本翻译服务
使用OpenAI API进行高质量翻译
"""
import logging
import asyncio
from typing import Optional

from backend.core.ai_client import get_openai_client, is_openai_available
from backend.config.ai_config import get_openai_config, get_language_name
from backend.services.content_completion import EmptyContentError, IncompleteContentError, SOURCE_RULES, request_text_content
from backend.utils.text_processor import detect_language, smart_chunk_text

logger = logging.getLogger(__name__)

MAX_CONCURRENT_CHUNKS = 5


class TextTranslator:
    """文本翻译服务"""
    
    def __init__(self):
        """初始化翻译服务"""
        self.config = get_openai_config()
        self.warnings: list[str] = []

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
    
    async def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None
    ) -> str:
        """
        翻译文本到目标语言
        
        Args:
            text: 要翻译的文本
            target_language: 目标语言代码
            source_language: 源语言代码（可选，会自动检测）
            
        Returns:
            翻译后的文本
        """
        self.warnings.clear()
        try:
            # 检测源语言
            if not source_language:
                source_language = detect_language(text)
            
            # 如果源语言和目标语言相同，直接返回
            if not self.should_translate(source_language, target_language):
                logger.info(f"源语言({source_language})与目标语言({target_language})相同，跳过翻译")
                return text

            if not is_openai_available():
                logger.warning("OpenAI API不可用，无法翻译")
                self._warn("LLM 未配置，翻译保留原文")
                return text
            
            source_lang_name = get_language_name(source_language)
            target_lang_name = get_language_name(target_language)
            
            logger.info(f"开始翻译：{source_lang_name} -> {target_lang_name}")
            
            # 估算文本长度，决定是否需要分块
            if len(text) > 3000:
                logger.info(f"文本较长({len(text)} chars)，启用分块翻译")
                return await self._translate_with_chunks(text, target_lang_name, source_lang_name)
            else:
                return await self._translate_single_text(text, target_lang_name, source_lang_name)
                
        except Exception as e:
            logger.error("翻译失败 (%s)", type(e).__name__)
            self._warn("LLM 翻译失败，已保留原文")
            return text
    
    async def _translate_single_text(
        self,
        text: str,
        target_lang_name: str,
        source_lang_name: str
    ) -> str:
        """
        翻译单个文本块
        
        Args:
            text: 要翻译的文本
            target_lang_name: 目标语言名称
            source_lang_name: 源语言名称
            
        Returns:
            翻译后的文本
        """
        system_prompt = f"""你是专业翻译专家。请将{source_lang_name}文本准确翻译为{target_lang_name}。
{SOURCE_RULES}

翻译要求：
- 保持原文的格式和结构（包括段落分隔、标题等）
- 准确传达原意，语言自然流畅
- 源文明确写出的产品名、代码标识和专业名称保留原拼写及大小写，不按发音或常识改成另一个名称
- 源文若比较不同名称或拼写，保留各自所指对象，不能全局统一替换
- 不补充原文没有的解释、背景、事实或结论，不消除原有不确定性
- 不要添加解释或注释
- 如果遇到Markdown格式，请保持格式不变"""

        user_prompt = f"""请将以下{source_lang_name}文本翻译为{target_lang_name}：

{text}

只返回翻译结果，不要添加任何说明。"""

        try:
            client = get_openai_client()
            return await request_text_content(
                client,
                reasoning_effort=getattr(self.config, "reasoning_effort", None),
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.config.translation_max_tokens,
                temperature=self.config.translation_temperature
            )
            
        except IncompleteContentError:
            self._warn("LLM 输出被截断或预算耗尽，翻译保留原文")
            return text
        except EmptyContentError:
            self._warn("LLM 返回空内容，翻译保留原文")
            return text
        except Exception as e:
            logger.error("单文本翻译失败 (%s)", type(e).__name__)
            self._warn("LLM 翻译失败，已保留原文")
            return text
    
    async def _translate_with_chunks(
        self,
        text: str,
        target_lang_name: str,
        source_lang_name: str
    ) -> str:
        chunks = smart_chunk_text(text, max_chars_per_chunk=4000, prefer_paragraphs=True)
        total = len(chunks)
        logger.info(f"分割为 {total} 个块并行翻译")

        client = get_openai_client()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

        async def _translate_chunk(i: int, chunk: str) -> str:
            system_prompt = f"""你是专业翻译专家。请将{source_lang_name}文本准确翻译为{target_lang_name}。
{SOURCE_RULES}

这是完整文档的第{i+1}部分，共{total}部分。

翻译要求：
- 保持原文的格式和结构
- 准确传达原意，语言自然流畅
- 源文明确写出的产品名、代码标识和专业名称保留原拼写及大小写；比较不同名称或拼写时保留各自所指对象，不全局替换
- 不补充本段没有的背景或事实，也不猜测未提供的前后文
- 不要添加解释或注释
- 保持与前后文的连贯性"""

            user_prompt = f"""请将以下{source_lang_name}文本翻译为{target_lang_name}：

{chunk}

只返回翻译结果。"""

            async with semaphore:
                try:
                    return await request_text_content(
                        client,
                        reasoning_effort=getattr(self.config, "reasoning_effort", None),
                        model=self.config.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        max_tokens=self.config.translation_max_tokens,
                        temperature=self.config.translation_temperature
                    )
                except EmptyContentError:
                    self._warn("LLM 返回空内容，部分翻译保留原文")
                    return chunk
                except Exception as e:
                    logger.error("翻译第 %s 块失败 (%s)", i + 1, type(e).__name__)
                    self._warn("LLM 翻译失败，部分翻译保留原文")
                    return chunk

        translated_chunks = await asyncio.gather(*[_translate_chunk(i, c) for i, c in enumerate(chunks)])
        return "\n\n".join(translated_chunks)
    
    def is_available(self) -> bool:
        """检查翻译服务是否可用"""
        return is_openai_available()
    
    @staticmethod
    def should_translate(source_language: str, target_language: str) -> bool:
        """
        判断是否需要翻译
        
        Args:
            source_language: 源语言代码
            target_language: 目标语言代码
            
        Returns:
            True if 需要翻译，False otherwise
        """
        if not source_language or not target_language:
            return False
        
        # 标准化语言代码
        source_lang = source_language.lower().strip()
        target_lang = target_language.lower().strip()
        
        # 如果语言相同，不需要翻译
        if source_lang == target_lang:
            return False
        
        # 处理中文的特殊情况
        chinese_variants = ["zh", "zh-cn", "zh-hans", "chinese"]
        if source_lang in chinese_variants and target_lang in chinese_variants:
            return False
        
        return True
