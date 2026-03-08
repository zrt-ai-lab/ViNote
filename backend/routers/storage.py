"""
存储管理 — 磁盘统计、临时文件清理、任务文件删除
"""
import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.state import tasks, save_tasks, active_tasks, TEMP_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

DOWNLOADS_DIR = TEMP_DIR / "downloads"
BACKUPS_DIR = TEMP_DIR / "backups"

# 音频文件扩展名
AUDIO_EXTENSIONS = {".m4a", ".wav", ".webm", ".mp3", ".ogg", ".part"}

# Markdown 笔记文件正则 (summary/transcript/raw/mindmap/translation)
NOTE_FILE_RE = re.compile(
    r"^(summary|transcript|raw|mindmap|translation)_(.+)_([a-f0-9]{6})\.md$"
)


def _file_age_days(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 86400


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


@router.get("/storage/stats")
async def get_storage_stats():
    """返回 temp 目录各类文件的存储统计（含 backups 子目录）"""
    stats = {
        "notes": {"count": 0, "size": 0, "files": []},
        "audio": {"count": 0, "size": 0, "files": []},
        "downloads": {"count": 0, "size": 0, "files": []},
        "backups": {"count": 0, "size": 0, "files": []},
        "other": {"count": 0, "size": 0},
    }

    if TEMP_DIR.exists():
        for f in TEMP_DIR.iterdir():
            if not f.is_file():
                continue
            size = f.stat().st_size
            suffix = f.suffix.lower()

            if suffix == ".md" and NOTE_FILE_RE.match(f.name):
                stats["notes"]["count"] += 1
                stats["notes"]["size"] += size
            elif suffix in AUDIO_EXTENSIONS or f.name.endswith(".m4a.part"):
                stats["audio"]["count"] += 1
                stats["audio"]["size"] += size
                stats["audio"]["files"].append({
                    "name": f.name,
                    "size": _format_size(size),
                    "age_days": round(_file_age_days(f), 1),
                })
            else:
                stats["other"]["count"] += 1
                stats["other"]["size"] += size

    if DOWNLOADS_DIR.exists():
        for f in DOWNLOADS_DIR.iterdir():
            if not f.is_file():
                continue
            size = f.stat().st_size
            stats["downloads"]["count"] += 1
            stats["downloads"]["size"] += size
            stats["downloads"]["files"].append({
                "name": f.name,
                "size": _format_size(size),
                "age_days": round(_file_age_days(f), 1),
            })

    if BACKUPS_DIR.exists():
        for f in BACKUPS_DIR.iterdir():
            if not f.is_file():
                continue
            size = f.stat().st_size
            stats["backups"]["count"] += 1
            stats["backups"]["size"] += size
            stats["backups"]["files"].append({
                "name": f.name,
                "size": _format_size(size),
                "age_days": round(_file_age_days(f), 1),
            })

    total_size = sum(s["size"] for s in stats.values())

    return {
        "notes": {
            "count": stats["notes"]["count"],
            "size": stats["notes"]["size"],
            "size_display": _format_size(stats["notes"]["size"]),
        },
        "audio": {
            "count": stats["audio"]["count"],
            "size": stats["audio"]["size"],
            "size_display": _format_size(stats["audio"]["size"]),
            "files": stats["audio"]["files"],
        },
        "downloads": {
            "count": stats["downloads"]["count"],
            "size": stats["downloads"]["size"],
            "size_display": _format_size(stats["downloads"]["size"]),
            "files": stats["downloads"]["files"],
        },
        "backups": {
            "count": stats["backups"]["count"],
            "size": stats["backups"]["size"],
            "size_display": _format_size(stats["backups"]["size"]),
            "files": stats["backups"]["files"],
        },
        "other": {
            "count": stats["other"]["count"],
            "size": stats["other"]["size"],
            "size_display": _format_size(stats["other"]["size"]),
        },
        "total_size": total_size,
        "total_size_display": _format_size(total_size),
    }


class CleanupRequest(BaseModel):
    clean_audio: bool = True
    clean_downloads: bool = False
    clean_backups: bool = False
    clean_all_notes: bool = False
    older_than_days: int = 0


@router.post("/storage/cleanup")
async def cleanup_storage(req: CleanupRequest):
    """清理临时文件（音频缓存、下载视频、备份、笔记）"""
    active_short_ids = set()
    for tid in active_tasks:
        active_short_ids.add(tid.replace("-", "")[:8])

    deleted_files = []
    freed_bytes = 0

    if req.clean_audio and TEMP_DIR.exists():
        for f in TEMP_DIR.iterdir():
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            is_audio = suffix in AUDIO_EXTENSIONS or f.name.endswith(".m4a.part")
            if not is_audio:
                continue
            if any(sid in f.name for sid in active_short_ids):
                continue
            if req.older_than_days > 0 and _file_age_days(f) < req.older_than_days:
                continue
            try:
                size = f.stat().st_size
                f.unlink()
                deleted_files.append(f.name)
                freed_bytes += size
                logger.info(f"清理音频文件: {f.name}")
            except Exception as e:
                logger.warning(f"删除文件失败 {f.name}: {e}")

    if req.clean_downloads and DOWNLOADS_DIR.exists():
        for f in DOWNLOADS_DIR.iterdir():
            if not f.is_file():
                continue
            if req.older_than_days > 0 and _file_age_days(f) < req.older_than_days:
                continue
            try:
                size = f.stat().st_size
                f.unlink()
                deleted_files.append(f"downloads/{f.name}")
                freed_bytes += size
                logger.info(f"清理下载文件: {f.name}")
            except Exception as e:
                logger.warning(f"删除文件失败 {f.name}: {e}")

    if req.clean_backups and BACKUPS_DIR.exists():
        for f in BACKUPS_DIR.iterdir():
            if not f.is_file():
                continue
            if req.older_than_days > 0 and _file_age_days(f) < req.older_than_days:
                continue
            try:
                size = f.stat().st_size
                f.unlink()
                deleted_files.append(f"backups/{f.name}")
                freed_bytes += size
                logger.info(f"清理备份文件: {f.name}")
            except Exception as e:
                logger.warning(f"删除文件失败 {f.name}: {e}")

    if req.clean_all_notes and TEMP_DIR.exists():
        active_short_ids_6 = {tid.replace("-", "")[:6] for tid in active_tasks}
        for f in TEMP_DIR.iterdir():
            if not f.is_file() or f.suffix != ".md":
                continue
            match = NOTE_FILE_RE.match(f.name)
            if not match:
                continue
            if match.group(3) in active_short_ids_6:
                continue
            if req.older_than_days > 0 and _file_age_days(f) < req.older_than_days:
                continue
            try:
                size = f.stat().st_size
                f.unlink()
                deleted_files.append(f.name)
                freed_bytes += size
                logger.info(f"清理笔记文件: {f.name}")
            except Exception as e:
                logger.warning(f"删除文件失败 {f.name}: {e}")

        # 清除内存中对应的已完成任务
        completed_tids = [
            tid for tid, t in tasks.items()
            if t.get("status") in ("completed", "error", "cancelled")
            and tid.replace("-", "")[:6] not in active_short_ids_6
        ]
        for tid in completed_tids:
            del tasks[tid]
        if completed_tids:
            save_tasks(tasks)

        # 清除 SQLite 中所有笔记
        try:
            from backend.services.note_repository import delete_all_notes
            deleted_db = await delete_all_notes()
            logger.info(f"清除 SQLite {deleted_db} 条笔记记录")
        except Exception as e:
            logger.error(f"清除 SQLite 笔记失败: {e}")

    return {
        "deleted_count": len(deleted_files),
        "freed_size": freed_bytes,
        "freed_size_display": _format_size(freed_bytes),
        "deleted_files": deleted_files,
    }


@router.delete("/storage/task/{short_id}")
async def delete_task_files(short_id: str):
    """删除指定任务的所有文件和数据库记录"""
    if not re.match(r"^[a-f0-9]{6}$", short_id):
        raise HTTPException(status_code=400, detail="无效的任务ID格式")

    for tid in active_tasks:
        if tid.replace("-", "")[:6] == short_id:
            raise HTTPException(status_code=409, detail="任务正在处理中，无法删除")

    deleted_files = []
    freed_bytes = 0

    if TEMP_DIR.exists():
        for f in TEMP_DIR.iterdir():
            if not f.is_file() or f.suffix != ".md":
                continue
            match = NOTE_FILE_RE.match(f.name)
            if match and match.group(3) == short_id:
                try:
                    size = f.stat().st_size
                    f.unlink()
                    deleted_files.append(f.name)
                    freed_bytes += size
                    logger.info(f"删除任务文件: {f.name}")
                except Exception as e:
                    logger.warning(f"删除文件失败 {f.name}: {e}")

    # 从内存 tasks dict 中移除（兼容未迁移的）
    task_ids_to_remove = [
        tid for tid in tasks
        if tid.replace("-", "")[:6] == short_id
    ]
    for tid in task_ids_to_remove:
        del tasks[tid]
    if task_ids_to_remove:
        save_tasks(tasks)

    # 从 SQLite 删除
    db_deleted = False
    try:
        from backend.services.note_repository import delete_note
        db_deleted = await delete_note(short_id)
        if db_deleted:
            logger.info(f"删除 SQLite 笔记记录: {short_id}")
    except Exception as e:
        logger.error(f"删除 SQLite 记录失败: {e}")

    if not deleted_files and not task_ids_to_remove and not db_deleted:
        raise HTTPException(status_code=404, detail="未找到该任务的相关文件")

    return {
        "deleted_files": deleted_files,
        "freed_size": freed_bytes,
        "freed_size_display": _format_size(freed_bytes),
        "removed_task_ids": task_ids_to_remove,
    }
