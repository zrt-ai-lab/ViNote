"""
数据库连接管理 — aiosqlite 连接池
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from backend.core.state import TEMP_DIR

logger = logging.getLogger(__name__)

DB_PATH = TEMP_DIR / "vinote.db"


@asynccontextmanager
async def get_db():
    """获取 aiosqlite 数据库连接（async context manager）"""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        await db.close()
