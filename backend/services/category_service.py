"""
分类管理服务 — CRUD + 笔记计数
"""
import logging
from typing import Optional

from backend.db.connection import get_db

logger = logging.getLogger(__name__)


async def list_categories(include_counts: bool = True) -> list[dict]:
    """列出所有分类，可选附带笔记计数"""
    async with get_db() as db:
        if include_counts:
            cursor = await db.execute(
                """SELECT c.id, c.name, c.sort_order, c.is_system, c.created_at,
                          COUNT(n.id) AS note_count
                   FROM categories c
                   LEFT JOIN notes n ON n.category_id = c.id
                   GROUP BY c.id
                   ORDER BY c.sort_order, c.name"""
            )
        else:
            cursor = await db.execute(
                """SELECT id, name, sort_order, is_system, created_at, 0 AS note_count
                   FROM categories ORDER BY sort_order, name"""
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "sort_order": row[2],
                "is_system": bool(row[3]),
                "created_at": row[4],
                "note_count": row[5],
            }
            for row in rows
        ]


async def create_category(name: str, sort_order: int = 0) -> dict:
    """创建自定义分类"""
    async with get_db() as db:
        try:
            cursor = await db.execute(
                "INSERT INTO categories (name, sort_order, is_system) VALUES (?, ?, 0)",
                (name.strip(), sort_order),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "name": name.strip(), "sort_order": sort_order, "is_system": False}
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ValueError(f"分类 '{name}' 已存在")
            raise


async def update_category(category_id: int, *, name: Optional[str] = None, sort_order: Optional[int] = None) -> bool:
    """修改分类名或排序"""
    async with get_db() as db:
        updates = []
        params: list = []
        if name is not None:
            updates.append("name = ?")
            params.append(name.strip())
        if sort_order is not None:
            updates.append("sort_order = ?")
            params.append(sort_order)
        if not updates:
            return False
        params.append(category_id)
        cursor = await db.execute(
            f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", params
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_category(category_id: int) -> bool:
    """删除分类（笔记的 category_id 自动置 NULL，由 ON DELETE SET NULL 处理）"""
    async with get_db() as db:
        # 不允许删除 is_system=1 的"其他"分类
        cursor = await db.execute(
            "SELECT is_system, name FROM categories WHERE id = ?", (category_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        if row[0] and row[1] == "其他":
            raise ValueError("不能删除默认分类「其他」")

        cursor = await db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_category_id_by_name(name: str) -> Optional[int]:
    """按名称查分类ID"""
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM categories WHERE name = ?", (name,))
        row = await cursor.fetchone()
        return row[0] if row else None
