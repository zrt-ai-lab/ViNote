import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Form
from pydantic import BaseModel

from backend.services.content_summarizer import ContentSummarizer
from backend.services.video_downloader import VideoDownloader
from backend.services.audio_transcriber import AudioTranscriber
from backend.core.state import (
    tasks, active_tasks,
    save_tasks, broadcast_task_update, TEMP_DIR,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class MindmapRequest(BaseModel):
    content: str
    language: str = "zh"


@router.post("/generate-mindmap")
async def generate_mindmap(req: MindmapRequest):
    """接收文本内容，直接调用大模型生成思维导图 Markdown 结构"""
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")

    if len(content) > 50000:
        raise HTTPException(status_code=400, detail="内容过长，请限制在 50000 字以内")

    try:
        summarizer = ContentSummarizer()
        if not summarizer.is_available():
            raise HTTPException(status_code=503, detail="AI 服务不可用")

        mindmap = await summarizer.generate_mindmap(content, req.language)
        if not mindmap:
            raise HTTPException(status_code=500, detail="生成思维导图失败")

        return {"mindmap": mindmap}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成思维导图失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.post("/video-to-mindmap")
async def video_to_mindmap(
    url: str = Form(...),
    language: str = Form(default="zh"),
):
    """视频 → 下载 → 转录 → 生成思维导图（跳过优化/摘要/翻译）"""
    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        "status": "processing",
        "progress": 0,
        "message": "开始处理...",
        "mindmap": None,
        "error": None,
        "url": url,
    }
    save_tasks(tasks)

    task = asyncio.create_task(_video_to_mindmap_task(task_id, url, language))
    active_tasks[task_id] = task

    return {"task_id": task_id}


async def _video_to_mindmap_task(task_id: str, url: str, language: str):
    try:
        async def progress(pct: int, msg: str):
            tasks[task_id].update({"progress": pct, "message": msg})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

        await progress(10, "🎬 正在下载视频音频...")
        downloader = VideoDownloader()
        audio_path, video_title = await downloader.download_video_audio(url, TEMP_DIR)

        await progress(30, "🎤 正在转录音频...")
        transcriber = AudioTranscriber()
        transcript = await transcriber.transcribe_audio(
            audio_path, video_title=video_title, video_url=url
        )

        await progress(80, "🧠 正在生成思维导图...")
        summarizer = ContentSummarizer()
        mindmap = await summarizer.generate_mindmap(transcript, language)

        tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "✨ 思维导图生成完成！",
            "mindmap": mindmap or "",
            "video_title": video_title,
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

    except asyncio.CancelledError:
        logger.info(f"思维导图任务 {task_id} 被取消")
        if task_id in tasks:
            tasks[task_id].update({"status": "cancelled", "message": "已取消"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

    except Exception as e:
        logger.error(f"思维导图任务 {task_id} 失败: {e}")
        tasks[task_id].update({"status": "error", "error": str(e), "message": f"失败: {e}"})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

    finally:
        active_tasks.pop(task_id, None)
