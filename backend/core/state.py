"""
应用状态管理 — 任务状态、SSE连接、全局服务实例（lazy init）
"""
import json
import re
import logging
import threading
from pathlib import Path
from typing import Dict, Set, List
from datetime import datetime

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

# ── 路径 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(exist_ok=True)

TASKS_FILE = TEMP_DIR / "tasks.json"
tasks_lock = threading.Lock()

# ── 全局状态 ──────────────────────────────────────────
tasks: Dict = {}
processing_urls: Set[str] = set()
active_tasks: Dict = {}
sse_connections: Dict[str, List] = {}
sse_connection_last_activity: Dict[str, datetime] = {}

# ── 服务实例 (lazy init) ─────────────────────────────
_video_preview_service = None
_video_download_service = None
_video_qa_service = None
_video_search_agent = None


def get_video_preview_service():
    global _video_preview_service
    if _video_preview_service is None:
        from backend.services.video_preview_service import VideoPreviewService
        _video_preview_service = VideoPreviewService()
    return _video_preview_service


def get_video_download_service():
    global _video_download_service
    if _video_download_service is None:
        from backend.services.video_download_service import VideoDownloadService
        _video_download_service = VideoDownloadService(TEMP_DIR / "downloads")
    return _video_download_service


def get_video_qa_service():
    global _video_qa_service
    if _video_qa_service is None:
        from backend.services.video_qa_service import VideoQAService
        _video_qa_service = VideoQAService()
    return _video_qa_service


def get_video_search_agent():
    global _video_search_agent
    if _video_search_agent is None:
        from backend.services.search_providers.manager import SearchProviderManager
        from backend.services.video_search_agent import VideoSearchAgent
        settings = get_settings()
        search_manager = SearchProviderManager(
            provider_names=settings.SEARCH_PROVIDERS,
            anp_server_url=settings.ANP_SERVER_URL,
        )
        _video_search_agent = VideoSearchAgent(search_manager=search_manager)
    return _video_search_agent


# ── 任务持久化 ────────────────────────────────────────
def load_tasks() -> Dict:
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


_last_backup_time: datetime | None = None


def save_tasks(tasks_data: Dict) -> None:
    global _last_backup_time
    try:
        with tasks_lock:
            temp_file = TASKS_FILE.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
            temp_file.replace(TASKS_FILE)

            now = datetime.now()
            if _last_backup_time and (now - _last_backup_time).total_seconds() < 30:
                return
            _last_backup_time = now

            backup_dir = TEMP_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"tasks_{timestamp}.json"

            import shutil
            shutil.copy2(TASKS_FILE, backup_file)

            backups = sorted(
                backup_dir.glob("tasks_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old_backup in backups[3:]:
                old_backup.unlink()

    except Exception as e:
        logger.error(f"保存任务状态失败: {e}")


# ── SSE 广播 ──────────────────────────────────────────
async def broadcast_task_update(task_id: str, task_data: dict) -> None:
    logger.debug(
        f"广播任务更新: {task_id}, 状态: {task_data.get('status')}, "
        f"连接数: {len(sse_connections.get(task_id, []))}"
    )
    if task_id in sse_connections:
        connections_to_remove = []
        for queue in sse_connections[task_id]:
            try:
                await queue.put(json.dumps(task_data, ensure_ascii=False))
            except Exception as e:
                logger.warning(f"发送消息到队列失败: {e}")
                connections_to_remove.append(queue)

        for queue in connections_to_remove:
            sse_connections[task_id].remove(queue)

        if not sse_connections[task_id]:
            del sse_connections[task_id]


# ── 工具函数 ──────────────────────────────────────────
def sanitize_title_for_filename(title: str) -> str:
    if not title:
        return "untitled"
    safe = re.sub(r"[^\w\-\s]", "", title)
    safe = re.sub(r"\s+", "_", safe).strip("._-")
    return safe[:80] or "untitled"


def validate_download_filename(filename: str) -> bool:
    allowed_extensions = [".md"]
    if not any(filename.endswith(ext) for ext in allowed_extensions):
        return False

    dangerous_chars = ["..", "/", "\\", "\0", ":", "*", "?", '"', "<", ">", "|"]
    if any(char in filename for char in dangerous_chars):
        return False

    if len(filename) > 255:
        return False

    if not filename or filename.strip() == "":
        return False

    try:
        file_path = (TEMP_DIR / filename).resolve()
        temp_dir_resolved = TEMP_DIR.resolve()
        if not str(file_path).startswith(str(temp_dir_resolved)):
            return False
    except Exception:
        return False

    return True


# ── 启动时加载 ────────────────────────────────────────
tasks.update(load_tasks())
