"""Small row helpers; SQL identifiers are supplied only by repository code."""
from uuid import uuid4

from backend.db.connection import get_db


def new_id() -> str:
    return str(uuid4())


async def fetch_one(db, sql, params=()) -> dict | None:
    async with db.execute(sql, params) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row is not None else None


async def read_one(sql, params=()) -> dict | None:
    async with get_db() as db:
        return await fetch_one(db, sql, params)


async def read_all(sql, params=()) -> list[dict]:
    async with get_db() as db, db.execute(sql, params) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def write_one(sql, params=()) -> dict | None:
    async with get_db() as db:
        row = await fetch_one(db, sql, params)
        await db.commit()
        return row


async def insert(table: str, **fields) -> dict:
    fields = {"id": new_id(), **fields}
    placeholders = ", ".join("?" for _ in fields)
    return await write_one(
        f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({placeholders}) RETURNING *",
        tuple(fields.values()),
    )


async def delete_row(table: str, row_id: str) -> bool:
    return await write_one(f"DELETE FROM {table} WHERE id = ? RETURNING id", (row_id,)) is not None
