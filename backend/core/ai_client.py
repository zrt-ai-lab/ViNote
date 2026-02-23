"""
AI客户端单例管理
确保全局只有一个ASR模型和OpenAI客户端实例
"""
from typing import Optional
from pathlib import Path
import logging
from openai import OpenAI, AsyncOpenAI
from faster_whisper import WhisperModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config.ai_config import get_asr_config, get_whisper_config, get_openai_config

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


def _normalize_source(source: str) -> str:
    if source in {"modelscope", "ms"}:
        return "modelscope"
    if source in {"huggingface", "hf"}:
        return "huggingface"
    return "huggingface"


def _resolve_funasr_model_id(model: str, source: str) -> str:
    if "/" in model or model.startswith("."):
        return model
    normalized = model.replace("_", "-").lower()
    if normalized in {"sensevoicesmall", "sensevoice-small"}:
        return "iic/SenseVoiceSmall" if source == "modelscope" else "FunAudioLLM/SenseVoiceSmall"
    return model


def _resolve_qwen_model_id(model: str) -> str:
    if "/" in model or model.startswith("."):
        return model
    normalized = model.replace("_", "-").lower()
    if normalized in {"qwen3-asr-0.6b", "qwen3-asr-06b"}:
        return "Qwen/Qwen3-ASR-0.6B"
    if normalized in {"qwen3-asr-1.7b", "qwen3-asr-17b"}:
        return "Qwen/Qwen3-ASR-1.7B"
    return model


def _download_model(model_id: str, source: str, cache_dir: Optional[str]) -> str:
    if source == "modelscope":
        from modelscope.hub.snapshot_download import snapshot_download
        return snapshot_download(model_id, cache_dir=cache_dir)
    from huggingface_hub import snapshot_download
    return snapshot_download(repo_id=model_id, cache_dir=cache_dir)


class ASRModelSingleton:
    _instance = None
    _key: Optional[str] = None
    
    @classmethod
    def get_instance(cls):
        config = get_asr_config()
        source = _normalize_source(config.download_source)
        key = f"{config.provider}:{config.model}:{source}:{config.model_dir}:{config.device}:{config.compute_type}"
        if cls._instance is None or cls._key != key:
            cls._instance = cls._load_model(config, source)
            cls._key = key
        return cls._instance
    
    @staticmethod
    def _load_model(config, source: str):
        provider = config.provider.lower()
        if provider == "whisper":
            logger.info(f"加载Whisper模型: {config.model}")
            model = WhisperModel(
                config.model,
                device=config.device,
                compute_type=config.compute_type
            )
            logger.info("Whisper模型加载完成")
            return model
        
        if provider == "funasr":
            from funasr import AutoModel
            model_id = config.model_dir or _resolve_funasr_model_id(config.model, source)
            hub = "ms" if source == "modelscope" else "hf"
            
            kwargs = {
                "model": model_id,
                "device": config.device,
                "hub": hub,
                "vad_model": "fsmn-vad",
                "vad_kwargs": {"max_single_segment_time": 30000},
                "trust_remote_code": True,
                "disable_update": True
            }
            
            model = AutoModel(**kwargs)
            return model
        
        if provider == "qwen3":
            from qwen_asr import Qwen3ASRModel
            model_id = config.model_dir or _resolve_qwen_model_id(config.model)
            if config.model_dir:
                model_path = model_id
            else:
                model_path = _download_model(model_id, source, config.model_dir)
            model = Qwen3ASRModel.from_pretrained(
                model_path,
                device_map=config.device,
                trust_remote_code=True
            )
            return model
        
        raise ValueError(f"不支持的ASR提供方: {config.provider}")


class OpenAIClientSingleton:
    """OpenAI客户端单例"""
    _instance: Optional[OpenAI] = None
    _async_instance: Optional[AsyncOpenAI] = None
    
    @classmethod
    def get_instance(cls) -> Optional[OpenAI]:
        """获取OpenAI客户端实例（同步）"""
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
                logger.debug("OpenAI客户端初始化成功")
            except Exception as e:
                logger.error(f"OpenAI客户端初始化失败: {e}")
                return None
        
        return cls._instance
    
    @classmethod
    def get_async_instance(cls) -> Optional[AsyncOpenAI]:
        """获取OpenAI异步客户端实例"""
        if cls._async_instance is None:
            config = get_openai_config()
            
            if not config.is_configured:
                logger.warning("OpenAI API未配置，某些功能将不可用")
                return None
            
            try:
                cls._async_instance = AsyncOpenAI(
                    api_key=config.api_key,
                    base_url=config.base_url,
                    timeout=config.timeout,
                    max_retries=config.max_retries
                )
                logger.debug("OpenAI异步客户端初始化成功")
            except Exception as e:
                logger.error(f"OpenAI异步客户端初始化失败: {e}")
                return None
        
        return cls._async_instance
    
    @classmethod
    def clear_instance(cls):
        """清除实例（用于测试或重新加载）"""
        cls._instance = None
        cls._async_instance = None
    
    @classmethod
    def is_available(cls) -> bool:
        """检查OpenAI客户端是否可用"""
        return cls.get_instance() is not None


# 便捷访问函数
def get_whisper_model() -> WhisperModel:
    """获取Whisper模型"""
    return WhisperModelSingleton.get_instance()


def get_asr_model():
    return ASRModelSingleton.get_instance()


def get_openai_client() -> Optional[OpenAI]:
    """获取OpenAI客户端（同步）"""
    return OpenAIClientSingleton.get_instance()


def get_async_openai_client() -> Optional[AsyncOpenAI]:
    """获取OpenAI异步客户端"""
    return OpenAIClientSingleton.get_async_instance()


def is_openai_available() -> bool:
    """检查OpenAI是否可用"""
    return OpenAIClientSingleton.is_available()
