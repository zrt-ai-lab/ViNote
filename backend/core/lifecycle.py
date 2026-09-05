"""
应用生命周期 — 启动/关闭事件
"""
import asyncio
import logging
from datetime import datetime, timedelta

from backend.core.state import (
    active_batches,
    active_tasks,
    save_tasks,
    sse_connections,
    sse_connection_last_activity,
    tasks,
)

logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()


async def cleanup_stale_sse_connections():
    """定期清理断开或过期的 SSE 连接（只清理已完成/失败的任务连接）"""
    while True:
        try:
            await asyncio.sleep(300)

            current_time = datetime.now()
            stale_threshold = timedelta(hours=2)
            tasks_to_cleanup = []

            for task_id in list(sse_connections.keys()):
                task = tasks.get(task_id)

                if task:
                    task_status = task.get("status")

                    if task_status == "processing":
                        logger.debug(f"任务 {task_id} 正在处理中，跳过清理")
                        continue

                    if task_status in ["completed", "error", "cancelled"]:
                        last_activity = sse_connection_last_activity.get(task_id)
                        if last_activity and (current_time - last_activity) > stale_threshold:
                            tasks_to_cleanup.append(task_id)
                        elif not last_activity:
                            tasks_to_cleanup.append(task_id)
                else:
                    tasks_to_cleanup.append(task_id)

            for task_id in tasks_to_cleanup:
                if task_id in sse_connections:
                    logger.info(f"清理已完成任务的SSE连接: {task_id}")
                    del sse_connections[task_id]
                if task_id in sse_connection_last_activity:
                    del sse_connection_last_activity[task_id]

            if tasks_to_cleanup:
                logger.info(f"已清理 {len(tasks_to_cleanup)} 个已完成任务的SSE连接")

        except Exception as e:
            logger.error(f"清理SSE连接时出错: {e}")


async def repair_note_file_links():
    """保守修复 notes 表中文件名字段，避免同标题笔记互相覆盖。"""
    from collections import Counter
    import re
    from backend.db.connection import get_db
    from backend.core.state import TEMP_DIR

    note_file_re = re.compile(
        r"^(summary|transcript|raw|mindmap|translation)_(.+)_([a-f0-9]{6,32})\.md$"
    )

    # safe_title 只用于兼容旧的 short_id 错配；重复标题绝不自动猜测。
    fs_index: dict[str, dict[str, dict[str, str]]] = {}
    for f in TEMP_DIR.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        match = note_file_re.match(f.name)
        if not match:
            continue
        file_type, safe_title, short_id = match.group(1), match.group(2), match.group(3)
        fs_index.setdefault(safe_title, {}).setdefault(short_id, {})[file_type] = f.name

    if not fs_index:
        return

    async with get_db() as db:
        # 查找文件名字段全为 NULL 的笔记
        cursor = await db.execute(
            """SELECT id, short_id, safe_title FROM notes
               WHERE summary_file IS NULL AND transcript_file IS NULL"""
        )
        broken_notes = await cursor.fetchall()
        broken_title_counts = Counter(row[2] for row in broken_notes if row[2])

        repaired = 0
        for note_id, db_short_id, safe_title in broken_notes:
            if not safe_title:
                continue
            candidates = fs_index.get(safe_title, {})
            if not candidates:
                continue
            if db_short_id in candidates:
                real_short_id = db_short_id
                files = candidates[db_short_id]
            elif len(candidates) == 1 and broken_title_counts[safe_title] == 1:
                real_short_id, files = next(iter(candidates.items()))
            else:
                logger.warning("跳过标题重复的笔记文件自动修复: %s", safe_title)
                continue

            # 检查 real_short_id 是否已被其他 note 占用
            cursor = await db.execute(
                "SELECT id FROM notes WHERE short_id = ? AND id != ?",
                (real_short_id, note_id),
            )
            if await cursor.fetchone():
                continue  # 跳过冲突记录

            # 更新 short_id 和文件名
            await db.execute(
                """UPDATE notes SET
                    short_id = ?,
                    summary_file = ?,
                    transcript_file = ?,
                    mindmap_file = ?,
                    translation_file = ?,
                    raw_transcript_file = ?
                   WHERE id = ?""",
                (
                    real_short_id,
                    files.get("summary"),
                    files.get("transcript") or files.get("raw"),
                    files.get("mindmap"),
                    files.get("translation"),
                    files.get("raw"),
                    note_id,
                ),
            )
            repaired += 1

        if repaired:
            await db.commit()
            logger.info(f"修复了 {repaired} 条笔记的文件关联")


async def startup_event():
    # 初始化 SQLite 数据库 + 自动迁移 JSON 数据
    from backend.db.schema import init_db, migrate_from_json
    await init_db()
    await migrate_from_json()

    # 修复历史数据中 short_id 不匹配导致的文件关联丢失
    await repair_note_file_links()

    from backend.services.note_search import backfill_note_search
    await backfill_note_search()

    interrupted = False
    for task_data in tasks.values():
        if task_data.get("status") in {"queued", "processing"}:
            task_data.update({
                "status": "error",
                "error": "应用上次运行已中断",
                "message": "任务因应用重启而中断，请重新提交",
            })
            interrupted = True
    if interrupted:
        save_tasks(tasks)

    from backend.config.ai_config import get_openai_config
    if get_openai_config().is_configured:
        logger.info("LLM 已配置，将在首次使用时建立连接")
    else:
        logger.warning("LLM 未配置，AI 功能将使用可用的基础回退")

    cleanup_task = asyncio.create_task(cleanup_stale_sse_connections())
    _background_tasks.add(cleanup_task)
    cleanup_task.add_done_callback(_background_tasks.discard)


async def shutdown_event():
    """取消由应用拥有的后台任务，等待清理逻辑完成。"""
    owned_tasks = {
        *_background_tasks,
        *active_batches.values(),
        *active_tasks.values(),
    }
    for task in owned_tasks:
        if not task.done():
            task.cancel()
    if owned_tasks:
        await asyncio.gather(*owned_tasks, return_exceptions=True)
    _background_tasks.clear()
    active_batches.clear()
    active_tasks.clear()
    sse_connections.clear()
    sse_connection_last_activity.clear()
