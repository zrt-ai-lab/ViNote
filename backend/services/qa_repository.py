"""知识问答会话、来源和消息的 SQLite 数据访问层。"""
import uuid

from backend.db.connection import get_db


async def create_session(source_short_ids: list[str], content_field: str, title: str = "") -> dict:
    session_id = uuid.uuid4().hex
    async with get_db() as db:
        placeholders = ",".join("?" for _ in source_short_ids)
        cursor = await db.execute(
            f"SELECT id, short_id, title FROM notes WHERE short_id IN ({placeholders})",
            source_short_ids,
        )
        rows = await cursor.fetchall()
        by_short_id = {row[1]: row for row in rows}
        missing = [short_id for short_id in source_short_ids if short_id not in by_short_id]
        if missing:
            raise ValueError(f"笔记不存在: {', '.join(missing)}")

        session_title = title.strip()[:100] or " / ".join(
            str(by_short_id[short_id][2]) for short_id in source_short_ids[:2]
        )[:100]
        await db.execute(
            "INSERT INTO qa_sessions (id, title) VALUES (?, ?)",
            (session_id, session_title or "知识问答"),
        )
        for position, short_id in enumerate(source_short_ids):
            await db.execute(
                """INSERT INTO qa_session_sources
                   (session_id, note_id, content_field, position) VALUES (?, ?, ?, ?)""",
                (session_id, by_short_id[short_id][0], content_field, position),
            )
        await db.commit()
    return await get_session(session_id)


async def get_session(session_id: str) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, created_at, updated_at FROM qa_sessions WHERE id = ?",
            (session_id,),
        )
        session = await cursor.fetchone()
        if not session:
            return None
        cursor = await db.execute(
            """SELECT n.short_id, n.title, n.url, s.content_field
               FROM qa_session_sources s JOIN notes n ON n.id = s.note_id
               WHERE s.session_id = ? ORDER BY s.position""",
            (session_id,),
        )
        sources = [dict(row) for row in await cursor.fetchall()]
        cursor = await db.execute(
            """SELECT id, role, content, sequence, created_at FROM qa_messages
               WHERE session_id = ? ORDER BY sequence""",
            (session_id,),
        )
        messages = [dict(row) for row in await cursor.fetchall()]
    return {
        "id": session[0], "title": session[1],
        "created_at": session[2], "updated_at": session[3],
        "sources": sources, "messages": messages,
    }


async def list_sessions(limit: int = 50) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT s.id, s.title, s.created_at, s.updated_at,
                      COUNT(DISTINCT src.note_id) AS source_count,
                      COUNT(DISTINCT m.id) AS message_count
               FROM qa_sessions s
               LEFT JOIN qa_session_sources src ON src.session_id = s.id
               LEFT JOIN qa_messages m ON m.session_id = s.id
               GROUP BY s.id ORDER BY s.updated_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def add_message(session_id: str, role: str, content: str) -> dict:
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO qa_messages (session_id, role, content, sequence)
               SELECT ?, ?, ?, COALESCE(MAX(sequence), 0) + 1
               FROM qa_messages WHERE session_id = ?""",
            (session_id, role, content, session_id),
        )
        message_id = cursor.lastrowid
        row = await (await db.execute(
            "SELECT sequence FROM qa_messages WHERE id = ?", (message_id,)
        )).fetchone()
        await db.execute(
            "UPDATE qa_sessions SET updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )
        await db.commit()
        return {"id": message_id, "role": role, "content": content, "sequence": row[0]}


async def delete_session(session_id: str) -> bool:
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM qa_sessions WHERE id = ?", (session_id,))
        await db.commit()
        return cursor.rowcount > 0
