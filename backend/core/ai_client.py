"""
AI客户端单例管理
确保全局只有一个Whisper模型和OpenAI客户端实例
"""
from typing import Optional
import logging
from openai import OpenAI
from faster_whisper import WhisperModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config.ai_config import get_whisper_config, get_openai_config

logger = logging.getLogger(__name__)


class WhisperModelSingleton:
    """Whisper模型单例"""
    _instance: Optional[WhisperModel] = None
    _model_size: Optional[str] = None
    
    @classmethod
    def get_instance(cls) -> WhisperModel:
        """获取Whisper模型实例（懒加载）"""
        config = get_whisper_config()
        
        # 如果模型大小改变，重新加载
        if cls._instance is None or cls._model_size != config.model_size:
            logger.info(f"加载Whisper模型: {config.model_size}")
            cls._instance = WhisperModel(
                config.model_size,
                device=config.device,
                compute_type=config.compute_type
            )
            cls._model_size = config.model_size
            logger.info("Whisper模型加载完成")
        
        return cls._instance
    
    @classmethod
    def clear_instance(cls):
        """清除实例（用于测试或重新加载）"""
        cls._instance = None
        cls._model_size = None


class OpenAIClientSingleton:
    """OpenAI客户端单例"""
    _instance: Optional[OpenAI] = None
    
    @classmethod
    def get_instance(cls) -> Optional[OpenAI]:
        """获取OpenAI客户端实例"""
        if cls._instance is None:
            config = get_openai_config()
            
            if not config.is_configured:
                logger.warning("OpenAI API未配置，某些功能将不可用")
                return None
            
            try:
                cls._instance = OpenAI(
                    api_key=config.api_key,
                    base_url=config.base_url,
                    timeout=config.timeout,
                    max_retries=config.max_retries
                )
                logger.info(f"OpenAI客户端初始化成功 (base_url: {config.base_url})")
            except Exception as e:
                logger.error(f"OpenAI客户端初始化失败: {e}")
                return None
        
        return cls._instance
    
    @classmethod
    def clear_instance(cls):
        """清除实例（用于测试或重新加载）"""
        cls._instance = None
    
    @classmethod
    def is_available(cls) -> bool:
        """检查OpenAI客户端是否可用"""
        return cls.get_instance() is not None


# 便捷访问函数
def get_whisper_model() -> WhisperModel:
    """获取Whisper模型"""
    return WhisperModelSingleton.get_instance()


def get_openai_client() -> Optional[OpenAI]:
    """获取OpenAI客户端"""
    return OpenAIClientSingleton.get_instance()


def is_openai_available() -> bool:
    """检查OpenAI是否可用"""
    return OpenAIClientSingleton.is_available()
