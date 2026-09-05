import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.state import (
    tasks, active_tasks, save_tasks, broadcast_task_update, TEMP_DIR,
    get_video_qa_service,
)
from backend.core.errors import internal_error, task_failure
from backend.services.media_ingestion import transcribe_local_media, transcribe_remote_media
from backend.services.qa_retrieval import MAX_TRANSCRIPT_CHARS, build_qa_context, retrieval_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class CreateQASessionRequest(BaseModel):
    source_note_ids: list[str] = Field(min_length=1, max_length=5)
    content_field: Literal["summary", "transcript"] = "transcript"
    title: str = Field(default="", max_length=100)


class AskSessionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


async def _read_session_sources(session: dict, question: str = "") -> str:
    """完整读取来源并召回相关片段，避免首篇笔记占满所有上下文。"""
    from backend.services.note_repository import get_note

    sources: list[dict] = []
    for source in session["sources"]:
        note = await get_note(source["short_id"])
        if not note:
            continue
        if source["content_field"] == "summary":
            filename = note.get("summary_file")
        else:
            filename = note.get("raw_transcript_file") or note.get("transcript_file")
        if not filename or Path(filename).name != filename:
            continue
        path = (TEMP_DIR / filename).resolve()
        if path.parent != TEMP_DIR.resolve() or not path.is_file():
            continue
        content = (await asyncio.to_thread(path.read_text, encoding="utf-8")).strip()
        if not content:
            continue
        sources.append({**source, "content": content})
    query = retrieval_query(question, session.get("messages"))
    return await asyncio.to_thread(build_qa_context, sources, query)


@router.post("/qa/sessions")
async def create_qa_session(request: CreateQASessionRequest):
    from backend.services.qa_repository import create_session

    source_ids = list(dict.fromkeys(item.strip() for item in request.source_note_ids if item.strip()))
    if not source_ids or len(source_ids) > 5:
        raise HTTPException(status_code=400, detail="请选择 1-5 条笔记")
    if any(not item.isalnum() or len(item) > 64 for item in source_ids):
        raise HTTPException(status_code=400, detail="笔记 ID 不合法")
    try:
        return await create_session(source_ids, request.content_field, request.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/qa/sessions")
async def get_qa_sessions():
    from backend.services.qa_repository import list_sessions
    return {"sessions": await list_sessions()}


@router.get("/qa/sessions/{session_id}")
async def get_qa_session(session_id: str):
    from backend.services.qa_repository import get_session
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="问答会话不存在")
    return session


@router.delete("/qa/sessions/{session_id}")
async def remove_qa_session(session_id: str):
    from backend.services.qa_repository import delete_session
    if not await delete_session(session_id):
        raise HTTPException(status_code=404, detail="问答会话不存在")
    return {"message": "问答会话已删除"}


@router.post("/qa/sessions/{session_id}/messages/stream")
async def ask_qa_session(session_id: str, request: AskSessionRequest):
    from backend.services.qa_repository import add_message, get_session

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="问答会话不存在")
    if not get_video_qa_service().is_available():
        raise HTTPException(status_code=503, detail="AI服务暂时不可用，请稍后重试")
    transcript = await _read_session_sources(session, question)
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="所选笔记没有可用内容")
    history = session["messages"][-12:]
    await add_message(session_id, "user", question)

    async def event_generator():
        answer_parts: list[str] = []
        try:
            async for content in get_video_qa_service().answer_question_stream(
                question, transcript, history=history, prepared_context=True
            ):
                answer_parts.append(content)
                yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            answer = "".join(answer_parts).strip()
            if answer:
                await add_message(session_id, "assistant", answer)
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error(f"知识问答流异常: {exc}")
            yield f"data: {json.dumps({'error': '问答生成失败，请检查AI配置和服务日志'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/transcribe-only")
