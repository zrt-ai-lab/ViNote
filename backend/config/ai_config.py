"""
AI模型统一配置
管理所有AI服务的配置参数
"""
from dataclasses import dataclass
from typing import Optional
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


@dataclass
class WhisperConfig:
    """Whisper模型配置"""
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    
    # VAD参数
    vad_filter: bool = True
    min_silence_duration_ms: int = 900
    speech_pad_ms: int = 300
    
    # 识别参数
    beam_size: int = 5
    best_of: int = 5
    temperature: list = None
    no_speech_threshold: float = 0.7
    compression_ratio_threshold: float = 2.3
    log_prob_threshold: float = -1.0
    condition_on_previous_text: bool = False
    
    def __post_init__(self):
        if self.temperature is None:
            self.temperature = [0.0, 0.2, 0.4]
        
        # 从环境变量读取模型大小
        env_model_size = os.getenv("WHISPER_MODEL_SIZE")
        if env_model_size:
            self.model_size = env_model_size


@dataclass
class OpenAIConfig:
    """OpenAI API配置"""
    api_key: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "cortex-4"
    
    # 通用参数
    default_temperature: float = 0.3
    default_max_tokens: int = 4000
    
    # 专用参数
    optimization_temperature: float = 0.1
    optimization_max_tokens: int = 4000
    
    summary_temperature: float = 0.3
    summary_max_tokens: int = 3500
    
    translation_temperature: float = 0.1
    translation_max_tokens: int = 4000
    
    qa_temperature: float = 0.3
    qa_max_tokens: int = 1500
    
    # 重试配置
    max_retries: int = 3
    timeout: int = 60
    
    def __post_init__(self):
        # 从环境变量读取
        self.api_key = os.getenv("OPENAI_API_KEY")
        env_base_url = os.getenv("OPENAI_BASE_URL")
        if env_base_url:
            self.base_url = env_base_url
        
        env_model = os.getenv("OPENAI_MODEL")
        if env_model:
            self.model = env_model
    
    @property
    def is_configured(self) -> bool:
        """检查API是否已配置"""
        return bool(self.api_key)


@dataclass
class AIServiceConfig:
    """AI服务统一配置"""
    whisper: WhisperConfig
    openai: OpenAIConfig
    
    # 文本处理配置
    max_chars_per_chunk: int = 4000
    max_paragraph_chars: int = 400
    max_transcript_length: int = 8000
    
    # 语言映射
    supported_languages: dict = None
    
    def __post_init__(self):
        if self.supported_languages is None:
            self.supported_languages = {
                "zh": "中文（简体）",
                "zh-tw": "中文（繁体）",
                "en": "English",
                "ja": "日本語",
                "ko": "한국어",
                "fr": "Français",
                "de": "Deutsch",
                "es": "Español",
                "it": "Italiano",
                "pt": "Português",
                "ru": "Русский",
                "ar": "العربية",
                "hi": "हिन्दी"
            }


# 创建全局配置实例
ai_config = AIServiceConfig(
    whisper=WhisperConfig(),
    openai=OpenAIConfig()
)


# 便捷访问函数
def get_whisper_config() -> WhisperConfig:
    """获取Whisper配置"""
    return ai_config.whisper


def get_openai_config() -> OpenAIConfig:
    """获取OpenAI配置"""
    return ai_config.openai


def get_ai_config() -> AIServiceConfig:
    """获取完整AI配置"""
    return ai_config


def get_language_name(lang_code: str) -> str:
    """获取语言名称"""
    return ai_config.supported_languages.get(lang_code, lang_code)
