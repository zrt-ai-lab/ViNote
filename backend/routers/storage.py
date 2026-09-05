"""
存储管理 — 磁盘统计、临时文件清理、任务文件删除
"""
import logging
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.state import tasks, save_tasks, active_tasks, TEMP_DIR
from backend.services.note_operations import cleanup_staging, finish_commit, note_operation
from backend.services.note_repository import delete_note, get_note, list_note_artifacts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

DOWNLOADS_DIR = TEMP_DIR / "downloads"
BACKUPS_DIR = TEMP_DIR / "backups"

# 音频文件扩展名
AUDIO_EXTENSIONS = {".m4a", ".wav", ".webm", ".mp3", ".ogg", ".part"}

# Markdown 笔记文件正则 (summary/transcript/raw/mindmap/translation)
NOTE_FILE_RE = re.compile(
    r"^(summary|transcript|raw|mindmap|translation)_(.+)_([a-f0-9]{6,32})\.md$"
)
ARTIFACT_FIELDS = (
    "raw_transcript_file", "transcript_file", "summary_file", "mindmap_file", "translation_file",
)


def _note_id_for_task(task_id: str) -> str:
    task_short_id = tasks.get(task_id, {}).get("short_id")
    return str(task_short_id or task_id.replace("-", "")[:6])


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
    older_than_days: int = Field(default=0, ge=0)


@router.post("/storage/cleanup")
async def cleanup_storage(req: CleanupRequest):
    """清理临时文件（音频缓存、下载视频、备份、笔记）"""
    if req.clean_audio and active_tasks:
        raise HTTPException(status_code=409, detail="有任务正在处理，请结束后再清理音频缓存")
    if req.clean_all_notes and active_tasks:
        raise HTTPException(status_code=409, detail="有任务正在处理，请结束后再清理笔记")

    active_short_ids = set()
    for tid in active_tasks:
        active_short_ids.add(_note_id_for_task(tid))

    deleted_files = []
    freed_bytes = 0
    failed_note_ids: list[str] = []
    skipped_note_ids: list[str] = []

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

    if req.clean_all_notes:
        files_by_note = _scan_note_files()
        records = {note["short_id"]: note for note in await list_note_artifacts()}
        terminal_ids = {
            _note_id_for_task(tid) for tid, task in tasks.items()
            if task.get("status") in {"completed", "error", "cancelled"}
        }
        # A note is the deletion unit: never remove its row while retaining one
        # of its newer artifacts or after a failed file operation.
        candidates = set(files_by_note) | set(records) | terminal_ids
        for short_id in sorted(candidates):
            async with note_operation(short_id):
                if active_tasks:
                    skipped_note_ids.append(short_id)
                    continue
                note = await get_note(short_id)
                files = _note_files(note, files_by_note.get(short_id, []))
                if not _old_enough(note, files, req.older_than_days):
                    skipped_note_ids.append(short_id)
                    continue
                try:
                    removed = await finish_commit(_delete_note_group(short_id, files))
                except Exception:
                    logger.exception("清理笔记失败，已尝试恢复文件: %s", short_id)
                    failed_note_ids.append(short_id)
                    continue
                deleted_files.extend(removed["deleted_files"])
                freed_bytes += removed["freed_size"]

    return {
        "deleted_count": len(deleted_files),
        "freed_size": freed_bytes,
        "freed_size_display": _format_size(freed_bytes),
        "deleted_files": deleted_files,
        "failed_note_ids": failed_note_ids,
        "skipped_note_ids": skipped_note_ids,
    }


@router.delete("/storage/task/{short_id}")
async def delete_task_files(short_id: str):
    """删除指定任务的所有文件和数据库记录"""
    if not re.fullmatch(r"[a-f0-9]{6,32}", short_id):
        raise HTTPException(status_code=400, detail="无效的任务ID格式")

    async with note_operation(short_id):
        if any(_note_id_for_task(tid) == short_id for tid in active_tasks):
            raise HTTPException(status_code=409, detail="任务正在处理中，无法删除")
        note = await get_note(short_id)
        files = _note_files(note, _scan_note_files().get(short_id, []))
        try:
            return await finish_commit(_delete_note_group(short_id, files))
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("删除笔记失败，已尝试恢复文件: %s", short_id)
            raise HTTPException(status_code=500, detail="笔记删除失败，相关记录已保留，请重试") from exc


def _scan_note_files() -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    if TEMP_DIR.exists():
        for path in TEMP_DIR.iterdir():
            match = NOTE_FILE_RE.fullmatch(path.name)
            if path.is_file() and not path.is_symlink() and match:
                groups.setdefault(match.group(3), []).append(path)
    return groups


def _note_files(note: dict | None, known_files: list[Path]) -> list[Path]:
    paths = set(known_files)
    for field in ARTIFACT_FIELDS:
        filename = (note or {}).get(field)
        if filename and Path(filename).name == filename:
            path = TEMP_DIR / filename
            if path.suffix == ".md" and path.resolve().parent == TEMP_DIR.resolve():
                paths.add(path)
    return sorted(path for path in paths if path.is_file() and not path.is_symlink())


def _old_enough(note: dict | None, files: list[Path], days: int) -> bool:
    if not days:
        return True
    if files:
        return all(_file_age_days(path) >= days for path in files)
    # An already missing artifact must not make a recent row eligible.
    try:
        created = datetime.fromisoformat((note or {}).get("created_at") or "")
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (time.time() - created.timestamp()) / 86400 >= days
    except (ValueError, TypeError):
        return False


async def _delete_note_group(short_id: str, files: list[Path]) -> dict:
    # Prepare all backups before unlinking anything. A rollback uses renames,
    # so disk-full errors do not require writing the old Markdown a second time.
    originals: dict[Path, Path] = {}
    removed: list[Path] = []
    committed = False
    freed = sum(path.stat().st_size for path in files)
    try:
        for path in files:
            backup = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.backup")
            originals[path] = backup
            shutil.copy2(path, backup)
        for path in files:
            path.unlink()
            removed.append(path)
        db_deleted = await delete_note(short_id)
        committed = True
    except BaseException:
        for path in removed:
            originals[path].replace(path)
        cleanup_staging(originals.values())
        raise
    finally:
        if committed:
            cleanup_staging(originals.values())

    task_ids = [tid for tid in tasks if _note_id_for_task(tid) == short_id]
    if not files and not task_ids and not db_deleted:
        raise HTTPException(status_code=404, detail="未找到该任务的相关文件")
    for tid in task_ids:
        del tasks[tid]
    if task_ids:
        save_tasks(tasks)
    return {
        "deleted_files": [path.name for path in files],
        "freed_size": freed,
        "freed_size_display": _format_size(freed),
        "removed_task_ids": task_ids,
    }
