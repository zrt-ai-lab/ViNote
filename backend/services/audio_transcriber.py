"""
音频转录服务
使用多模型进行语音转文字
"""
import os
import logging
import asyncio
from typing import Optional
from types import SimpleNamespace

from backend.core.ai_client import get_asr_model
from backend.config.ai_config import get_asr_config

logger = logging.getLogger(__name__)

_transcribe_semaphore = asyncio.Semaphore(1)


class AudioTranscriber:
    """音频转录服务"""
    
    def __init__(self):
        """初始化转录服务"""
        self.config = get_asr_config()
        self.last_detected_language: Optional[str] = None
    
    async def transcribe_audio(
        self,
        audio_path: str,
        language: Optional[str] = None,
        video_title: str = "",
        video_url: str = "",
        cancel_check: Optional[callable] = None
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
            if not os.path.exists(audio_path):
                raise Exception(f"音频文件不存在: {audio_path}")
            
            logger.info(f"开始转录音频: {audio_path}")
            
            async with _transcribe_semaphore:
                provider = self.config.provider.lower()
                logger.info(f"🤖 正在加载 ASR 模型: {provider}:{self.config.model}")
                model = get_asr_model()
                logger.info("✅ ASR 模型加载完成")
                
                if provider == "whisper":
                    segments, info = await asyncio.to_thread(
                        self._do_whisper_transcribe,
                        model,
                        audio_path,
                        language
                    )
                elif provider == "funasr":
                    segments, info = await asyncio.to_thread(
                        self._do_funasr_transcribe,
                        model,
                        audio_path,
                        language
                    )
                elif provider == "qwen3":
                    segments, info = await asyncio.to_thread(
                        self._do_qwen_transcribe,
                        model,
                        audio_path,
                        language
                    )
                else:
                    raise Exception(f"不支持的ASR提供方: {self.config.provider}")
            
            # 保存检测到的语言
            detected_language = getattr(info, "language", None) or language or "unknown"
            language_probability = getattr(info, "language_probability", None)
            if language_probability is None:
                language_probability = 0.0
            self.last_detected_language = detected_language
            logger.info(f"检测到的语言: {detected_language}")
            logger.info(f"语言检测概率: {language_probability:.2f}")
            
            # 组装转录结果
            transcript_text = self._format_transcript(
                segments,
                detected_language,
                language_probability,
                video_title,
                video_url
            )
            
            logger.info("转录完成")
            return transcript_text
            
        except Exception as e:
            logger.error(f"转录失败: {str(e)}")
            raise Exception(f"转录失败: {str(e)}")
    
    def _do_whisper_transcribe(self, model, audio_path: str, language: Optional[str]):
        """
        执行实际的转录操作（在线程中运行）
        
        Args:
            model: Whisper模型实例
            audio_path: 音频文件路径
            language: 指定语言
            
        Returns:
            (segments, info) 转录片段和信息
        """
        whisper_config = self.config.whisper
        segments_generator, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=whisper_config.beam_size,
            best_of=whisper_config.best_of,
            temperature=whisper_config.temperature,
            # VAD参数（降低静音/噪音导致的重复）
            vad_filter=whisper_config.vad_filter,
            vad_parameters={
                "min_silence_duration_ms": whisper_config.min_silence_duration_ms,
                "speech_pad_ms": whisper_config.speech_pad_ms
            },
            # 阈值参数
            no_speech_threshold=whisper_config.no_speech_threshold,
            compression_ratio_threshold=whisper_config.compression_ratio_threshold,
            log_prob_threshold=whisper_config.log_prob_threshold,
            # 避免错误累积导致的连环重复
            condition_on_previous_text=whisper_config.condition_on_previous_text
        )
        
        # 收集所有segment并打印时间段信息
        segments_list = []
        segment_count = 0
        
        logger.info("=" * 60)
        logger.info("🎬 开始逐段处理音频")
        logger.info("=" * 60)
        
        for segment in segments_generator:
            segment_count += 1
            start_time = self._format_time(segment.start)
            end_time = self._format_time(segment.end)
            duration = segment.end - segment.start
            text_preview = segment.text.strip()[:50] + "..." if len(segment.text.strip()) > 50 else segment.text.strip()
            
            # 打印每个segment的详细信息
            logger.info(f"📝 片段 #{segment_count:03d} | {start_time} → {end_time} | 时长: {duration:.1f}s")
            logger.info(f"   内容: {text_preview}")
            logger.info("-" * 60)
            
            segments_list.append(segment)
        
        logger.info("=" * 60)
        logger.info(f"✅ 处理完成！共 {segment_count} 个片段")
        logger.info("=" * 60)
        
        return segments_list, info

    def _do_funasr_transcribe(self, model, audio_path: str, language: Optional[str]):
        model_id = self.config.model
        result = model.generate(
            input=[audio_path],
            cache={},
            language=language or "auto",
            batch_size=1
        )
            
        segments, detected_language = self._parse_funasr_result(result, language)
        info = SimpleNamespace(
            language=detected_language,
            language_probability=0.0
        )
        return segments, info

    def _do_qwen_transcribe(self, model, audio_path: str, language: Optional[str]):
        results = model.transcribe(
            audio=audio_path,
            language=language
        )
        segments, detected_language = self._parse_qwen_result(results, language)
        info = SimpleNamespace(
            language=detected_language,
            language_probability=0.0
        )
        return segments, info

    def _parse_funasr_result(self, result, fallback_language: Optional[str]):
        detected_language = fallback_language or "unknown"
        if isinstance(result, list) and result:
            item = result[0] if isinstance(result[0], dict) else {}
            detected_language = item.get("language") or item.get("lang") or detected_language
            sentence_info = item.get("sentence_info") or item.get("sentences")
            if sentence_info:
                segments = []
                for sentence in sentence_info:
                    text = (sentence.get("text") or "").strip()
                    if not text:
                        continue
                    start = self._normalize_timestamp(sentence.get("start") or sentence.get("start_time"), "ms")
                    end = self._normalize_timestamp(sentence.get("end") or sentence.get("end_time"), "ms")
                    segments.append(SimpleNamespace(start=start, end=end, text=text))
                if segments:
                    return segments, detected_language
            text = (item.get("text") or "").strip()
            if text:
                return self._build_single_segment(text), detected_language
        return self._build_single_segment(""), detected_language

    def _parse_qwen_result(self, results, fallback_language: Optional[str]):
        detected_language = fallback_language or "unknown"
        if isinstance(results, list) and results:
            res = results[0]
            if isinstance(res, dict):
                detected_language = res.get("language") or detected_language
                segments_data = res.get("segments")
                text = res.get("text")
            else:
                detected_language = getattr(res, "language", None) or detected_language
                segments_data = getattr(res, "segments", None)
                text = getattr(res, "text", None)
            if segments_data:
                segments = []
                for seg in segments_data:
                    if isinstance(seg, dict):
                        seg_text = seg.get("text")
                        start = seg.get("start_time", seg.get("start"))
                        end = seg.get("end_time", seg.get("end"))
                    else:
                        seg_text = getattr(seg, "text", None)
                        start = getattr(seg, "start_time", None) or getattr(seg, "start", None)
                        end = getattr(seg, "end_time", None) or getattr(seg, "end", None)
                    if not seg_text:
                        continue
                    segments.append(SimpleNamespace(
                        start=self._normalize_timestamp(start, "s"),
                        end=self._normalize_timestamp(end, "s"),
                        text=seg_text.strip()
                    ))
                if segments:
                    return segments, detected_language
            if text:
                return self._build_single_segment(str(text)), detected_language
        return self._build_single_segment(""), detected_language

    def _build_single_segment(self, text: str):
        return [SimpleNamespace(start=0.0, end=0.0, text=text)]

    def _normalize_timestamp(self, value, unit: str) -> float:
        if value is None:
            return 0.0
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        if unit == "ms":
            return number / 1000.0
        return number
    
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
            model = get_asr_model()
            return model is not None
        except Exception as e:
            logger.error(f"检查ASR模型可用性失败: {e}")
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
