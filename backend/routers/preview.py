import logging
from fastapi import APIRouter, HTTPException
from backend.core.state import get_video_preview_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/preview-video")
async def preview_video(url: str):
    try:
        video_info = await get_video_preview_service().get_video_info(url)
        return {"success": True, "data": video_info}
    except Exception as e:
        logger.error(f"预览视频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")
