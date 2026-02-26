import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import StreamingResponse

from backend.core.state import (
    tasks, active_tasks, save_tasks, broadcast_task_update, TEMP_DIR,
    get_video_qa_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/transcribe-only")
async def transcribe_only(
    url: Optional[str] = Form(None),
    file_path: Optional[str] = Form(None),
):
    try:
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
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


async def _transcribe_local_file_task(task_id: str, file_path: str):
    from backend.services.audio_transcriber import AudioTranscriber
    from backend.utils.file_handler import extract_audio_from_file, cleanup_temp_audio

    try:
        audio_transcriber = AudioTranscriber()
        video_title = Path(file_path).stem

        tasks[task_id].update({"progress": 5, "message": "正在提取音频..."})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

        audio_path, needs_cleanup = await extract_audio_from_file(file_path, TEMP_DIR, task_id)

        try:
            tasks[task_id].update({"progress": 40, "message": "正在转录音频..."})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

            transcript = await audio_transcriber.transcribe_audio(audio_path)
        finally:
            cleanup_temp_audio(audio_path, needs_cleanup)

        tasks[task_id].update({
            "status": "completed", "progress": 100, "message": "",
            "transcript": transcript, "video_title": video_title,
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
        tasks[task_id].update({"status": "error", "error": str(e), "message": f"转录失败: {str(e)}"})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])


async def _transcribe_only_task(task_id: str, url: str):
    from backend.services.video_downloader import VideoDownloader
    from backend.services.audio_transcriber import AudioTranscriber

    try:
        video_downloader = VideoDownloader()
        audio_transcriber = AudioTranscriber()

        # 先尝试提取字幕（无需下载音频）
        tasks[task_id].update({"progress": 5, "message": "📄 正在检查视频字幕..."})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

        subtitle_text = None
        video_title = None
        try:
            subtitle_text, video_title = await video_downloader.extract_subtitles(url, TEMP_DIR)
        except Exception as e:
            logger.warning(f"字幕提取异常: {e}")

        if subtitle_text:
            # 有字幕，跳过音频下载和转录
            logger.info(f"✅ 使用视频字幕替代转录，跳过音频下载")
            tasks[task_id].update({"progress": 80, "message": "✅ 已从字幕中提取文本"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
            transcript = subtitle_text
        else:
            # 无字幕，下载音频并转录
            tasks[task_id].update({"progress": 10, "message": "🎬 无可用字幕，正在下载音频..."})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

            audio_path, video_title = await video_downloader.download_video_audio(url, TEMP_DIR)

            tasks[task_id].update({"progress": 40, "message": "🎤 正在转录音频..."})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

            transcript = await audio_transcriber.transcribe_audio(audio_path)

            try:
                Path(audio_path).unlink()
            except Exception:
                pass

        tasks[task_id].update({
            "status": "completed", "progress": 100, "message": "",
            "transcript": transcript, "video_title": video_title,
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
        tasks[task_id].update({"status": "error", "error": str(e), "message": f"转录失败: {str(e)}"})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])


@router.post("/video-qa-stream")
async def video_qa_stream(request: Request):
    try:
        data = await request.json()
        question = data.get("question", "").strip()
        transcript = data.get("transcript", "").strip()
        video_url = data.get("video_url", "")

        if not question:
            raise HTTPException(status_code=400, detail="问题不能为空")
        if not transcript:
            raise HTTPException(status_code=400, detail="转录文本不能为空")
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
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"视频问答失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")
