"""Initialize the ViNote 2.0 runtime."""

from backend.db.connection import get_db
from backend.db.schema import CREATE_V2_TABLES_SQL


async def startup_event():
    """Create the asset schema without running v1 repair or migration hooks."""
    async with get_db() as db:
        await db.executescript(CREATE_V2_TABLES_SQL)
        await db.commit()
