"""
数据库 schema 管理 — 建表、预置数据、JSON 迁移
"""
import json
import logging
import re
from pathlib import Path

from backend.db.connection import get_db, DB_PATH
from backend.core.state import TEMP_DIR

logger = logging.getLogger(__name__)

PREDEFINED_CATEGORIES = [
    "编程开发", "人工智能", "数据科学", "网络安全",
    "硬件电子", "操作系统", "设计创意", "数学科学",
    "语言学习", "商业管理", "生活技能", "健康运动",
    "音乐艺术", "历史人文", "自然科学", "工程技术",
    "其他",
]

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_system  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    short_id        TEXT NOT NULL UNIQUE,
    task_id         TEXT,
    url             TEXT,
    title           TEXT NOT NULL DEFAULT '未命名',
    safe_title      TEXT,
    source          TEXT DEFAULT 'url',
    status          TEXT NOT NULL DEFAULT 'completed',
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    summary_file    TEXT,
    transcript_file TEXT,
    mindmap_file    TEXT,
    translation_file TEXT,
    has_summary     INTEGER NOT NULL DEFAULT 0,
    has_transcript  INTEGER NOT NULL DEFAULT 0,
    batch_id        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_notes_short_id ON notes(short_id);
CREATE INDEX IF NOT EXISTS idx_notes_category_id ON notes(category_id);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at);
CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
"""


async def init_db():
    """初始化数据库：建表 + 预置分类"""
    async with get_db() as db:
        await db.executescript(CREATE_TABLES_SQL)

        # 预置系统分类（幂等）
        for i, cat_name in enumerate(PREDEFINED_CATEGORIES):
            await db.execute(
                "INSERT OR IGNORE INTO categories (name, sort_order, is_system) VALUES (?, ?, 1)",
                (cat_name, i),
            )
        await db.commit()
    logger.info(f"数据库初始化完成: {DB_PATH}")


async def migrate_from_json():
    """从 tasks.json + tags.json 迁移数据到 SQLite（幂等）"""
    tasks_file = TEMP_DIR / "tasks.json"
    tags_file = TEMP_DIR / "tags.json"

    if not tasks_file.exists() and not tags_file.exists():
        logger.info("无 JSON 数据需要迁移")
        return

    # 加载 JSON 数据
    tasks_data = {}
    tags_data = {}

    if tasks_file.exists():
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                tasks_data = json.load(f)
        except Exception as e:
            logger.error(f"读取 tasks.json 失败: {e}")

    if tags_file.exists():
        try:
            with open(tags_file, "r", encoding="utf-8") as f:
                tags_data = json.load(f)
        except Exception as e:
            logger.error(f"读取 tags.json 失败: {e}")

    # 同时扫描 temp 目录中的 .md 文件，补充文件系统中的笔记
    note_file_re = re.compile(
        r"^(summary|transcript|raw|mindmap|translation)_(.+)_([a-f0-9]{6})\.md$"
    )
    fs_notes: dict[str, dict] = {}  # short_id -> {files, title}
    for f in TEMP_DIR.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        match = note_file_re.match(f.name)
        if not match:
            continue
        file_type, title, short_id = match.group(1), match.group(2), match.group(3)
        if short_id not in fs_notes:
            fs_notes[short_id] = {"title": title.replace("_", " "), "files": {}}
        fs_notes[short_id]["files"][file_type] = f.name

    async with get_db() as db:
        # 检查是否已迁移过（notes 表有数据就跳过）
        cursor = await db.execute("SELECT COUNT(*) FROM notes")
        count = (await cursor.fetchone())[0]
        if count > 0:
            logger.info(f"数据库已有 {count} 条笔记，跳过迁移")
            return

        # 构建分类名→ID映射
        cursor = await db.execute("SELECT id, name FROM categories")
        cat_map = {row[1]: row[0] for row in await cursor.fetchall()}

        migrated = 0

        # 1. 从 tasks.json 迁移已完成任务
        for task_id, task in tasks_data.items():
            if task.get("status") != "completed":
                continue

            short_id = task_id.replace("-", "")[:6]
            title = task.get("video_title", "未命名")
            url = task.get("url", "")
            source = task.get("source", "url")
            safe_title = task.get("safe_title", "")
            has_summary = 1 if task.get("summary") else 0
            has_transcript = 1 if (task.get("script") or task.get("raw_script") or task.get("transcript")) else 0
            batch_id = task.get("batch_id")

            # 从 fs_notes 获取文件信息
            fs_info = fs_notes.pop(short_id, {})
            files = fs_info.get("files", {})
            summary_file = files.get("summary")
            transcript_file = files.get("transcript") or files.get("raw")
            mindmap_file = files.get("mindmap")
            translation_file = files.get("translation")

            # 查找分类
            tag_entry = tags_data.get(short_id, {})
            category_name = tag_entry.get("category", "")
            category_id = cat_map.get(category_name)

            await db.execute(
                """INSERT OR IGNORE INTO notes
                   (short_id, task_id, url, title, safe_title, source, status,
                    category_id, summary_file, transcript_file, mindmap_file,
                    translation_file, has_summary, has_transcript, batch_id)
                   VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (short_id, task_id, url, title, safe_title, source,
                 category_id, summary_file, transcript_file, mindmap_file,
                 translation_file, has_summary, has_transcript, batch_id),
            )

            # 迁移标签
            for tag_name in tag_entry.get("tags", []):
                await db.execute(
                    "INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,)
                )
                cursor = await db.execute(
                    "SELECT id FROM tags WHERE name = ?", (tag_name,)
                )
                tag_id = (await cursor.fetchone())[0]
                cursor2 = await db.execute(
                    "SELECT id FROM notes WHERE short_id = ?", (short_id,)
                )
                note_row = await cursor2.fetchone()
                if note_row:
                    await db.execute(
                        "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                        (note_row[0], tag_id),
                    )
            migrated += 1

        # 2. 从文件系统补充遗漏的笔记（有文件但不在 tasks.json 中）
        for short_id, info in fs_notes.items():
            files = info.get("files", {})
            title = info.get("title", "未命名")
            has_summary = 1 if "summary" in files else 0
            has_transcript = 1 if ("transcript" in files or "raw" in files) else 0

            if not has_summary and not has_transcript:
                continue

            tag_entry = tags_data.get(short_id, {})
            category_name = tag_entry.get("category", "")
            category_id = cat_map.get(category_name)

            await db.execute(
                """INSERT OR IGNORE INTO notes
                   (short_id, title, source, status, category_id,
                    summary_file, transcript_file, mindmap_file, translation_file,
                    has_summary, has_transcript)
                   VALUES (?, ?, 'url', 'completed', ?, ?, ?, ?, ?, ?, ?)""",
                (short_id, title, category_id,
                 files.get("summary"), files.get("transcript") or files.get("raw"),
                 files.get("mindmap"), files.get("translation"),
                 has_summary, has_transcript),
            )

            for tag_name in tag_entry.get("tags", []):
                await db.execute(
                    "INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,)
                )
                cursor = await db.execute(
                    "SELECT id FROM tags WHERE name = ?", (tag_name,)
                )
                tag_id = (await cursor.fetchone())[0]
                cursor2 = await db.execute(
                    "SELECT id FROM notes WHERE short_id = ?", (short_id,)
                )
                note_row = await cursor2.fetchone()
                if note_row:
                    await db.execute(
                        "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                        (note_row[0], tag_id),
                    )
            migrated += 1

        await db.commit()
        logger.info(f"JSON → SQLite 迁移完成，共迁移 {migrated} 条笔记")

    # 备份原 JSON 文件
    if tasks_file.exists():
        backup = tasks_file.with_suffix(".json.migrated")
        tasks_file.rename(backup)
        logger.info(f"tasks.json → {backup.name}")

    if tags_file.exists():
        backup = tags_file.with_suffix(".json.migrated")
        tags_file.rename(backup)
        logger.info(f"tags.json → {backup.name}")
