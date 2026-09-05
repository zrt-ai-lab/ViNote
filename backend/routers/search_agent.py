import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.core.state import get_video_search_agent, TEMP_DIR
from backend.core.errors import internal_error
from backend.services.search_session_repository import validate_session_id
from backend.agent_runtime.harness import AgentCleanupError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except (ValueError, UnicodeError):
        raise HTTPException(status_code=400, detail="请求必须是 JSON 对象") from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="请求必须是 JSON 对象")
    return data


def _session_id(value):
    try:
        return validate_session_id(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="会话标识格式不正确") from None


@router.post("/search-agent-chat")
async def search_agent_chat(request: Request):
    try:
        data = await _body(request)
        message = data.get("message", "")
        session_id = _session_id(data.get("session_id", "default"))

        if not isinstance(message, str) or not message.strip() or len(message) > 8000:
            raise HTTPException(status_code=400, detail="请输入 1–8000 字的消息")
        message = message.strip()
        if not get_video_search_agent().is_available():
            raise HTTPException(status_code=503, detail="AI服务暂时不可用，请稍后重试")

        async def event_generator():
            try:
                async for event in get_video_search_agent().process_message(message, session_id):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.warning("Agent chat failed (%s)", type(e).__name__)
                yield f"data: {json.dumps({'type': 'error', 'content': '搜索对话失败，请重试'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Agent request failed (%s)", type(e).__name__)
        raise internal_error("搜索对话处理失败")


@router.post("/search-agent-generate-notes")
async def search_agent_generate_notes(request: Request):
    try:
        data = await _body(request)
        video_url = data.get("video_url", "")
        summary_language = data.get("summary_language", "zh")

        if not isinstance(video_url, str) or not video_url.strip() or len(video_url) > 4096:
            raise HTTPException(status_code=400, detail="视频URL不正确")
        video_url = video_url.strip()
        if not isinstance(summary_language, str) or len(summary_language) > 16:
            raise HTTPException(status_code=400, detail="笔记语言不正确")

        generation_id = str(uuid.uuid4())

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
                logger.warning("Agent notes failed (%s)", type(e).__name__)
                yield f"data: {json.dumps({'type': 'error', 'content': '笔记生成失败，请重试'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Agent notes request failed (%s)", type(e).__name__)
        raise internal_error("搜索笔记生成失败")


@router.delete("/search-agent-cancel-generation/{generation_id}")
async def cancel_note_generation(generation_id: str):
    try:
        success = get_video_search_agent().cancel_generation(generation_id)
        if success:
            logger.info(f"笔记生成任务已取消: {generation_id}")
            return {"message": "任务已取消", "generation_id": generation_id}
        else:
            raise HTTPException(status_code=404, detail="任务不存在或已完成")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消笔记生成失败: {str(e)}")
        raise internal_error("取消笔记生成失败")


@router.post("/search-agent-clear-session")
async def search_agent_clear_session(request: Request):
    try:
        data = await _body(request)
        session_id = _session_id(data.get("session_id", "default"))
        await get_video_search_agent().clear_conversation(session_id)
        logger.info(f"已清空会话: {session_id}")
        return {"message": "会话已清空", "session_id": session_id}
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=409, detail="会话正在清空，请稍后重试") from None
    except AgentCleanupError:
        raise HTTPException(status_code=503, detail="会话清理未完成，请重启服务后重试") from None
    except Exception as e:
        logger.warning("Agent clear failed (%s)", type(e).__name__)
        raise internal_error("清空搜索会话失败")


@router.get("/search-agent-session/{session_id}")
async def search_agent_session(session_id: str):
    session_id = _session_id(session_id)
    try:
        return await get_video_search_agent().get_conversation(session_id)
    except Exception as exc:
        logger.warning("Agent session read failed (%s)", type(exc).__name__)
        raise internal_error("读取搜索会话失败")
