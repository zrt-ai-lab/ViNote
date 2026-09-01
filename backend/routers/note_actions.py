from typing import Literal
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.services.note_regenerator import regenerate_note

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class RegenerateRequest(BaseModel):
    targets: list[Literal["transcript", "summary", "mindmap"]] = Field(min_length=1, max_length=3)
    language: str = Field(default="zh", pattern=r"^[a-z]{2}(?:-[A-Za-z]{2,4})?$")

    @field_validator("targets")
    @classmethod
    def deduplicate_targets(cls, targets: list[str]) -> list[str]:
        return list(dict.fromkeys(targets))


@router.post("/notes/{short_id}/regenerate")
async def regenerate(short_id: str, request: RegenerateRequest):
    if not short_id.isalnum() or len(short_id) > 64:
        raise HTTPException(status_code=400, detail="笔记 ID 不合法")
    try:
        return await regenerate_note(short_id, request.targets, request.language)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if detail == "笔记不存在" else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:
        logger.error("笔记 %s 重新生成失败: %s", short_id, exc)
        raise HTTPException(status_code=502, detail="重新生成失败，请检查AI配置和服务日志") from exc
