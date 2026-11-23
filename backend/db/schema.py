"""
数据库 schema 管理 — 建表、预置数据、JSON 迁移
"""
import logging

from backend.db.connection import get_db, DB_PATH

logger = logging.getLogger(__name__)

PREDEFINED_CATEGORIES = [
    "编程开发", "人工智能", "数据科学", "网络安全",
    "硬件电子", "操作系统", "设计创意", "数学科学",
    "语言学习", "商业管理", "生活技能", "健康运动",
    "音乐艺术", "历史人文", "自然科学", "工程技术",
    "其他",
]

CREATE_V2_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('url', 'upload', 'local')),
    source_uri TEXT,
    platform TEXT,
    platform_video_id TEXT,
    content_hash TEXT,
    duration_ms INTEGER CHECK (duration_ms >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'running', 'completed', 'partial_success', 'failed', 'cancel_requested', 'cancelled'
    )),
    stage TEXT,
    error TEXT,
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (asset_id, id)
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    stage TEXT,
    error TEXT,
    attempt INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    job_id TEXT,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    path TEXT NOT NULL,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (asset_id, kind, version),
    FOREIGN KEY (asset_id, job_id) REFERENCES processing_jobs(asset_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    start_ms INTEGER NOT NULL CHECK (start_ms >= 0),
    end_ms INTEGER NOT NULL CHECK (end_ms > start_ms),
    text TEXT NOT NULL,
    edited_text TEXT,
    speaker TEXT,
    language TEXT,
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    UNIQUE (asset_id, id)
);

CREATE TABLE IF NOT EXISTS highlights (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    segment_id TEXT,
    start_ms INTEGER NOT NULL CHECK (start_ms >= 0),
    end_ms INTEGER NOT NULL CHECK (end_ms > start_ms),
    text_snapshot TEXT NOT NULL,
    user_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id, segment_id) REFERENCES transcript_segments(asset_id, id)
);

CREATE TABLE IF NOT EXISTS flashcards (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    segment_id TEXT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'new'
        CHECK (review_state IN ('new', 'remembered', 'unsure', 'forgotten')),
    next_review_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id, segment_id) REFERENCES transcript_segments(asset_id, id)
);

CREATE TABLE IF NOT EXISTS search_agent_sessions (
    session_id TEXT PRIMARY KEY,
    runtime_session_id TEXT NOT NULL UNIQUE,
    messages_json TEXT NOT NULL DEFAULT '[]',
    videos_json TEXT NOT NULL DEFAULT '[]',
    search_state_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_v2_jobs_asset ON processing_jobs(asset_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_v2_jobs_status ON processing_jobs(status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_v2_events_job ON job_events(job_id, id);
CREATE INDEX IF NOT EXISTS idx_v2_artifacts_job ON artifacts(asset_id, job_id);
CREATE INDEX IF NOT EXISTS idx_v2_segments_timeline ON transcript_segments(asset_id, start_ms, end_ms, id);
CREATE INDEX IF NOT EXISTS idx_v2_highlights_segment ON highlights(asset_id, segment_id);
CREATE INDEX IF NOT EXISTS idx_v2_flashcards_segment ON flashcards(asset_id, segment_id);
CREATE INDEX IF NOT EXISTS idx_v2_search_updated ON search_agent_sessions(updated_at);
"""


async def init_db():
    """Initialize only the ViNote 2.0 asset schema."""
    async with get_db() as db:
        await db.executescript(CREATE_V2_TABLES_SQL)
        await db.commit()
    logger.info(f"数据库初始化完成: {DB_PATH}")
