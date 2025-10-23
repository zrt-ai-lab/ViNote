"""
核心基础设施模块
"""
from .ai_client import (
    get_whisper_model,
    get_openai_client,
    is_openai_available,
    WhisperModelSingleton,
    OpenAIClientSingleton
)

__all__ = [
    'get_whisper_model',
    'get_openai_client',
    'is_openai_available',
    'WhisperModelSingleton',
    'OpenAIClientSingleton'
]
