"""
基础应用配置
路径、常量、环境变量等
"""
from pathlib import Path
import os
from dotenv import load_dotenv
from backend.version import VERSION

# 加载环境变量
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


class Settings:
    """应用设置"""
    
    # ========== 路径配置 ==========
    PROJECT_ROOT: Path = PROJECT_ROOT
    BACKEND_DIR: Path = PROJECT_ROOT / "backend"
    TEMP_DIR: Path = PROJECT_ROOT / "temp"
    
    # 临时文件子目录
    DOWNLOADS_DIR: Path = TEMP_DIR / "downloads"
    BACKUPS_DIR: Path = TEMP_DIR / "backups"
    
    # 任务持久化文件
    TASKS_FILE: Path = TEMP_DIR / "tasks.json"
    
    # ========== 应用配置 ==========
    APP_TITLE: str = "ViNote API"
    APP_VERSION: str = VERSION
    APP_DESCRIPTION: str = "AI驱动的视频笔记生成系统"
    
    HOST: str = os.getenv("APP_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("APP_PORT", "8999"))
    DEBUG: bool = os.getenv("APP_DEBUG", "false").lower() == "true"
    ALLOWED_HOSTS: list = [
        host.strip() for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,::1").split(",") if host.strip()
    ]
    if HOST not in {"0.0.0.0", "::"} and HOST not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(HOST)
    
    # ========== CORS配置 ==========
    CORS_ORIGINS: list = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]
    CORS_CREDENTIALS: bool = False
    CORS_METHODS: list = ["*"]
    CORS_HEADERS: list = ["*"]
    
    # ========== 速率限制配置 ==========
    RATE_LIMIT_CALLS: int = int(os.getenv("RATE_LIMIT_CALLS", "100"))
    RATE_LIMIT_PERIOD: int = int(os.getenv("RATE_LIMIT_PERIOD", "60"))
    
    # ========== 文件安全配置 ==========
    ALLOWED_EXTENSIONS: list = ['.md']
    MAX_FILENAME_LENGTH: int = 255
    DANGEROUS_CHARS: list = ['..', '/', '\\', '\0', ':', '*', '?', '"', '<', '>', '|']
    
    # ========== SSE配置 ==========
    SSE_HEARTBEAT_INTERVAL: float = 0.5
    SSE_CLEANUP_INTERVAL: int = 300
    SSE_STALE_THRESHOLD: int = 7200
    
    # ========== 任务配置 ==========
    TASK_BACKUP_COUNT: int = 3
    # 批量任务同时处理数（默认5）。值越大同时跑的任务越多，占用更多内存和API并发
    BATCH_CONCURRENCY: int = int(os.getenv("BATCH_CONCURRENCY", "5"))
    # ASR转录并发数（默认1）。模型共享单实例，并发不增加内存，但每个转录占1个CPU核。
    # tiny/base可设3-5，small/medium设2-3，large设1-2
    ASR_CONCURRENCY: int = int(os.getenv("ASR_CONCURRENCY", "1"))
    
    
    def __init__(self):
        """初始化时创建必要的目录"""
        self.TEMP_DIR.mkdir(exist_ok=True)
        self.DOWNLOADS_DIR.mkdir(exist_ok=True)
        self.BACKUPS_DIR.mkdir(exist_ok=True)


# 创建全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
