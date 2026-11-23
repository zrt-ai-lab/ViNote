"""Media asset metadata and recycle-bin operations."""
from ._sqlite import insert, read_all, read_one, write_one


async def create(
    title: str, source_type: str, *, source_uri: str | None = None,
    platform: str | None = None, platform_video_id: str | None = None,
    content_hash: str | None = None, duration_ms: int | None = None,
) -> dict:
    return await insert(
        "media_assets", title=title, source_type=source_type, source_uri=source_uri,
        platform=platform, platform_video_id=platform_video_id, content_hash=content_hash,
        duration_ms=duration_ms,
    )


async def get(asset_id: str, *, include_deleted: bool = False) -> dict | None:
    condition = "" if include_deleted else " AND deleted_at IS NULL"
    return await read_one("SELECT * FROM media_assets WHERE id = ?" + condition, (asset_id,))


async def list_assets(*, include_deleted: bool = False) -> list[dict]:
    condition = "" if include_deleted else " WHERE deleted_at IS NULL"
    return await read_all("SELECT * FROM media_assets" + condition + " ORDER BY created_at, id")


async def rename(asset_id: str, title: str) -> dict | None:
    return await write_one(
        "UPDATE media_assets SET title = ? WHERE id = ? AND deleted_at IS NULL RETURNING *",
        (title, asset_id),
    )


async def delete(asset_id: str) -> bool:
    row = await write_one(
        "UPDATE media_assets SET deleted_at = datetime('now') "
        "WHERE id = ? AND deleted_at IS NULL RETURNING id", (asset_id,),
    )
    return row is not None


async def restore(asset_id: str) -> dict | None:
    return await write_one(
        "UPDATE media_assets SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL RETURNING *",
        (asset_id,),
    )
