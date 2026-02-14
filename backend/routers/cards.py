"""
知识卡片 API 路由

POST /api/generate-cards  — 流式生成知识卡片（SSE）
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.services.card_generator import CardGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/generate-cards")
async def generate_cards(request: Request):
    """
    流式生成知识卡片。

    Request body:
        {
            "source": "notes" | "text" | "qa",
            "content": "...",
            "count": 5          // 5-10
        }

    SSE events:
        data: {"type": "card", "data": {...}}
        data: {"type": "done"}
        data: {"type": "error", "message": "..."}
    """
    try:
        data = await request.json()
        content = (data.get("content") or "").strip()
        source = data.get("source", "text")
        style = data.get("style", "keypoint")
        count = int(data.get("count", 5))

        if not content:
            raise HTTPException(status_code=400, detail="内容不能为空")
        if source not in ("notes", "text", "qa"):
            source = "text"
        if style not in ("anki", "keypoint", "concept", "cornell"):
            style = "keypoint"
        count = max(3, min(count, 10))

        generator = CardGenerator()
        if not generator.is_available():
            raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请检查配置")

        async def event_stream():
            try:
                async for item in generator.generate_cards_stream(content, count, source, style):
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"卡片生成流异常: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成知识卡片失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
