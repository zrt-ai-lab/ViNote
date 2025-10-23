"""
配置模块
统一管理应用配置和AI模型配置
"""
from .settings import settings, get_settings
from .ai_config import (
    ai_config,
    get_ai_config,
    get_whisper_config,
    get_openai_config,
    get_language_name
)

__all__ = [
    'settings',
    'get_settings',
    'ai_config',
    'get_ai_config',
    'get_whisper_config',
    'get_openai_config',
    'get_language_name'
]
