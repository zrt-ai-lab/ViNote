"""SQLite 正文检索：本地内容缓存，可用时由 FTS5 trigram 加速子串查询。"""
import asyncio
import logging
from pathlib import Path

from backend.core.state import TEMP_DIR

logger = logging.getLogger(__name__)
CONTENT_FIELDS = ("raw_transcript_file", "transcript_file", "summary_file")


async def init_search_schema(db) -> None:
    await db.execute("""CREATE TABLE IF NOT EXISTS note_search (
        note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
        body TEXT NOT NULL DEFAULT ''
    )""")
    # 老版本 SQLite/精简发行版可能未编译 trigram；仍提供等价子串搜索。
    try:
        await db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS note_search_fts
            USING fts5(body, content='note_search', content_rowid='note_id', tokenize='trigram')""")
    except Exception as exc:
        import sqlite3
        if not isinstance(exc, sqlite3.OperationalError) or not any(
            marker in str(exc).lower() for marker in ("no such module", "no such tokenizer")
        ):
            raise
        logger.info("SQLite 未提供 FTS5 trigram，正文搜索使用兼容模式")
        return
    cursor = await db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='note_search_ai'")
    needs_rebuild = await cursor.fetchone() is None
    await db.executescript("""
        CREATE TRIGGER IF NOT EXISTS note_search_ai AFTER INSERT ON note_search BEGIN
            INSERT INTO note_search_fts(rowid, body) VALUES (new.note_id, new.body);
        END;
        CREATE TRIGGER IF NOT EXISTS note_search_ad AFTER DELETE ON note_search BEGIN
            INSERT INTO note_search_fts(note_search_fts, rowid, body) VALUES ('delete', old.note_id, old.body);
        END;
        CREATE TRIGGER IF NOT EXISTS note_search_au AFTER UPDATE ON note_search BEGIN
            INSERT INTO note_search_fts(note_search_fts, rowid, body) VALUES ('delete', old.note_id, old.body);
            INSERT INTO note_search_fts(rowid, body) VALUES (new.note_id, new.body);
        END;
    """)
    if needs_rebuild:
        await db.execute("INSERT INTO note_search_fts(note_search_fts) VALUES ('rebuild')")


def _read_content(filenames: list[str]) -> str:
    root = TEMP_DIR.resolve()
    sections = []
    for filename in dict.fromkeys(filenames):
        if not filename or Path(filename).name != filename:
            continue
        path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            continue
        try:
            sections.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            logger.warning("笔记内容暂不可读，跳过该搜索来源")
    return "\n\n".join(sections)


async def refresh_note_search(db, short_id: str) -> None:
    """在调用方事务内同步缓存，文件更新与索引更新使用同一次笔记操作。"""
    cursor = await db.execute(
        "SELECT id, raw_transcript_file, transcript_file, summary_file FROM notes WHERE short_id=?",
        (short_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return
    body = await asyncio.to_thread(_read_content, list(row[1:]))
    await db.execute(
        "INSERT INTO note_search(note_id, body) VALUES (?, ?) "
        "ON CONFLICT(note_id) DO UPDATE SET body=excluded.body",
        (row[0], body),
    )


async def backfill_note_search() -> None:
    """启动时只回填缺少索引的旧笔记，幂等且分批提交。"""
    from backend.db.connection import get_db
    while True:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT n.short_id FROM notes n LEFT JOIN note_search s ON s.note_id=n.id "
                "WHERE s.note_id IS NULL ORDER BY n.id LIMIT 100"
            )
            rows = await cursor.fetchall()
            if not rows:
                return
            for row in rows:
                await refresh_note_search(db, row[0])
            await db.commit()


async def search_condition(db, query: str) -> tuple[str, list[str]]:
    """参数化字面子串搜索；中文一二字和 LIKE 通配符具有明确语义。"""
    cursor = await db.execute("SELECT 1 FROM sqlite_master WHERE name='note_search_fts' AND type='table'")
    fts_available = await cursor.fetchone() is not None
    # LIKE 的 %/_ 按字面匹配，而不是意外扩展为全量笔记。
    literal = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    title_condition = "n.title LIKE ? ESCAPE '\\'"
    if fts_available and len(query) >= 3 and "\x00" not in query:
        phrase = '"' + query.replace('"', '""') + '"'
        return (
            f"({title_condition} OR n.id IN (SELECT rowid FROM note_search_fts WHERE note_search_fts MATCH ?))",
            [f"%{literal}%", phrase],
        )
    return (
        f"({title_condition} OR n.id IN (SELECT note_id FROM note_search WHERE body LIKE ? ESCAPE '\\'))",
        [f"%{literal}%", f"%{literal}%"],
    )
