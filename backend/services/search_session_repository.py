"""Bounded display history for video-search sessions, separate from SDK state."""
import json
import re
import uuid

from backend.db.connection import get_db


MAX_MESSAGES = 40
MAX_MESSAGE_CHARS = 16_000
MAX_HISTORY_CHARS = 128_000
MAX_VIDEOS = 100
MAX_RECORD_CHARS = 1_000_000
VIDEO_FIELD_LIMITS = {
    "title": 500,
    "url": 2048,
    "cover": 2048,
    "thumbnail": 2048,
    "duration": 32,
    "author": 200,
    "platform": 32,
}
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")


def validate_session_id(session_id: str) -> str:
    """External identifiers are data, never SDK paths or SQL fragments."""
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id must contain 1-128 letters, digits, underscores or hyphens")
    return session_id


def _messages_for_storage(messages: list[dict]) -> list[dict]:
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    selected = []
    remaining = MAX_HISTORY_CHARS
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content:
            continue
        content = content[:min(MAX_MESSAGE_CHARS, remaining)]
        selected.append({"role": message["role"], "content": content})
        remaining -= len(content)
        if len(selected) >= MAX_MESSAGES or not remaining:
            break
    return list(reversed(selected))


def _videos_for_storage(videos: list[dict]) -> list[dict]:
    if not isinstance(videos, list):
        raise ValueError("videos must be a list")
    selected = []
    # Keep the displayed order: generated-note indexes refer to this exact list.
    for video in videos[:MAX_VIDEOS]:
        if not isinstance(video, dict):
            continue
        selected.append({
            field: value[:limit]
            for field, limit in VIDEO_FIELD_LIMITS.items()
            if isinstance(value := video.get(field), str)
        })
    return selected


def _search_state_for_storage(state) -> dict:
    if state is None or isinstance(state, dict) and not state:
        return {}
    if not isinstance(state, dict):
        raise ValueError('Invalid search state')
    query, platform = state.get('query'), state.get('platform')
    page, limit = state.get('page'), state.get('max_results')
    if (not isinstance(query, str) or not 1 <= len(query) <= 200
            or not isinstance(platform, str) or platform not in {'youtube', 'bilibili', 'all'}
            or type(page) is not int or not 1 <= page <= 10
            or type(limit) is not int or not 1 <= limit <= 20):
        raise ValueError('Invalid search state')
    return {'query': query, 'platform': platform, 'page': page, 'max_results': limit}


def _decode_session(row) -> dict:
    try:
        messages = json.loads(row["messages_json"])
        videos = json.loads(row["videos_json"])
        search_state = json.loads(row['search_state_json'])
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Stored search session data is invalid") from None
    return {
        "session_id": row["session_id"],
        "runtime_session_id": row["runtime_session_id"],
        "messages": _messages_for_storage(messages),
        "videos": _videos_for_storage(videos),
        "search_state": _search_state_for_storage(search_state),
        "updated_at": row["updated_at"],
    }


async def _read_session(db, session_id: str):
    cursor = await db.execute(
        """SELECT session_id, runtime_session_id, messages_json, videos_json, search_state_json, updated_at
           FROM search_agent_sessions WHERE session_id = ?""",
        (session_id,),
    )
    return await cursor.fetchone()


async def get(session_id: str) -> dict | None:
    validate_session_id(session_id)
    async with get_db() as db:
        row = await _read_session(db, session_id)
    return _decode_session(row) if row is not None else None


async def get_or_create(session_id: str) -> dict:
    validate_session_id(session_id)
    async with get_db() as db:
        await db.execute(
            """INSERT INTO search_agent_sessions (session_id, runtime_session_id)
               VALUES (?, ?) ON CONFLICT(session_id) DO NOTHING""",
            (session_id, str(uuid.uuid4())),
        )
        row = await _read_session(db, session_id)
        await db.commit()
    return _decode_session(row)


async def save(session_id: str, messages: list[dict], videos: list[dict], *,
               search_state=None, expected_runtime_id: str | None = None) -> dict:
    """Save only display fields; SDK/system/tool/config metadata is never copied."""
    validate_session_id(session_id)
    messages_json = json.dumps(_messages_for_storage(messages), ensure_ascii=False)
    videos_json = json.dumps(_videos_for_storage(videos), ensure_ascii=False)
    state_json = json.dumps(_search_state_for_storage(search_state), ensure_ascii=False)
    if len(messages_json) + len(videos_json) > MAX_RECORD_CHARS:
        raise ValueError("Search session data exceeds the storage limit")
    async with get_db() as db:
        if expected_runtime_id is not None:
            cursor = await db.execute(
                """UPDATE search_agent_sessions SET messages_json = ?, videos_json = ?,
                   search_state_json = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                   WHERE session_id = ? AND runtime_session_id = ?""",
                (messages_json, videos_json, state_json, session_id, expected_runtime_id),
            )
            if cursor.rowcount != 1:
                raise ValueError('Search session was cleared during this turn')
        else:
            await db.execute(
                """INSERT INTO search_agent_sessions
                   (session_id, runtime_session_id, messages_json, videos_json, search_state_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   messages_json = excluded.messages_json,
                   videos_json = excluded.videos_json,
                   search_state_json = excluded.search_state_json,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (session_id, str(uuid.uuid4()), messages_json, videos_json, state_json),
            )
        row = await _read_session(db, session_id)
        await db.commit()
    return _decode_session(row)


async def reset(session_id: str) -> dict:
    """Atomically clear both lists and detach this session from its old SDK state."""
    validate_session_id(session_id)
    async with get_db() as db:
        await db.execute(
            """INSERT INTO search_agent_sessions (session_id, runtime_session_id)
               VALUES (?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   runtime_session_id = excluded.runtime_session_id,
                   messages_json = '[]', videos_json = '[]', search_state_json = '{}',
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (session_id, str(uuid.uuid4())),
        )
        row = await _read_session(db, session_id)
        await db.commit()
    return _decode_session(row)
