"""
标签 & 分类管理路由 — 标签 CRUD、AI自动标签、分类 CRUD
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.tag_service import (
    get_task_tags,
    set_task_tags,
    delete_task_tags,
    get_all_tags,
    get_all_tags_with_counts,
    create_tag,
    rename_tag,
    delete_tag,
    auto_tag_from_summary,
)
from backend.db.schema import PREDEFINED_CATEGORIES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── 标签端点 ──────────────────────────────────────────

@router.get("/tags/stats")
async def list_tags_with_counts():
    """获取所有标签及笔记计数"""
    return {"tags": await get_all_tags_with_counts()}


class CreateTagRequest(BaseModel):
    name: str


@router.post("/tags")
async def create_tag_endpoint(req: CreateTagRequest):
    """创建独立标签"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="标签名不能为空")
    try:
        return await create_tag(req.name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


class RenameTagRequest(BaseModel):
    new_name: str


@router.put("/tags/{tag_name}")
async def rename_tag_endpoint(tag_name: str, req: RenameTagRequest):
    """重命名标签"""
    if not req.new_name.strip():
        raise HTTPException(status_code=400, detail="新标签名不能为空")
    try:
        ok = await rename_tag(tag_name, req.new_name)
        if not ok:
            raise HTTPException(status_code=404, detail="标签不存在")
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/tags/{tag_name}")
async def delete_tag_endpoint(tag_name: str):
    """删除标签及其关联"""
    ok = await delete_tag(tag_name)
    if not ok:
        raise HTTPException(status_code=404, detail="标签不存在")
    return {"ok": True}


@router.get("/tags/all")
async def list_all_tags():
    """获取所有已用标签和分类"""
    return {
        "tags": await get_all_tags(),
        "predefined_categories": PREDEFINED_CATEGORIES,
    }


@router.get("/tags/task/{short_id}")
async def get_tags(short_id: str):
    """获取指定任务的标签"""
    return await get_task_tags(short_id)


class SetTagsRequest(BaseModel):
    tags: list[str] = []
    category: str = ""


@router.put("/tags/task/{short_id}")
async def update_tags(short_id: str, req: SetTagsRequest):
    """设置指定任务的标签和分类"""
    return await set_task_tags(short_id, req.tags, req.category)


@router.delete("/tags/task/{short_id}")
async def remove_tags(short_id: str):
    """删除指定任务的标签"""
    await delete_task_tags(short_id)
    return {"ok": True}


class AutoTagRequest(BaseModel):
    summary: str
    title: str = ""


@router.post("/tags/auto/{short_id}")
async def auto_tag(short_id: str, req: AutoTagRequest):
    """AI 自动从摘要中提取标签和分类"""
    if not req.summary.strip():
        raise HTTPException(status_code=400, detail="摘要内容不能为空")
    result = await auto_tag_from_summary(short_id, req.summary, req.title)
    return result


# ── 分类 CRUD 端点 ──────────────────────────────────────

@router.get("/categories")
async def list_categories():
    """列出所有分类（含笔记计数）"""
    from backend.services.category_service import list_categories as _list
    return {"categories": await _list(include_counts=True)}


class CreateCategoryRequest(BaseModel):
    name: str
    sort_order: int = 0


@router.post("/categories")
async def create_category(req: CreateCategoryRequest):
    """创建自定义分类"""
    from backend.services.category_service import create_category as _create
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="分类名不能为空")
    try:
        result = await _create(req.name, req.sort_order)
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


@router.put("/categories/{category_id}")
async def update_category(category_id: int, req: UpdateCategoryRequest):
    """修改分类名/排序"""
    from backend.services.category_service import update_category as _update
    ok = await _update(category_id, name=req.name, sort_order=req.sort_order)
    if not ok:
        raise HTTPException(status_code=404, detail="分类不存在")
    return {"ok": True}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int):
    """删除分类（笔记自动移到未分类）"""
    from backend.services.category_service import delete_category as _delete
    try:
        ok = await _delete(category_id)
        if not ok:
            raise HTTPException(status_code=404, detail="分类不存在")
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 笔记分类修改 ──────────────────────────────────────

class UpdateNoteCategoryRequest(BaseModel):
    category_id: Optional[int] = None


@router.put("/notes/{short_id}/category")
async def update_note_category(short_id: str, req: UpdateNoteCategoryRequest):
    """修改笔记的分类"""
    from backend.services.note_repository import update_note_category as _update
    ok = await _update(short_id, req.category_id)
    if not ok:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"ok": True}
