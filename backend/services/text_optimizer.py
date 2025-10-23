"""
文本优化服务
优化转录文本：修正错别字、按含义分段
"""
import logging
import asyncio
import re
from typing import Optional

from backend.core.ai_client import get_openai_client, is_openai_available
from backend.config.ai_config import get_openai_config
from backend.utils.text_processor import detect_language, smart_chunk_text, format_markdown_paragraphs, remove_transcript_headings, enforce_paragraph_length

logger = logging.getLogger(__name__)


class TextOptimizer:
    """文本优化服务"""
    
    def __init__(self):
        """初始化文本优化服务"""
        self.config = get_openai_config()
    
    async def optimize_transcript(self, raw_transcript: str) -> str:
        """
        优化转录文本：修正错别字，按含义分段
        
        Args:
            raw_transcript: 原始转录文本
            
        Returns:
            优化后的转录文本（Markdown格式）
        """
        try:
            if not is_openai_available():
                logger.warning("OpenAI API不可用，返回清理后的原始转录")
                return self._basic_transcript_cleanup(raw_transcript)
            
            # 预处理：移除时间戳与元信息
            preprocessed = self._remove_timestamps_and_meta(raw_transcript)
            
            # 检测语言
            detected_lang = detect_language(preprocessed)
            max_chars_per_chunk = 4000
            
            if len(preprocessed) > max_chars_per_chunk:
                logger.info(f"文本较长({len(preprocessed)} chars)，启用分块优化")
                return await self._format_long_transcript_in_chunks(preprocessed, detected_lang, max_chars_per_chunk)
            else:
                return await self._format_single_chunk(preprocessed, detected_lang)
                
        except Exception as e:
            logger.error(f"优化转录文本失败: {str(e)}")
            logger.info("返回清理后的原始转录文本")
            return self._basic_transcript_cleanup(raw_transcript)
    
    def _remove_timestamps_and_meta(self, text: str) -> str:
        """移除时间戳行与元信息"""
        lines = text.split('\n')
        kept = []
        for line in lines:
            s = line.strip()
            # 跳过时间戳、标题、元信息、source链接
            if (s.startswith('**[') and s.endswith(']**')):
                continue
            if s.startswith('# '):
                continue
            if s.startswith('**检测语言:**') or s.startswith('**语言概率:**'):
                continue
            if s.startswith('**Detected Language:**') or s.startswith('**Language Probability:**'):
                continue
            if s.startswith('source:') or s.startswith('Source:'):
                continue
            if s.startswith('##'):
                continue
            kept.append(line)
        return '\n'.join(kept)
    
    async def _format_single_chunk(self, chunk_text: str, transcript_language: str = 'zh') -> str:
        """格式化单个文本块"""
        if transcript_language == 'zh':
            prompt = (
                "请对以下音频转录文本进行智能优化和格式化，要求：\n\n"
                "**内容优化（正确性优先）：**\n"
                "1. 错误修正（转录错误/错别字/同音字/专有名词/错误的英文单词）\n"
                "2. 适度改善语法，补全不完整句子，保持原意和语言不变\n"
                "3. 口语处理：保留自然口语与重复表达，不要删减内容，仅添加必要标点\n"
                "4. **绝对不要改变人称代词（I/我、you/你等）和说话者视角**\n\n"
                "**分段规则：**\n"
                "- 按主题和逻辑含义分段，每段包含1-8个相关句子\n"
                "- 单段长度不超过400字符（中文计为1字符）\n"
                "- 避免过多短段落（连续<3句的段落强制合并）\n"
                "- 遇到转折词（但是/另外/不过）自动换段\n\n"
                "**输出要求：**\n"
                "- **直接输出优化后的正文内容，不要添加任何标题（如转录内容优化、优化内容等）**\n"
                "- **不要添加修改日志、注释或任何额外说明**\n"
                "- Markdown标准段落（段间空行）\n"
                "- 保留原始换行符和缩进\n"
                "- 中英文混用不做统一化处理\n\n"
                f"原始转录文本：\n{chunk_text}"
            )
            system_prompt = (
                "你是专业的音频转录文本优化助手，修正错误、改善通顺度和排版格式，"
                "必须保持原意，不得删减口语/重复/细节；仅移除时间戳或元信息。"
                "绝对不要改变人称代词或说话者视角。"
            )
        else:
            prompt = (
                "Please intelligently optimize and format the following audio transcript with these requirements:\n\n"
                "**Content Optimization (Accuracy First):**\n"
                "1. Error correction (transcription errors/typos/homophones/proper nouns/incorrect English words)\n"
                "2. Moderate grammar improvement, complete fragmented sentences while preserving original meaning\n"
                "3. Spoken language processing: Retain natural speech patterns and repetitions, no content deletion, only add essential punctuation\n"
                "4. **Absolutely DO NOT alter personal pronouns (I/me, you, etc.) or speaker perspective**\n\n"
                "**Paragraph Rules:**\n"
                "- Segment by topic and logical meaning (1-8 related sentences per paragraph)\n"
                "- Maximum 400 characters per paragraph (Chinese characters count as 1)\n"
                "- Avoid excessive short paragraphs (merge consecutive paragraphs with <3 sentences)\n"
                "- Automatic paragraph break at transition words (but/however/additionally)\n\n"
                "**Output Requirements:**\n"
                "- **Output optimized text directly WITHOUT any titles (like 'Optimized Content', 'Transcript Optimization', etc.)**\n"
                "- **Do NOT add modification logs, comments, or any extra explanations**\n"
                "- Standard Markdown paragraphs (blank lines between)\n"
                "- Preserve original line breaks and indentation\n"
                "- No standardization of Chinese-English mixed usage\n\n"
                f"Original Transcript:\n{chunk_text}"
            )
            system_prompt = (
                "You are a professional transcript formatting assistant. Fix errors and improve fluency "
                "without changing meaning or removing content. NEVER change pronouns or speaker perspective."
            )
        
        try:
            client = get_openai_client()
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.config.optimization_max_tokens,
                temperature=self.config.optimization_temperature
            )
            optimized_text = response.choices[0].message.content or ""
            optimized_text = remove_transcript_headings(optimized_text)
            enforced = enforce_paragraph_length(optimized_text.strip(), max_chars=400)
            return format_markdown_paragraphs(enforced)
        except Exception as e:
            logger.error(f"单块文本优化失败: {e}")
            return self._basic_transcript_cleanup(chunk_text)
    
    async def _format_long_transcript_in_chunks(
        self,
        raw_transcript: str,
        transcript_language: str,
        max_chars_per_chunk: int
    ) -> str:
        """智能分块+上下文+去重合成优化文本"""
        # 使用统一的分块函数
        chunks = smart_chunk_text(raw_transcript, max_chars_per_chunk, prefer_paragraphs=True)
        logger.info(f"文本分为 {len(chunks)} 块处理")
        
        optimized = []
        client = get_openai_client()
        
        for i, c in enumerate(chunks):
            # 添加上下文
            chunk_with_context = c
            if i > 0:
                prev_tail = chunks[i - 1][-100:]
                marker = f"[上文续：{prev_tail}]" if transcript_language == 'zh' else f"[Context: {prev_tail}]"
                chunk_with_context = marker + "\n\n" + c
            
            try:
                oc = await self._format_single_chunk(chunk_with_context, transcript_language)
                # 移除上下文标记
                oc = re.sub(r"^\[(上文续|Context)：?:?.*?\]\s*", "", oc, flags=re.S)
                optimized.append(oc)
            except Exception as e:
                logger.warning(f"第 {i+1} 块优化失败: {e}")
                optimized.append(self._basic_transcript_cleanup(c))
        
        # 邻接块去重
        deduped = []
        for i, c in enumerate(optimized):
            cur_txt = c
            if i > 0 and deduped:
                prev = deduped[-1]
                overlap = self._find_overlap(prev[-200:], cur_txt[:200])
                if overlap:
                    cur_txt = cur_txt[len(overlap):].lstrip()
                    if not cur_txt:
                        continue
            if cur_txt.strip():
                deduped.append(cur_txt)
        
        merged = "\n\n".join(deduped)
        merged = remove_transcript_headings(merged)
        enforced = enforce_paragraph_length(merged, max_chars=400)
        return format_markdown_paragraphs(enforced)
    
    def _find_overlap(self, text1: str, text2: str) -> str:
        """检测相邻两段的重叠内容"""
        max_len = min(len(text1), len(text2))
        for length in range(max_len, 19, -1):
            if text1[-length:] == text2[:length]:
                return text2[:length]
        return ""
    
    def _basic_transcript_cleanup(self, raw_transcript: str) -> str:
        """基本清理：移除时间戳，简单分段"""
        lines = raw_transcript.split('\n')
        cleaned_lines = []
        
        for line in lines:
            s = line.strip()
            if s.startswith('**[') and s.endswith(']**'):
                continue
            if s.startswith('#'):
                continue
            if '**检测语言:**' in s or '**语言概率:**' in s:
                continue
            if '**Detected Language:**' in s or '**Language Probability:**' in s:
                continue
            if s:
                cleaned_lines.append(s)
        
        text = ' '.join(cleaned_lines)
        sentences = re.split(r'[.!?。！？]\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        paragraphs = []
        current = []
        for i, sentence in enumerate(sentences):
            current.append(sentence)
            if len(current) >= 3 or len(' '.join(current)) > 250:
                paragraphs.append('. '.join(current) + '.')
                current = []
        
        if current:
            paragraphs.append('. '.join(current) + '.')
        
        return '\n\n'.join(paragraphs)
    
    def is_available(self) -> bool:
        """
        检查文本优化服务是否可用
        
        Returns:
            True if OpenAI API可用
        """
        return is_openai_available()
    
    @staticmethod
    def _get_language_instruction(lang_code: str) -> str:
        """获取语言指令名称"""
        instructions = {
            "en": "English", "zh": "中文", "ja": "日本語",
            "ko": "한국어", "es": "Español", "fr": "Français",
            "de": "Deutsch", "it": "Italiano", "pt": "Português",
            "ru": "Русский", "ar": "العربية"
        }
        return instructions.get(lang_code, "English")
