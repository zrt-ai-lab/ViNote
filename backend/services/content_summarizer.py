"""
内容摘要服务

从summarizer.py提取的摘要功能，使用统一的配置和工具函数。
"""

import logging
import asyncio
import re
from typing import Optional

from backend.config.ai_config import get_openai_config
from backend.core.ai_client import get_openai_client
from backend.utils.text_processor import estimate_tokens, smart_chunk_text

logger = logging.getLogger(__name__)

MAX_CONCURRENT_CHUNKS = 5
MAX_MERGE_INPUT_CHARS = 10000
MAX_MERGE_LEVELS = 8


class ContentSummarizer:
    """内容摘要服务"""
    
    def __init__(self):
        """初始化摘要服务"""
        self.config = get_openai_config()
        self.client = get_openai_client()
        self.warnings: list[str] = []
        
        # 支持的语言映射
        self.language_map = {
            "en": "English",
            "zh": "中文（简体）",
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch",
            "it": "Italiano",
            "pt": "Português",
            "ru": "Русский",
            "ja": "日本語",
            "ko": "한국어",
            "ar": "العربية"
        }

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
    
    async def summarize(
        self,
        transcript: str,
        target_language: str = "zh",
        video_title: Optional[str] = None
    ) -> str:
        """
        生成视频转录的摘要
        
        Args:
            transcript: 转录文本
            target_language: 目标语言代码
            video_title: 视频标题（可选）
            
        Returns:
            摘要文本（Markdown格式）
        """
        self.warnings.clear()
        try:
            if not self.client:
                logger.warning("OpenAI API不可用，生成备用摘要")
                self._warn("LLM 未配置，摘要使用备用版本")
                return self._generate_fallback_summary(transcript, target_language, video_title)
            
            # 估算转录文本长度
            estimated_tokens = self._estimate_tokens(transcript)
            max_summarize_tokens = 4000
            
            if estimated_tokens <= max_summarize_tokens:
                # 短文本直接摘要
                summary = await self._summarize_single_text(transcript, target_language, video_title)
            else:
                # 长文本分块摘要
                logger.info(f"文本较长({estimated_tokens} tokens)，启用分块摘要")
                summary = await self._summarize_with_chunks(
                    transcript, target_language, video_title, max_summarize_tokens
                )
            if summary and summary.strip():
                return summary
            logger.warning("AI 返回空摘要，生成备用摘要")
            self._warn("LLM 返回空内容，摘要使用备用版本")
            return self._generate_fallback_summary(transcript, target_language, video_title)
            
        except Exception as e:
            logger.error(f"生成摘要失败: {str(e)}")
            self._warn("LLM 摘要失败，摘要使用备用版本")
            return self._generate_fallback_summary(transcript, target_language, video_title)
    
    async def _summarize_single_text(
        self,
        transcript: str,
        target_language: str,
        video_title: Optional[str] = None
    ) -> str:
        """对单个文本进行摘要"""
        language_name = self.language_map.get(target_language, "中文（简体）")
        
        system_prompt = f"""You are a professional content analyst. Please generate a comprehensive, well-structured summary in {language_name} for the following text.

Summary Requirements:
1. Extract the main topics and core viewpoints from the text
2. Maintain clear logical structure, highlighting the core arguments
3. Include important discussions, viewpoints, and conclusions
4. Use concise and clear language
5. Appropriately preserve the speaker's expression style and key opinions

Paragraph Organization Requirements (Core):
1. **Organize by semantic and logical themes** - Start a new paragraph whenever the topic shifts
2. **Each paragraph should focus on one main point or theme**
3. **Paragraphs must be separated by blank lines (double line breaks \\n\\n)**
4. **Consider the logical flow of content and reasonably divide paragraph boundaries**

Format Requirements:
1. Use Markdown format with double line breaks between paragraphs
2. Each paragraph should be a complete logical unit
3. Write entirely in {language_name}
4. Aim for substantial content (600-1200 words when appropriate)"""

        user_prompt = f"""Based on the following content, write a comprehensive, well-structured summary in {language_name}:

{transcript}

Requirements:
- Focus on natural paragraphs, avoiding decorative headings
- Cover all key ideas and arguments, preserving important examples and data
- Ensure balanced coverage of both early and later content
- Use restrained but comprehensive language
- Organize content logically with proper paragraph breaks"""

        logger.info(f"正在生成{language_name}摘要...")
        
        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=3500,
            temperature=0.3,
            timeout=60.0
        )
        
        summary = response.choices[0].message.content
        return self._format_summary_with_meta(summary, target_language, video_title)
    
    async def _summarize_with_chunks(
        self,
        transcript: str,
        target_language: str,
        video_title: Optional[str],
        max_tokens: int
    ) -> str:
        """分块并行摘要长文本"""
        language_name = self.language_map.get(target_language, "中文（简体）")

        chunks = self._smart_chunk_text(transcript, max_chars_per_chunk=4000)
        total = len(chunks)
        logger.info(f"分割为 {total} 个块并行摘要")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

        async def _summarize_chunk(i: int, chunk: str) -> str:
            system_prompt = f"""You are a summarization expert. Please write a high-density summary for this text chunk in {language_name}.

This is part {i+1} of {total} of the complete content.

Output preferences: Focus on natural paragraphs, use minimal bullet points if necessary; highlight new information and its relationship to the main narrative; avoid vague repetition and formatted headings; moderate length (suggested 120-220 words)."""

            user_prompt = f"""[Part {i+1}/{total}] Summarize the key points of the following text in {language_name} (natural paragraphs preferred, minimal bullet points, 120-220 words):

{chunk}

Avoid using any subheadings or decorative separators, output content only."""

            async with semaphore:
                try:
                    response = await asyncio.to_thread(
                        self.client.chat.completions.create,
                        model=self.config.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        max_tokens=1000,
                        temperature=0.3,
                        timeout=60.0
                    )
                    content = (response.choices[0].message.content or "").strip()
                    if not content:
                        raise ValueError("分块摘要为空")
                    return content
                except Exception as e:
                    logger.error(f"摘要第 {i+1} 块失败: {e}")
                    self._warn("部分摘要生成失败，已使用原文片段")
                    return chunk

        chunk_summaries = await asyncio.gather(*[_summarize_chunk(i, c) for i, c in enumerate(chunks)])
        chunk_summaries = list(chunk_summaries)

        logger.info("正在整合最终摘要...")
        final_summary = await self._integrate_hierarchical_summaries(
            chunk_summaries, target_language
        )

        return self._format_summary_with_meta(final_summary, target_language, video_title)
    
    async def _integrate_chunk_summaries(
        self,
        combined_summaries: str,
        target_language: str
    ) -> str:
        """整合分块摘要为最终连贯摘要"""
        if len(combined_summaries) > MAX_MERGE_INPUT_CHARS:
            return await self._integrate_hierarchical_summaries(
                [combined_summaries], target_language
            )
        language_name = self.language_map.get(target_language, "中文（简体）")
        
        try:
            system_prompt = f"""You are a content integration expert. Please integrate multiple segmented summaries into a complete, coherent summary in {language_name}.

Integration Requirements:
1. Remove duplicate content and maintain clear logic
2. Reorganize content by themes or chronological order
3. Each paragraph must be separated by double line breaks
4. Ensure output is in Markdown format with double line breaks between paragraphs
5. Use concise and clear language
6. Form a complete content summary
7. Cover all parts comprehensively without omission"""

            user_prompt = f"""Please integrate the following segmented summaries into a complete, coherent summary in {language_name}:

{combined_summaries}

Requirements:
- Remove duplicate content and maintain clear logic
- Reorganize content by themes or chronological order
- Each paragraph must be separated by double line breaks
- Ensure output is in Markdown format with double line breaks between paragraphs
- Use concise and clear language
- Form a complete content summary"""

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=2500,
                temperature=0.3
            )
            
            content = (response.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("整合摘要为空")
            return content
            
        except Exception as e:
            logger.error(f"整合摘要失败: {e}")
            self._warn("摘要整合失败，已保留分块结果")
            return combined_summaries
    
    async def _integrate_hierarchical_summaries(
        self,
        chunk_summaries: list,
        target_language: str
    ) -> str:
        """逐层归并，任何一次模型请求的资料都不超过固定预算。"""
        combined = "\n\n".join(
            f"[Part {i + 1}]\n{summary.strip()}"
            for i, summary in enumerate(chunk_summaries)
            if summary and summary.strip()
        )
        if not combined:
            return ""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

        async def merge_group(group: str) -> str:
            async with semaphore:
                return await self._integrate_chunk_summaries(group, target_language)

        for _ in range(MAX_MERGE_LEVELS):
            if len(combined) <= MAX_MERGE_INPUT_CHARS:
                return await self._integrate_chunk_summaries(combined, target_language)
            groups = smart_chunk_text(combined, MAX_MERGE_INPUT_CHARS)
            merged = await asyncio.gather(*(merge_group(group) for group in groups))
            next_level = "\n\n".join(merged)
            if len(next_level) >= len(combined):
                # 上游失败会返回原文；停止重试并完整保留已有材料，避免无限归并。
                self._warn("摘要整合未能压缩内容，已保留分块结果")
                return next_level
            combined = next_level
        self._warn("摘要内容较长，已保留分层整理结果")
        return combined
    
    def _smart_chunk_text(self, text: str, max_chars_per_chunk: int = 3500) -> list:
        """复用无损且有长度上限的公共分块函数。"""
        return smart_chunk_text(text, max_chars_per_chunk)
    
    def _estimate_tokens(self, text: str) -> int:
        """估算token数量"""
        return estimate_tokens(text)
    
    def _format_summary_with_meta(
        self,
        summary: str,
        target_language: str,
        video_title: Optional[str] = None
    ) -> str:
        """
        清理摘要格式（不添加标题，标题由note_generator统一添加）
        
        清理操作：
        1. 移除AI可能添加的语言标题（如 "## 中文（简体）总结"）
        2. 移除末尾的source链接
        3. 清理多余的空行
        """
        import re
        
        # 1. 移除可能的语言标题（各种变体）
        # 匹配类似 "## 中文（简体）总结" "## 中文总结" "## English Summary" 等
        summary = re.sub(
            r'^##?\s*(?:中文(?:（简体）)?|English|日本語|한국어|Español|Français|Deutsch|Italiano|Português|Русский)(?:\s*摘要|\s*总结|\s*Summary)?\s*\n+',
            '',
            summary,
            flags=re.MULTILINE | re.IGNORECASE
        )
        
        # 2. 移除末尾的source链接
        summary = re.sub(r'\n*source:\s*https?://\S+\s*$', '', summary, flags=re.IGNORECASE)
        
        # 3. 清理多余的空行（超过2个连续换行符）
        summary = re.sub(r'\n{3,}', '\n\n', summary)
        
        # 4. 清理首尾空白
        summary = summary.strip()
        
        # 注意：不在这里添加标题，标题由note_generator.py统一添加
        return summary
    
    def _generate_fallback_summary(
        self,
        transcript: str,
        target_language: str,
        video_title: Optional[str] = None
    ) -> str:
        """生成备用摘要（当OpenAI API不可用时）"""
        language_name = self.language_map.get(target_language, "中文（简体）")
        
        lines = transcript.split('\n')
        content_lines = [
            line for line in lines
            if line.strip() and not line.startswith('#') and not line.startswith('**')
        ]
        
        total_chars = sum(len(line) for line in content_lines)
        
        meta_labels = self._get_summary_labels(target_language)
        fallback_labels = self._get_fallback_labels(target_language)
        
        title = video_title if video_title else "Summary"
        
        summary = f"""# {title}

**{meta_labels['language_label']}:** {language_name}
**{fallback_labels['notice']}:** {fallback_labels['api_unavailable']}

## {fallback_labels['overview_title']}

**{fallback_labels['content_length']}:** {fallback_labels['about']} {total_chars} {fallback_labels['characters']}
**{fallback_labels['paragraph_count']}:** {len(content_lines)} {fallback_labels['paragraphs']}

## {fallback_labels['main_content']}

{fallback_labels['content_description']}

{fallback_labels['suggestions_intro']}

1. {fallback_labels['suggestion_1']}
2. {fallback_labels['suggestion_2']}
3. {fallback_labels['suggestion_3']}

## {fallback_labels['recommendations']}

- {fallback_labels['recommendation_1']}
- {fallback_labels['recommendation_2']}

<br/>

<p style="color: #888; font-style: italic; text-align: center; margin-top: 16px;"><em>{fallback_labels['fallback_disclaimer']}</em></p>"""
        
        return summary
    
    def _get_summary_labels(self, lang_code: str) -> dict:
        """获取摘要页面的多语言标签"""
        labels = {
            "en": {
                "language_label": "Summary Language",
                "disclaimer": "This summary is automatically generated by AI for reference only"
            },
            "zh": {
                "language_label": "摘要语言",
                "disclaimer": "本摘要由AI自动生成，仅供参考"
            }
        }
        return labels.get(lang_code, labels["en"])
    
    def _get_fallback_labels(self, lang_code: str) -> dict:
        """获取备用摘要的多语言标签"""
        labels = {
            "en": {
                "notice": "Notice",
                "api_unavailable": "OpenAI API is unavailable, this is a simplified summary",
                "overview_title": "Transcript Overview",
                "content_length": "Content Length",
                "about": "About",
                "characters": "characters",
                "paragraph_count": "Paragraph Count",
                "paragraphs": "paragraphs",
                "main_content": "Main Content",
                "content_description": "The transcript contains complete video speech content. Since AI summary cannot be generated currently, we recommend:",
                "suggestions_intro": "For detailed information, we suggest you:",
                "suggestion_1": "Review the complete transcript text for detailed information",
                "suggestion_2": "Focus on important paragraphs marked with timestamps",
                "suggestion_3": "Manually extract key points and takeaways",
                "recommendations": "Recommendations",
                "recommendation_1": "Configure OpenAI API key for better summary functionality",
                "recommendation_2": "Or use other AI services for text summarization",
                "fallback_disclaimer": "This is an automatically generated fallback summary"
            },
            "zh": {
                "notice": "注意",
                "api_unavailable": "由于OpenAI API不可用，这是一个简化的摘要",
                "overview_title": "转录概览",
                "content_length": "内容长度",
                "about": "约",
                "characters": "字符",
                "paragraph_count": "段落数量",
                "paragraphs": "段",
                "main_content": "主要内容",
                "content_description": "转录文本包含了完整的视频语音内容。由于当前无法生成智能摘要，建议您：",
                "suggestions_intro": "为获取详细信息，建议您：",
                "suggestion_1": "查看完整的转录文本以获取详细信息",
                "suggestion_2": "关注时间戳标记的重要段落",
                "suggestion_3": "手动提取关键观点和要点",
                "recommendations": "建议",
                "recommendation_1": "配置OpenAI API密钥以获得更好的摘要功能",
                "recommendation_2": "或者使用其他AI服务进行文本总结",
                "fallback_disclaimer": "本摘要为自动生成的备用版本"
            }
        }
        return labels.get(lang_code, labels["en"])
    
    def is_available(self) -> bool:
        """检查摘要服务是否可用"""
        return self.client is not None
    
    def get_supported_languages(self) -> dict:
        """获取支持的语言列表"""
        return self.language_map.copy()
    
    async def generate_mindmap(
        self,
        summary: str,
        target_language: str = "zh"
    ) -> str:
        """
        基于摘要生成 Markdown 思维导图代码
        格式为 Markdown 列表，适配 Markmap。
        
        Args:
            summary: 摘要内容
            target_language: 目标语言
            
        Returns:
            Markdown 列表字符串
        """
        try:
            if not self.client:
                self._warn("LLM 未配置，思维导图未生成")
                return ""
            
            language_name = self.language_map.get(target_language, "中文（简体）")
            
            system_prompt = f"""You are a visualization expert. Please generate a Mindmap structure using Markdown List syntax based on the provided summary content.

Requirements:
1. Use standard Markdown list syntax (`- `, `  - `, `    - `) to represent the tree structure.
2. The root node should be the main title as a level 1 heading `# Title` or just the first list item.
3. Use indentation to represent hierarchy.
4. Keep node text concise (keywords or short phrases).
5. Output ONLY the Markdown content (start with `#` or `-`), no code blocks or explanations.
6. Use {language_name} for node text.
"""

            user_prompt = f"""Based on the following summary, generate a Markdown Mindmap structure:

{summary}

Output ONLY the markdown content."""

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=2000,
                temperature=0.2
            )
            
            content = response.choices[0].message.content.strip()
            
            # 清理可能的代码块标记
            content = content.replace("```markdown", "").replace("```", "").strip()
            
            return content
            
        except Exception as e:
            logger.error(f"生成思维导图失败: {e}")
            self._warn("LLM 思维导图生成失败")
            return ""
