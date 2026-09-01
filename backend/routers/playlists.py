from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging

from backend.services.playlist_resolver import resolve_playlist

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class PlaylistRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


@router.post("/playlists/expand")
async def expand_playlist(request: PlaylistRequest):
    try:
        return await resolve_playlist(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("合集解析失败: %s", exc)
        raise HTTPException(status_code=502, detail="合集解析失败，请检查链接或登录状态") from exc
