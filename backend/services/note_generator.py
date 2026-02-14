"""
笔记生成服务

整合所有服务的主流程，生成完整的视频笔记。
"""

import logging
import asyncio
import re
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import aiofiles

from backend.services.video_downloader import VideoDownloader
from backend.services.audio_transcriber import AudioTranscriber
from backend.services.text_optimizer import TextOptimizer
from backend.services.content_summarizer import ContentSummarizer
from backend.services.text_translator import TextTranslator
from backend.utils.file_handler import sanitize_filename

logger = logging.getLogger(__name__)


class NoteGenerator:
    """
    笔记生成服务 - 整合所有服务生成完整视频笔记
    
    完整流程：
    1. 下载视频音频
    2. 转录音频
    3. 优化转录文本
    4. 生成摘要
    5. 翻译（如需要）
    6. 生成Markdown文件
    7. 清理临时文件
    """
    
    def __init__(self):
        """初始化笔记生成服务"""
        self.video_downloader = VideoDownloader()
        self.audio_transcriber = AudioTranscriber()
        self.text_optimizer = TextOptimizer()
        self.content_summarizer = ContentSummarizer()
        self.text_translator = TextTranslator()
    
    async def generate_note(
        self,
        video_url: str,
        temp_dir: Path,
        summary_language: str = "zh",
        progress_callback=None,
        cancel_check: Optional[Callable[[], bool]] = None,
        audio_path_override: Optional[str] = None,
        video_title_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        生成完整的视频笔记
        
        Args:
            video_url: 视频URL
            temp_dir: 临时文件目录
            summary_language: 摘要语言代码
            progress_callback: 进度回调函数 callback(progress: int, message: str)
            cancel_check: 取消检查函数 cancel_check() -> bool
            
        Returns:
            包含所有结果的字典：
            {
                "video_title": str,           # 视频标题
                "raw_transcript": str,        # 原始转录
                "optimized_transcript": str,  # 优化后的转录
                "summary": str,               # 摘要
                "translation": str,           # 翻译（如果有）
                "detected_language": str,     # 检测到的语言
                "files": {
                    "raw_transcript_path": Path,
                    "transcript_path": Path,
                    "summary_path": Path,
                    "translation_path": Path  # 如果有
                }
            }
        """
        try:
            # 步骤1: 获取音频
            if audio_path_override:
                audio_path = audio_path_override
                video_title = video_title_override or Path(audio_path_override).stem
                await self._update_progress(progress_callback, 35, "✅ 音频已就绪，开始处理...")
            else:
                await self._update_progress(progress_callback, 10, "🎬 正在获取并分析视频资源...")
                await asyncio.sleep(0.1)
                self._check_cancelled(cancel_check)

                audio_path, video_title = await self.video_downloader.download_video_audio(
                    video_url, temp_dir
                )
                await self._update_progress(progress_callback, 35, "✅ 解析视频成功，开始处理...")

            self._check_cancelled(cancel_check)
            
            # 步骤2: 转录音频
            await self._update_progress(progress_callback, 37, "🤖 正在加载 Whisper 模型...")
            await asyncio.sleep(0.1)
            self._check_cancelled(cancel_check)
            
            await self._update_progress(progress_callback, 40, "🎤 ViNote正在原文转录...")
            await asyncio.sleep(0.2)
            self._check_cancelled(cancel_check)
            
            # 转录任务（注意：这会在线程池中运行，无法被asyncio.CancelledError中断）
            # 但我们在转录完成后会立即检查取消状态
            raw_transcript = await self.audio_transcriber.transcribe_audio(
                audio_path,
                video_title=video_title,
                video_url=video_url,
                cancel_check=cancel_check
            )
            
            # 转录完成后立即检查是否已取消（关键检查点）
            self._check_cancelled(cancel_check)
            detected_language = self.audio_transcriber.get_detected_language(raw_transcript)
            
            # 生成短ID和安全文件名
            import uuid
            short_id = str(uuid.uuid4()).replace("-", "")[:6]
            safe_title = self._sanitize_title(video_title)
            
            # 保存原始转录
            raw_md_filename = f"raw_{safe_title}_{short_id}.md"
            raw_md_path = temp_dir / raw_md_filename
            await self._save_file(raw_md_path, raw_transcript)
            
            # 步骤3: 优化转录文本
            await self._update_progress(progress_callback, 55, "✍️ ViNote正在整理完整笔记...")
            await asyncio.sleep(0.2)
            self._check_cancelled(cancel_check)
            
            optimized_transcript = await self.text_optimizer.optimize_transcript(raw_transcript)
            
            # 为优化后的转录添加标题和来源（简洁格式）
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            transcript_with_meta = f"""# {video_title}

> 🔗 **视频来源：** [点击观看]({video_url})

---

{optimized_transcript}

---

*整理时间：{current_time}*  
*由 ViNote AI 自动生成*
"""
            
            # 保存优化后的转录
            transcript_filename = f"transcript_{safe_title}_{short_id}.md"
            transcript_path = temp_dir / transcript_filename
            await self._save_file(transcript_path, transcript_with_meta)
            
            # 步骤4: 检查是否需要翻译
            translation_content = None
            translation_path = None
            translation_with_meta = None
            
            if detected_language and self.text_translator.should_translate(
                detected_language, summary_language
            ):
                logger.info(f"需要翻译: {detected_language} -> {summary_language}")
                
                await self._update_progress(progress_callback, 70, "🌐 正在翻译为目标语言...")
                await asyncio.sleep(0.2)
                self._check_cancelled(cancel_check)
                
                # 翻译转录文本
                translation_content = await self.text_translator.translate_text(
                    optimized_transcript, summary_language, detected_language
                )

                # 为翻译添加格式化的元信息
                translation_with_meta = f"""# {video_title}

> 🔗 **视频来源：** [点击观看]({video_url})
> 
> 🌐 **翻译语言：** {summary_language}

---

{translation_content}

---

*翻译时间：{current_time}*  
*由 ViNote AI 自动生成*
"""
                
                # 保存翻译
                translation_filename = f"translation_{safe_title}_{short_id}.md"
                translation_path = temp_dir / translation_filename
                await self._save_file(translation_path, translation_with_meta)
            else:
                logger.info(f"不需要翻译: detected={detected_language}, target={summary_language}")
            
            # 步骤5: 生成摘要
            await self._update_progress(progress_callback, 80, "📝 ViNote正在提炼摘要...")
            await asyncio.sleep(0.2)
            self._check_cancelled(cancel_check)
            
            summary = await self.content_summarizer.summarize(
                optimized_transcript, summary_language, video_title
            )
            
            # 步骤6: 生成思维导图
            await self._update_progress(progress_callback, 90, "🧠 正在绘制思维导图...")
            self._check_cancelled(cancel_check)
            
            mindmap = await self.content_summarizer.generate_mindmap(
                summary, summary_language
            )
            
            mindmap_filename = None
            mindmap_path = None
            if mindmap:
                mindmap_filename = f"mindmap_{safe_title}_{short_id}.md"
                mindmap_path = temp_dir / mindmap_filename
                await self._save_file(mindmap_path, mindmap)
            
            summary_with_meta = f"""# {video_title}

> 🔗 **视频来源：** [点击观看]({video_url})

---

{summary}

---

*生成时间：{current_time}*  
*由 ViNote AI 自动生成*
"""
            
            summary_filename = f"summary_{safe_title}_{short_id}.md"
            summary_path = temp_dir / summary_filename
            await self._save_file(summary_path, summary_with_meta)
            
            # 步骤7: 完成
            await self._update_progress(progress_callback, 100, "✨ 所有处理已完成！")
            
            result = {
                "video_title": video_title,
                "raw_transcript": raw_transcript,
                "optimized_transcript": transcript_with_meta,
                "summary": summary_with_meta,
                "mindmap": mindmap or "",
                "detected_language": detected_language,
                "summary_language": summary_language,
                "short_id": short_id,
                "safe_title": safe_title,
                "files": {
                    "raw_transcript_path": raw_md_path,
                    "raw_transcript_filename": raw_md_filename,
                    "transcript_path": transcript_path,
                    "transcript_filename": transcript_filename,
                    "summary_path": summary_path,
                    "summary_filename": summary_filename,
                    "mindmap_path": mindmap_path,
                    "mindmap_filename": mindmap_filename,
                }
            }
            
            if translation_content and translation_path and translation_with_meta:
                result["translation"] = translation_with_meta
                result["files"]["translation_path"] = translation_path
                result["files"]["translation_filename"] = translation_path.name
            
            logger.info(f"笔记生成完成: {video_title}")
            return result
            
        except asyncio.CancelledError:
            logger.info("笔记生成被用户取消")
            await self._update_progress(
                progress_callback, -1, "❌ 任务已取消"
            )
            raise
        except Exception as e:
            logger.error(f"生成笔记失败: {str(e)}")
            await self._update_progress(
                progress_callback, -1, f"❌ 处理失败: {str(e)}"
            )
            raise
    
    def _check_cancelled(self, cancel_check: Optional[Callable[[], bool]]):
        """检查是否已取消"""
        if cancel_check and cancel_check():
            raise asyncio.CancelledError("任务已被取消")
    
    async def _update_progress(
        self,
        callback: Optional[Callable[[int, str], None]],
        progress: int,
        message: str
    ):
        """更新进度"""
        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(progress, message)
                else:
                    callback(progress, message)
            except Exception as e:
                logger.warning(f"进度回调失败: {e}")
    
    def _sanitize_title(self, title: str) -> str:
        """清洗标题为安全的文件名"""
        if not title:
            return "untitled"
        
        # 使用统一的文件名清洗函数
        safe = sanitize_filename(title)
        
        # 额外处理：压缩空白并转为下划线
        safe = re.sub(r"\s+", "_", safe).strip("._-")
        
        # 最长限制
        return safe[:80] or "untitled"
    
    async def _save_file(self, path: Path, content: str):
        """保存文件"""
        try:
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
            logger.info(f"文件已保存: {path.name}")
        except Exception as e:
            logger.error(f"保存文件失败 {path.name}: {e}")
            raise
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return (
            self.audio_transcriber.is_available() and
            self.text_optimizer.is_available() and
            self.content_summarizer.is_available()
        )
    
    def get_service_status(self) -> Dict[str, bool]:
        """获取各服务的状态"""
        return {
            "audio_transcriber": self.audio_transcriber.is_available(),
            "text_optimizer": self.text_optimizer.is_available(),
            "content_summarizer": self.content_summarizer.is_available(),
            "text_translator": self.text_translator.is_available(),
        }