async def transcribe_only(
    url: Optional[str] = Form(None),
    file_path: Optional[str] = Form(None),
):
    try:
        # 防御：如果 url 实际是本地文件路径，自动当作 file_path 处理
        if url and not file_path and os.path.exists(url) and os.path.isfile(url):
            file_path = url
            url = None

        if not url and not file_path:
            raise HTTPException(status_code=400, detail="url或file_path参数必需")
        if url and file_path:
            raise HTTPException(status_code=400, detail="url和file_path不能同时提供")

        task_id = str(uuid.uuid4())

        if file_path:
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
            if not os.path.isfile(file_path):
                raise HTTPException(status_code=400, detail="路径不是有效的文件")

            tasks[task_id] = {
                "status": "processing", "progress": 0,
                "message": "开始转录本地文件...", "transcript": None,
                "error": None, "source": "local_path", "file_path": file_path,
            }
            save_tasks(tasks)
            task = asyncio.create_task(_transcribe_local_file_task(task_id, file_path))
            active_tasks[task_id] = task
        else:
            assert url is not None
            video_url: str = url
            tasks[task_id] = {
                "status": "processing", "progress": 0,
                "message": "开始转录视频...", "transcript": None,
                "error": None, "url": video_url,
            }
            save_tasks(tasks)
            task = asyncio.create_task(_transcribe_only_task(task_id, video_url))
            active_tasks[task_id] = task

        return {"task_id": task_id, "message": "转录任务已创建"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建转录任务时出错: {str(e)}")
        raise internal_error("转录任务创建失败")


async def _transcribe_local_file_task(task_id: str, file_path: str):
    try:
        async def on_stage(stage: str):
            progress = {
                "checking_subtitles": (3, "📄 正在检查内嵌字幕..."),
                "subtitle_ready": (80, "✅ 已从内嵌字幕中提取文本"),
                "extracting_audio": (5, "正在提取音频..."),
                "transcribing_audio": (40, "正在转录音频..."),
            }.get(stage)
            if not progress:
                return
            tasks[task_id].update({"progress": progress[0], "message": progress[1]})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

        result = await transcribe_local_media(file_path, TEMP_DIR, task_id, on_stage)

        tasks[task_id].update({
            "status": "completed", "progress": 100, "message": "",
            "transcript": result.transcript, "video_title": result.video_title,
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        active_tasks.pop(task_id, None)

    except asyncio.CancelledError:
        logger.info(f"本地文件转录任务 {task_id} 被取消")
        active_tasks.pop(task_id, None)
        if task_id in tasks:
            tasks[task_id].update({"status": "cancelled", "error": "用户取消任务", "message": "❌ 任务已取消"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
    except Exception as e:
        logger.error(f"本地文件转录任务 {task_id} 失败: {str(e)}")
        active_tasks.pop(task_id, None)
        tasks[task_id].update(task_failure("本地文件转录失败，请重试"))
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])


async def _transcribe_only_task(task_id: str, url: str):
    try:
        async def on_stage(stage: str):
            progress = {
                "checking_subtitles": (5, "📄 正在检查视频字幕..."),
                "subtitle_ready": (80, "✅ 已从字幕中提取文本"),
                "downloading_audio": (10, "🎬 无可用字幕，正在下载音频..."),
                "transcribing_audio": (40, "🎤 正在转录音频..."),
            }.get(stage)
            if not progress:
                return
            tasks[task_id].update({"progress": progress[0], "message": progress[1]})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

        result = await transcribe_remote_media(url, TEMP_DIR, on_stage)

        tasks[task_id].update({
            "status": "completed", "progress": 100, "message": "",
            "transcript": result.transcript, "video_title": result.video_title,
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        active_tasks.pop(task_id, None)

    except asyncio.CancelledError:
        logger.info(f"转录任务 {task_id} 被取消")
        active_tasks.pop(task_id, None)
        if task_id in tasks:
            tasks[task_id].update({"status": "cancelled", "error": "用户取消任务", "message": "❌ 任务已取消"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
    except Exception as e:
        logger.error(f"转录任务 {task_id} 失败: {str(e)}")
        active_tasks.pop(task_id, None)
        tasks[task_id].update(task_failure("视频转录失败，请重试"))
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])


@router.post("/video-qa-stream")
async def video_qa_stream(request: Request):
    try:
        data = await request.json()
        question = str(data.get("question") or "").strip()
        transcript = str(data.get("transcript") or "").strip()
        video_url = str(data.get("video_url") or "")

        if not question:
            raise HTTPException(status_code=400, detail="问题不能为空")
        if not transcript:
            raise HTTPException(status_code=400, detail="转录文本不能为空")
        if len(question) > 4000 or len(transcript) > MAX_TRANSCRIPT_CHARS:
            raise HTTPException(status_code=400, detail="问题或转录内容过长")
        if not get_video_qa_service().is_available():
            raise HTTPException(status_code=503, detail="AI服务暂时不可用，请稍后重试")

        logger.info(f"正在处理问答流: {question[:50]}...")

        async def event_generator():
            try:
                async for content in get_video_qa_service().answer_question_stream(question, transcript, video_url):
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"问答流异常: {e}")
                yield f"data: {json.dumps({'error': '问答生成失败，请检查AI配置和服务日志'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"视频问答失败: {str(e)}")
        raise internal_error("问答请求处理失败")
