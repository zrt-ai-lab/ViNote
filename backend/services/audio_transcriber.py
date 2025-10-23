"""
音频转录服务
使用Faster-Whisper进行语音转文字
"""
import os
import logging
import asyncio
from typing import Optional

from backend.core.ai_client import get_whisper_model
from backend.config.ai_config import get_whisper_config

logger = logging.getLogger(__name__)


class AudioTranscriber:
    """音频转录服务"""
    
    def __init__(self):
        """初始化转录服务"""
        self.config = get_whisper_config()
        self.last_detected_language: Optional[str] = None
    
    async def transcribe_audio(
        self,
        audio_path: str,
        language: Optional[str] = None,
        video_title: str = "",
        video_url: str = ""
    ) -> str:
        """
        转录音频文件
        
        Args:
            audio_path: 音频文件路径
            language: 指定语言（可选，如果不指定则自动检测）
            video_title: 视频标题（可选）
            video_url: 视频URL（可选）
            
        Returns:
            转录文本（Markdown格式）
            
        Raises:
            Exception: 转录失败
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(audio_path):
                raise Exception(f"音频文件不存在: {audio_path}")
            
            logger.info(f"开始转录音频: {audio_path}")
            
            # 获取Whisper模型（单例）
            logger.info(f"🤖 正在加载 Whisper 模型: {self.config.model_size}")
            model = get_whisper_model()
            logger.info("✅ Whisper 模型加载完成")
            
            # 在线程池中执行转录（避免阻塞事件循环）
            segments, info = await asyncio.to_thread(
                self._do_transcribe,
                model,
                audio_path,
                language
            )
            
            # 保存检测到的语言
            detected_language = info.language
            self.last_detected_language = detected_language
            logger.info(f"检测到的语言: {detected_language}")
            logger.info(f"语言检测概率: {info.language_probability:.2f}")
            
            # 组装转录结果
            transcript_text = self._format_transcript(
                segments,
                detected_language,
                info.language_probability,
                video_title,
                video_url
            )
            
            logger.info("转录完成")
            return transcript_text
            
        except Exception as e:
            logger.error(f"转录失败: {str(e)}")
            raise Exception(f"转录失败: {str(e)}")
    
    def _do_transcribe(self, model, audio_path: str, language: Optional[str]):
        """
        执行实际的转录操作（在线程中运行）
        
        Args:
            model: Whisper模型实例
            audio_path: 音频文件路径
            language: 指定语言
            
        Returns:
            (segments, info) 转录片段和信息
        """
        return model.transcribe(
            audio_path,
            language=language,
            beam_size=self.config.beam_size,
            best_of=self.config.best_of,
            temperature=self.config.temperature,
            # VAD参数（降低静音/噪音导致的重复）
            vad_filter=self.config.vad_filter,
            vad_parameters={
                "min_silence_duration_ms": self.config.min_silence_duration_ms,
                "speech_pad_ms": self.config.speech_pad_ms
            },
            # 阈值参数
            no_speech_threshold=self.config.no_speech_threshold,
            compression_ratio_threshold=self.config.compression_ratio_threshold,
            log_prob_threshold=self.config.log_prob_threshold,
            # 避免错误累积导致的连环重复
            condition_on_previous_text=self.config.condition_on_previous_text
        )
    
    def _format_transcript(
        self,
        segments,
        detected_language: str,
        language_probability: float,
        video_title: str = "",
        video_url: str = ""
    ) -> str:
        """
        格式化转录结果为Markdown
        
        Args:
            segments: 转录片段
            detected_language: 检测到的语言
            language_probability: 语言检测概率
            video_title: 视频标题
            video_url: 视频URL
            
        Returns:
            格式化的Markdown文本
        """
        from datetime import datetime
        
        # 语言名称映射
        language_names = {
            'zh': '中文',
            'en': 'English',
            'ja': '日本語',
            'ko': '한국어',
            'es': 'Español',
            'fr': 'Français',
            'de': 'Deutsch',
            'it': 'Italiano',
            'pt': 'Português',
            'ru': 'Русский',
            'ar': 'العربية',
            'hi': 'हिन्दी',
            'th': 'ไทย',
            'vi': 'Tiếng Việt',
            'tr': 'Türkçe',
            'pl': 'Polski',
            'nl': 'Nederlands',
            'sv': 'Svenska',
            'da': 'Dansk',
            'no': 'Norsk'
        }
        
        lang_display = language_names.get(detected_language, detected_language)
        
        lines = []
        lines.append("# 视频转录文本")
        lines.append("")
        
        # 视频信息块
        if video_title or video_url:
            lines.append(f"> 📹 **视频标题：** {video_title or '未知'}")
            lines.append("> ")
            lines.append(f"> 🌐 **检测语言：** {lang_display} ({detected_language})")
            lines.append("> ")
            if video_url:
                lines.append(f"> 🔗 **视频来源：** [点击观看]({video_url})")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        lines.append("## 📝 转录内容")
        lines.append("")
        
        # 添加时间戳和文本
        for segment in segments:
            start_time = self._format_time(segment.start)
            end_time = self._format_time(segment.end)
            text = segment.text.strip()
            
            lines.append(f"**{start_time} - {end_time}**  ")
            lines.append(text)
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # 页脚信息
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines.append(f"*转录时间：{current_time}*  ")
        lines.append("*由 ViNote AI 自动生成*")
        
        return "\n".join(lines)
    
    def _format_time(self, seconds: float) -> str:
        """
        将秒数转换为时分秒格式
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化的时间字符串 (HH:MM:SS 或 MM:SS)
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def get_detected_language(self, transcript_text: Optional[str] = None) -> Optional[str]:
        """
        获取检测到的语言
        
        Args:
            transcript_text: 转录文本（可选，用于从文本中提取语言信息）
            
        Returns:
            检测到的语言代码
        """
        # 如果有保存的语言，直接返回
        if self.last_detected_language:
            return self.last_detected_language
        
        # 如果提供了转录文本，尝试从中提取语言信息
        if transcript_text and "**Detected Language:**" in transcript_text:
            lines = transcript_text.split('\n')
            for line in lines:
                if "**Detected Language:**" in line:
                    lang = line.split(":")[-1].strip()
                    return lang
        
        return None
    
    def is_available(self) -> bool:
        """
        检查转录服务是否可用
        
        Returns:
            True if Whisper模型可用
        """
        try:
            model = get_whisper_model()
            return model is not None
        except Exception as e:
            logger.error(f"检查Whisper模型可用性失败: {e}")
            return False
    
    @staticmethod
    def get_supported_languages() -> list:
        """
        获取支持的语言列表
        
        Returns:
            支持的语言代码列表
        """
        return [
            "zh", "en", "ja", "ko", "es", "fr", "de", "it", "pt", "ru",
            "ar", "hi", "th", "vi", "tr", "pl", "nl", "sv", "da", "no"
        ]
