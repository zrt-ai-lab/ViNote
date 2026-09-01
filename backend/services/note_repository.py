"""
笔记数据访问层 — SQLite CRUD + 分页/筛选/排序
"""
import json
import logging
from typing import Optional

from backend.db.connection import get_db

logger = logging.getLogger(__name__)


async def save_note(
    short_id: str,
    *,
    task_id: str = "",
    url: str = "",
    title: str = "未命名",
    safe_title: str = "",
    source: str = "url",
    category_id: Optional[int] = None,
    summary_file: Optional[str] = None,
    transcript_file: Optional[str] = None,
    mindmap_file: Optional[str] = None,
    translation_file: Optional[str] = None,
    has_summary: bool = False,
    has_transcript: bool = False,
    batch_id: Optional[str] = None,
    completed_at: Optional[str] = None,
    raw_transcript_file: Optional[str] = None,
    warnings: Optional[list[str]] = None,
) -> int:
    """保存或更新一条笔记。返回 note id。"""
    async with get_db() as db:
        # upsert by short_id
        cursor = await db.execute("SELECT id FROM notes WHERE short_id = ?", (short_id,))
        existing = await cursor.fetchone()

        if existing:
            await db.execute(
                """UPDATE notes SET
                    task_id=?, url=?, title=?, safe_title=?, source=?,
                    category_id=?, summary_file=?, transcript_file=?,
                    mindmap_file=?, translation_file=?,
                    has_summary=?, has_transcript=?, batch_id=?, completed_at=?,
                    raw_transcript_file=?, warnings_json=?
                   WHERE short_id=?""",
                (task_id, url, title, safe_title, source,
                 category_id, summary_file, transcript_file,
                 mindmap_file, translation_file,
                 int(has_summary), int(has_transcript), batch_id, completed_at,
                 raw_transcript_file, json.dumps(warnings or [], ensure_ascii=False),
                 short_id),
            )
            await db.commit()
            return existing[0]
        else:
            cursor = await db.execute(
                """INSERT INTO notes
                   (short_id, task_id, url, title, safe_title, source, status,
                    category_id, summary_file, transcript_file, mindmap_file,
                    translation_file, has_summary, has_transcript, batch_id, completed_at,
                    raw_transcript_file, warnings_json)
                   VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (short_id, task_id, url, title, safe_title, source,
                 category_id, summary_file, transcript_file, mindmap_file,
                 translation_file, int(has_summary), int(has_transcript),
                 batch_id, completed_at, raw_transcript_file,
                 json.dumps(warnings or [], ensure_ascii=False)),
            )
            await db.commit()
            return cursor.lastrowid


async def list_notes(
    *,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict:
    """分页查询笔记列表，带筛选/排序。返回 {tasks, total, page, page_size}。"""
    allowed_sort = {"created_at", "title", "completed_at"}
    if sort_by not in allowed_sort:
        sort_by = "created_at"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"

    async with get_db() as db:
        where_clauses = []
        params: list = []

        if category:
            where_clauses.append("c.name = ?")
            params.append(category)

        if tag:
            where_clauses.append(
                "n.id IN (SELECT nt.note_id FROM note_tags nt JOIN tags t ON nt.tag_id=t.id WHERE t.name=?)"
            )
            params.append(tag)

        if search:
            where_clauses.append("n.title LIKE ?")
            params.append(f"%{search}%")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Count total
        count_sql = f"""
            SELECT COUNT(DISTINCT n.id)
            FROM notes n
            LEFT JOIN categories c ON n.category_id = c.id
            {where_sql}
        """
        cursor = await db.execute(count_sql, params)
        total = (await cursor.fetchone())[0]

        # Fetch paginated results with inline tags + category
        query_sql = f"""
            SELECT n.id, n.short_id, n.task_id, n.url, n.title, n.safe_title,
                   n.source, n.status, n.has_summary, n.has_transcript,
                   n.batch_id, n.created_at, n.completed_at,
                   c.name AS category_name, c.id AS category_id
            FROM notes n
            LEFT JOIN categories c ON n.category_id = c.id
            {where_sql}
            ORDER BY n.{sort_by} {sort_order}
            LIMIT ? OFFSET ?
        """
        offset = (page - 1) * page_size
        cursor = await db.execute(query_sql, [*params, page_size, offset])
        rows = await cursor.fetchall()

        tags_by_note: dict[int, list[str]] = {}
        if rows:
            note_ids = [row[0] for row in rows]
            placeholders = ",".join("?" for _ in note_ids)
            tag_cursor = await db.execute(
                f"SELECT nt.note_id, t.name FROM note_tags nt "
                f"JOIN tags t ON nt.tag_id=t.id WHERE nt.note_id IN ({placeholders})",
                note_ids,
            )
            for note_id, tag_name in await tag_cursor.fetchall():
                tags_by_note.setdefault(note_id, []).append(tag_name)

        tasks = []
        for row in rows:
            note_id = row[0]
            short_id = row[1]

            tasks.append({
                "task_id": short_id,
                "video_title": row[4],  # title
                "type": "notes" if row[8] else "qa",  # has_summary
                "has_summary": bool(row[8]),
                "has_transcript": bool(row[9]),
                "category": row[13] or "",  # category_name
                "category_id": row[14],
                "tags": tags_by_note.get(note_id, []),
                "created_at": row[11],  # created_at
                "url": row[3] or "",
                "source": row[6] or "url",
                "batch_id": row[10] or "",
            })

        return {
            "tasks": tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
        }


async def get_note(short_id: str) -> Optional[dict]:
    """获取单条笔记详情（按 short_id）"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT n.*, c.name AS category_name
               FROM notes n LEFT JOIN categories c ON n.category_id = c.id
               WHERE n.short_id = ?""",
            (short_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return await _row_to_note(db, row)


async def get_note_by_task_id(task_id: str) -> Optional[dict]:
    """获取单条笔记详情（按完整 task_id / UUID）"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT n.*, c.name AS category_name
               FROM notes n LEFT JOIN categories c ON n.category_id = c.id
               WHERE n.task_id = ?""",
            (task_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return await _row_to_note(db, row)


async def _row_to_note(db, row) -> dict:
    """将数据库行转为笔记 dict"""
    note_id = row[0]
    tag_cursor = await db.execute(
        "SELECT t.name FROM note_tags nt JOIN tags t ON nt.tag_id=t.id WHERE nt.note_id=?",
        (note_id,),
    )
    tag_rows = await tag_cursor.fetchall()

    try:
        warnings = json.loads(row[19] or "[]")
        if not isinstance(warnings, list):
            warnings = []
    except (json.JSONDecodeError, TypeError):
        warnings = []

    return {
        "id": row[0],
        "short_id": row[1],
        "task_id": row[2],
        "url": row[3],
        "title": row[4],
        "safe_title": row[5],
        "source": row[6],
        "status": row[7],
        "category_id": row[8],
        "summary_file": row[9],
        "transcript_file": row[10],
        "mindmap_file": row[11],
        "translation_file": row[12],
        "category_name": row[-1],
        "has_summary": bool(row[13]),
        "has_transcript": bool(row[14]),
        "batch_id": row[15],
        "created_at": row[16],
        "completed_at": row[17],
        "raw_transcript_file": row[18],
        "warnings": warnings,
        "tags": [r[0] for r in tag_rows],
    }


async def update_note_artifacts(short_id: str, **artifacts: Optional[str]) -> bool:
    """只更新允许的产物文件字段，避免覆盖笔记其他元数据。"""
    allowed = {
        "raw_transcript_file", "transcript_file", "summary_file",
        "mindmap_file", "translation_file",
    }
    values = {key: value for key, value in artifacts.items() if key in allowed}
    if not values:
        return False

    assignments = [f"{key} = ?" for key in values]
    if "summary_file" in values:
        assignments.append("has_summary = ?")
        values["has_summary"] = 1 if values["summary_file"] else 0
    if "transcript_file" in values:
        assignments.append("has_transcript = ?")
        values["has_transcript"] = 1 if values["transcript_file"] else 0

    async with get_db() as db:
        cursor = await db.execute(
            f"UPDATE notes SET {', '.join(assignments)} WHERE short_id = ?",
            [*values.values(), short_id],
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_note(short_id: str) -> bool:
    """删除一条笔记（CASCADE 自动删 note_tags）"""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM notes WHERE short_id = ?", (short_id,))
        await db.commit()
        return cursor.rowcount > 0


async def delete_all_notes() -> int:
    """删除所有笔记"""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM notes")
        await db.commit()
        return cursor.rowcount


async def count_notes() -> int:
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM notes")
        return (await cursor.fetchone())[0]


async def list_notes_by_batch(batch_id: str) -> list[dict]:
    """按 batch_id 查询所有已完成笔记（批量状态查询用）"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT short_id, title, status FROM notes WHERE batch_id = ?""",
            (batch_id,),
        )
        rows = await cursor.fetchall()
        return [
            {"task_id": row[0], "video_title": row[1], "status": row[2] or "completed"}
            for row in rows
        ]


async def update_note_category(short_id: str, category_id: Optional[int]) -> bool:
    """修改笔记分类"""
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE notes SET category_id = ? WHERE short_id = ?",
            (category_id, short_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def set_note_tags(short_id: str, tag_names: list[str]) -> None:
    """设置笔记标签（替换全部）"""
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM notes WHERE short_id = ?", (short_id,))
        row = await cursor.fetchone()
        if not row:
            return
        note_id = row[0]

        # 清除旧标签
        await db.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))

        # 插入新标签
        for tag_name in tag_names:
            tag_name = tag_name.strip()
            if not tag_name:
                continue
            await db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
            cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = (await cursor.fetchone())[0]
            await db.execute(
                "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (note_id, tag_id),
            )

        await db.commit()
