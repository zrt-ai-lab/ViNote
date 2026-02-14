import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.core.state import get_video_search_agent, TEMP_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/search-agent-chat")
async def search_agent_chat(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        session_id = data.get("session_id", "default")

        if not message:
            raise HTTPException(status_code=400, detail="消息不能为空")
        if not get_video_search_agent().is_available():
            raise HTTPException(status_code=503, detail="AI服务暂时不可用，请稍后重试")

        logger.info(f"处理Agent消息: {message[:50]}...")

        async def event_generator():
            try:
                async for event in get_video_search_agent().process_message(message, session_id):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Agent聊天异常: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索Agent聊天失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.post("/search-agent-generate-notes")
async def search_agent_generate_notes(request: Request):
    try:
        data = await request.json()
        video_url = data.get("video_url", "").strip()
        summary_language = data.get("summary_language", "zh")

        if not video_url:
            raise HTTPException(status_code=400, detail="视频URL不能为空")

        generation_id = str(uuid.uuid4())
        logger.info(f"为视频生成笔记: {video_url}, 任务ID: {generation_id}")

        async def event_generator():
            try:
                yield f"data: {json.dumps({'type': 'generation_id', 'generation_id': generation_id}, ensure_ascii=False)}\n\n"
                async for event in get_video_search_agent().generate_notes_for_video(
                    video_url=video_url,
                    temp_dir=TEMP_DIR,
                    summary_language=summary_language,
                    generation_id=generation_id,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"生成笔记异常: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成笔记失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.delete("/search-agent-cancel-generation/{generation_id}")
async def cancel_note_generation(generation_id: str):
    try:
        success = get_video_search_agent().cancel_generation(generation_id)
        if success:
            logger.info(f"笔记生成任务已取消: {generation_id}")
            return {"message": "任务已取消", "generation_id": generation_id}
        else:
            raise HTTPException(status_code=404, detail="任务不存在或已完成")
    except Exception as e:
        logger.error(f"取消笔记生成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"取消失败: {str(e)}")


@router.post("/search-agent-clear-session")
async def search_agent_clear_session(request: Request):
    try:
        data = await request.json()
        session_id = data.get("session_id", "default")
        get_video_search_agent().clear_conversation(session_id)
        logger.info(f"已清空会话: {session_id}")
        return {"message": "会话已清空", "session_id": session_id}
    except Exception as e:
        logger.error(f"清空会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")
