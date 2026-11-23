import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.services.video_search_agent import VideoSearchAgent
from backend.services.search_providers.manager import SearchProviderManager
from backend.services.search_session_repository import validate_session_id
from backend.services import search_session_repository as sessions
from backend.repositories import assets, jobs
from backend.agent_runtime.harness import AgentCleanupError
def internal_error(message: str) -> HTTPException:
    return HTTPException(status_code=500, detail=message)
_agent: VideoSearchAgent | None = None

def get_agent() -> VideoSearchAgent:
    global _agent
    if _agent is None:
        _agent = VideoSearchAgent(SearchProviderManager())
    return _agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/search")


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


@router.post("/sessions/{session_id}/messages")
async def search_agent_chat(session_id: str, request: Request):
    try:
        data = await _body(request)
        message = data.get("message", "")
        session_id = _session_id(session_id)

        if not isinstance(message, str) or not message.strip() or len(message) > 8000:
            raise HTTPException(status_code=400, detail="请输入 1–8000 字的消息")
        message = message.strip()
        if not get_agent().is_available():
            raise HTTPException(status_code=503, detail="AI服务暂时不可用，请稍后重试")

        async def event_generator():
            try:
                async for event in get_agent().process_message(message, session_id):
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


@router.post("/sessions/{session_id}/clear")
async def search_agent_clear_session(session_id: str, request: Request):
    try:
        data = await _body(request)
        session_id = _session_id(session_id)
        await get_agent().clear_conversation(session_id)
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


@router.get("/sessions/{session_id}")
async def search_agent_session(session_id: str):
    session_id = _session_id(session_id)
    try:
        return await get_agent().get_conversation(session_id)
    except Exception as exc:
        logger.warning("Agent session read failed (%s)", type(exc).__name__)
        raise internal_error("读取搜索会话失败")


@router.post("/sessions/{session_id}/import")
async def import_search_result(session_id: str, request: Request):
    data = await _body(request)
    index = data.get("video_index")
    if type(index) is not int or index < 0:
        raise HTTPException(status_code=400, detail="video_index 不正确")
    record = await sessions.get(session_id)
    if record is None or index >= len(record["videos"]):
        raise HTTPException(status_code=404, detail="搜索结果不存在")
    video = record["videos"][index]
    asset = await assets.create(video.get("title") or "搜索结果", "url", source_uri=video["url"], platform=video.get("platform"))
    job = await jobs.create(asset["id"], "transcribe")
    return {"asset_id": asset["id"], "job_id": job["id"], "title": asset["title"], "url": asset["source_uri"]}
