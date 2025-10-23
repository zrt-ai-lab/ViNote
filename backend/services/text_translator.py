"""
文本翻译服务
使用OpenAI API进行高质量翻译
"""
import logging
from typing import Optional

from backend.core.ai_client import get_openai_client, is_openai_available
from backend.config.ai_config import get_openai_config, get_language_name
from backend.utils.text_processor import detect_language, smart_chunk_text

logger = logging.getLogger(__name__)


class TextTranslator:
    """文本翻译服务"""
    
    def __init__(self):
        """初始化翻译服务"""
        self.config = get_openai_config()
    
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
        try:
            if not is_openai_available():
                logger.warning("OpenAI API不可用，无法翻译")
                return text
            
            # 检测源语言
            if not source_language:
                source_language = detect_language(text)
            
            # 如果源语言和目标语言相同，直接返回
            if not self.should_translate(source_language, target_language):
                logger.info(f"源语言({source_language})与目标语言({target_language})相同，跳过翻译")
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
            logger.error(f"翻译失败: {str(e)}")
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

翻译要求：
- 保持原文的格式和结构（包括段落分隔、标题等）
- 准确传达原意，语言自然流畅
- 保留专业术语的准确性
- 不要添加解释或注释
- 如果遇到Markdown格式，请保持格式不变"""

        user_prompt = f"""请将以下{source_lang_name}文本翻译为{target_lang_name}：

{text}

只返回翻译结果，不要添加任何说明。"""

        try:
            client = get_openai_client()
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.config.translation_max_tokens,
                temperature=self.config.translation_temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"单文本翻译失败: {e}")
            return text
    
    async def _translate_with_chunks(
        self,
        text: str,
        target_lang_name: str,
        source_lang_name: str
    ) -> str:
        """
        分块翻译长文本
        
        Args:
            text: 要翻译的文本
            target_lang_name: 目标语言名称
            source_lang_name: 源语言名称
            
        Returns:
            翻译后的文本
        """
        # 使用统一的分块函数
        chunks = smart_chunk_text(text, max_chars_per_chunk=4000, prefer_paragraphs=True)
        logger.info(f"分割为 {len(chunks)} 个块进行翻译")
        
        translated_chunks = []
        client = get_openai_client()
        
        for i, chunk in enumerate(chunks):
            logger.info(f"正在翻译第 {i+1}/{len(chunks)} 块...")
            
            system_prompt = f"""你是专业翻译专家。请将{source_lang_name}文本准确翻译为{target_lang_name}。

这是完整文档的第{i+1}部分，共{len(chunks)}部分。

翻译要求：
- 保持原文的格式和结构
- 准确传达原意，语言自然流畅
- 保留专业术语的准确性
- 不要添加解释或注释
- 保持与前后文的连贯性"""

            user_prompt = f"""请将以下{source_lang_name}文本翻译为{target_lang_name}：

{chunk}

只返回翻译结果。"""

            try:
                response = client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=self.config.translation_max_tokens,
                    temperature=self.config.translation_temperature
                )
                
                translated_chunk = response.choices[0].message.content
                translated_chunks.append(translated_chunk)
                
            except Exception as e:
                logger.error(f"翻译第 {i+1} 块失败: {e}")
                # 失败时保留原文
                translated_chunks.append(chunk)
        
        # 合并翻译结果
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
