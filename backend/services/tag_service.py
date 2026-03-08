"""
标签服务 — 知识分类与标签管理（SQLite 版）
"""
import json
import logging

from backend.db.connection import get_db
from backend.db.schema import PREDEFINED_CATEGORIES

logger = logging.getLogger(__name__)


async def get_task_tags(short_id: str) -> dict:
    """获取指定笔记的标签和分类"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT n.id, c.name AS category_name
               FROM notes n LEFT JOIN categories c ON n.category_id = c.id
               WHERE n.short_id = ?""",
            (short_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {"tags": [], "category": ""}

        note_id = row[0]
        category = row[1] or ""

        tag_cursor = await db.execute(
            "SELECT t.name FROM note_tags nt JOIN tags t ON nt.tag_id=t.id WHERE nt.note_id=?",
            (note_id,),
        )
        tag_rows = await tag_cursor.fetchall()
        return {"tags": [r[0] for r in tag_rows], "category": category}


async def set_task_tags(short_id: str, tags: list[str], category: str = "") -> dict:
    """设置指定笔记的标签和分类"""
    from backend.services.note_repository import set_note_tags
    from backend.services.category_service import get_category_id_by_name

    # 设置分类
    if category:
        category_id = await get_category_id_by_name(category)
        if category_id:
            async with get_db() as db:
                await db.execute(
                    "UPDATE notes SET category_id = ? WHERE short_id = ?",
                    (category_id, short_id),
                )
                await db.commit()

    # 设置标签
    await set_note_tags(short_id, tags)

    return {"tags": tags, "category": category}


async def delete_task_tags(short_id: str) -> None:
    """清除笔记的所有标签"""
    from backend.services.note_repository import set_note_tags
    await set_note_tags(short_id, [])


async def get_all_tags() -> list[str]:
    """获取所有已用标签（去重排序）"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT DISTINCT t.name FROM tags t JOIN note_tags nt ON t.id=nt.tag_id ORDER BY t.name"
        )
        return [row[0] for row in await cursor.fetchall()]


async def get_all_categories() -> list[str]:
    """获取所有已用分类（去重排序）"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT DISTINCT c.name FROM categories c
               JOIN notes n ON n.category_id = c.id
               ORDER BY c.name"""
        )
        return [row[0] for row in await cursor.fetchall()]


async def get_all_tags_with_counts() -> list[dict]:
    """获取所有标签及其关联笔记数量（包含 0 计数的标签）"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT t.name, COUNT(nt.note_id) AS note_count
               FROM tags t
               LEFT JOIN note_tags nt ON t.id = nt.tag_id
               GROUP BY t.id, t.name
               ORDER BY note_count DESC, t.name"""
        )
        return [{"name": row[0], "note_count": row[1]} for row in await cursor.fetchall()]


async def create_tag(name: str) -> dict:
    """创建独立标签（无需关联笔记）"""
    name = name.strip()
    if not name:
        raise ValueError("标签名不能为空")

    async with get_db() as db:
        # 检查是否已存在
        cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (name,))
        if await cursor.fetchone():
            raise ValueError(f"标签「{name}」已存在")

        await db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        await db.commit()
        return {"name": name, "note_count": 0}


async def rename_tag(old_name: str, new_name: str) -> bool:
    """重命名标签"""
    old_name = old_name.strip()
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("新标签名不能为空")

    async with get_db() as db:
        # 检查旧标签是否存在
        cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (old_name,))
        row = await cursor.fetchone()
        if not row:
            return False

        # 检查新名称是否冲突
        cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (new_name,))
        if await cursor.fetchone():
            raise ValueError(f"标签「{new_name}」已存在")

        await db.execute("UPDATE tags SET name = ? WHERE name = ?", (new_name, old_name))
        await db.commit()
        return True


async def delete_tag(tag_name: str) -> bool:
    """删除标签及其所有关联"""
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        row = await cursor.fetchone()
        if not row:
            return False

        tag_id = row[0]
        await db.execute("DELETE FROM note_tags WHERE tag_id = ?", (tag_id,))
        await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        await db.commit()
        return True


async def auto_tag_from_summary(short_id: str, summary: str, title: str = "") -> dict:
    """用 AI 从摘要中自动提取标签和分类"""
    from backend.core.ai_client import get_async_openai_client, is_openai_available

    if not is_openai_available():
        return {"tags": [], "category": "其他"}

    client = get_async_openai_client()
    if not client:
        return {"tags": [], "category": "其他"}

    categories_str = "、".join(PREDEFINED_CATEGORIES)

    prompt = f"""根据以下视频笔记内容，提取关键标签和分类。

标题: {title}
内容摘要（截取前2000字）:
{summary[:2000]}

请返回 JSON 格式：
{{
  "tags": ["标签1", "标签2", "标签3"],  // 3-5个关键标签，简短精确
  "category": "分类名"  // 从以下分类中选择最合适的一个: {categories_str}
}}

只返回 JSON，不要其他文字。"""

    try:
        from backend.config.ai_config import get_ai_config
        ai_config = get_ai_config()

        response = await client.chat.completions.create(
            model=ai_config.openai.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        result_text = response.choices[0].message.content.strip()
        # 提取 JSON
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        result = json.loads(result_text)

        tags = result.get("tags", [])[:5]
        category = result.get("category", "其他")
        if category not in PREDEFINED_CATEGORIES:
            category = "其他"

        entry = await set_task_tags(short_id, tags, category)
        logger.info(f"自动标签: {short_id} -> {tags}, 分类: {category}")
        return entry

    except Exception as e:
        logger.warning(f"自动标签失败 {short_id}: {e}")
        return {"tags": [], "category": "其他"}
