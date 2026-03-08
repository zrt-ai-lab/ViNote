"""
应用生命周期 — 启动/关闭事件
"""
import asyncio
import logging
from datetime import datetime, timedelta

from backend.core.state import (
    sse_connections,
    sse_connection_last_activity,
    tasks,
)

logger = logging.getLogger(__name__)


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


async def check_openai_connection():
    """检查 OpenAI API 连接性"""
    from backend.core.ai_client import get_openai_client
    from backend.config.ai_config import get_openai_config

    config = get_openai_config()

    if not config.is_configured:
        logger.warning("OpenAI API 未配置，AI功能不可用")
        return

    try:
        client = get_openai_client()
        if client is None:
            logger.error("❌ OpenAI 客户端初始化失败")
            return

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=config.model,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
            timeout=10,
        )

        logger.info(f"OpenAI API 就绪 ({config.model})")

    except Exception as e:
        error_msg = str(e)
        if "API key" in error_msg or "Unauthorized" in error_msg:
            logger.error("OpenAI API Key 无效")
        elif "timeout" in error_msg.lower():
            logger.error("OpenAI API 连接超时")
        elif "Connection" in error_msg or "connect" in error_msg.lower():
            logger.error(f"OpenAI API 无法连接: {config.base_url}")
        else:
            logger.error(f"OpenAI API 异常: {error_msg}")


async def repair_note_file_links():
    """修复 notes 表中文件名字段为 NULL 的记录（short_id 不匹配导致的历史问题）"""
    import re
    from backend.db.connection import get_db
    from backend.core.state import TEMP_DIR

    note_file_re = re.compile(
        r"^(summary|transcript|raw|mindmap|translation)_(.+)_([a-f0-9]{6})\.md$"
    )

    # 扫描 temp 目录，建立 safe_title → {short_id, files} 索引
    fs_index: dict[str, dict] = {}  # safe_title -> {short_id, files: {type: filename}}
    for f in TEMP_DIR.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        match = note_file_re.match(f.name)
        if not match:
            continue
        file_type, safe_title, short_id = match.group(1), match.group(2), match.group(3)
        if safe_title not in fs_index:
            fs_index[safe_title] = {"short_id": short_id, "files": {}}
        fs_index[safe_title]["files"][file_type] = f.name

    if not fs_index:
        return

    async with get_db() as db:
        # 查找文件名字段全为 NULL 的笔记
        cursor = await db.execute(
            """SELECT id, short_id, safe_title FROM notes
               WHERE summary_file IS NULL AND transcript_file IS NULL"""
        )
        broken_notes = await cursor.fetchall()

        repaired = 0
        for note_id, db_short_id, safe_title in broken_notes:
            if not safe_title:
                continue
            fs_info = fs_index.get(safe_title)
            if not fs_info:
                continue

            real_short_id = fs_info["short_id"]
            files = fs_info["files"]

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
                    translation_file = ?
                   WHERE id = ?""",
                (
                    real_short_id,
                    files.get("summary"),
                    files.get("transcript") or files.get("raw"),
                    files.get("mindmap"),
                    files.get("translation"),
                    note_id,
                ),
            )
            repaired += 1

        if repaired:
            await db.commit()
            logger.info(f"修复了 {repaired} 条笔记的文件关联")


async def cleanup_orphan_notes():
    """删除没有文件且磁盘上已有同 safe_title 文件的孤立笔记"""
    import re
    from backend.db.connection import get_db
    from backend.core.state import TEMP_DIR

    # 扫描磁盘，收集所有 safe_title（已有文件）
    note_file_re = re.compile(
        r"^(?:summary|transcript|raw|mindmap|translation)_(.+)_[a-f0-9]{6}\.md$"
    )
    titles_with_files: set[str] = set()
    for f in TEMP_DIR.iterdir():
        if f.is_file() and f.suffix == ".md":
            match = note_file_re.match(f.name)
            if match:
                titles_with_files.add(match.group(1))

    if not titles_with_files:
        return

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, short_id, safe_title FROM notes
               WHERE summary_file IS NULL AND transcript_file IS NULL"""
        )
        orphans = await cursor.fetchall()
        if not orphans:
            return

        deleted = 0
        for note_id, short_id, safe_title in orphans:
            if safe_title and safe_title in titles_with_files:
                await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                deleted += 1

        if deleted:
            await db.commit()
            logger.info(f"清理了 {deleted} 条无文件的重复笔记")


async def startup_event():
    # 初始化 SQLite 数据库 + 自动迁移 JSON 数据
    from backend.db.schema import init_db, migrate_from_json
    await init_db()
    await migrate_from_json()

    # 修复历史数据中 short_id 不匹配导致的文件关联丢失
    await repair_note_file_links()

    # 清理无文件的重复笔记记录
    await cleanup_orphan_notes()

    asyncio.create_task(cleanup_stale_sse_connections())
    asyncio.create_task(check_openai_connection())
