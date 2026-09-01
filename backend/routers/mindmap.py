import asyncio
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Form, Request
from pydantic import BaseModel

from backend.services.content_summarizer import ContentSummarizer
from backend.services.media_ingestion import transcribe_local_media, transcribe_remote_media
from backend.core.state import (
    tasks, active_tasks,
    save_tasks, broadcast_task_update, TEMP_DIR,
)
from backend.core.errors import internal_error, task_failure

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
            raise internal_error("生成思维导图失败")

        return {"mindmap": mindmap}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成思维导图失败: {e}")
        raise internal_error("生成思维导图失败")


@router.post("/video-to-mindmap")
async def video_to_mindmap(
    url: str = Form(...),
    language: str = Form(default="zh"),
):
    """视频 → 下载 → 转录 → 生成思维导图（跳过优化/摘要/翻译）"""
    # 防御：如果收到本地文件路径，自动走本地处理流程
    if os.path.exists(url) and os.path.isfile(url):
        from backend.utils.file_handler import MEDIA_EXTENSIONS
        file_ext = Path(url).suffix.lower()
        if file_ext in MEDIA_EXTENSIONS:
            task_id = str(uuid.uuid4())
            tasks[task_id] = {
                "status": "processing",
                "progress": 0,
                "message": "开始处理本地文件...",
                "mindmap": None,
                "error": None,
                "source": "local_path",
                "file_path": url,
            }
            save_tasks(tasks)
            task = asyncio.create_task(_local_video_to_mindmap_task(task_id, url, language))
            active_tasks[task_id] = task
            return {"task_id": task_id}

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

        async def on_stage(stage: str):
            mapped = {
                "checking_subtitles": (5, "📄 正在检查视频字幕..."),
                "subtitle_ready": (40, "✅ 已从字幕中提取文本，跳过音频下载"),
                "downloading_audio": (10, "🎬 无可用字幕，正在下载音频..."),
                "transcribing_audio": (30, "🎤 正在转录音频..."),
            }.get(stage)
            if mapped:
                await progress(*mapped)

        result = await transcribe_remote_media(url, TEMP_DIR, on_stage, include_metadata=True)

        await progress(80, "🧠 正在生成思维导图...")
        summarizer = ContentSummarizer()
        mindmap = await summarizer.generate_mindmap(result.transcript, language)

        tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "✨ 思维导图生成完成！",
            "mindmap": mindmap or "",
            "video_title": result.video_title,
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
        tasks[task_id].update(task_failure("视频思维导图生成失败，请重试"))
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

    finally:
        active_tasks.pop(task_id, None)


@router.post("/local-video-to-mindmap")
async def local_video_to_mindmap(request: Request):
    """本地视频文件 → 提取音频 → 转录 → 生成思维导图"""
    try:
        data = await request.json()
        file_path = data.get("file_path", "").strip()
        language = data.get("language", "zh")

        if not file_path:
            raise HTTPException(status_code=400, detail="文件路径不能为空")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
        if not os.path.isfile(file_path):
            raise HTTPException(status_code=400, detail="路径不是有效的文件")

        from backend.utils.file_handler import MEDIA_EXTENSIONS
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in MEDIA_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的文件格式: {file_ext}")

        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "开始处理本地文件...",
            "mindmap": None,
            "error": None,
            "source": "local_path",
            "file_path": file_path,
        }
        save_tasks(tasks)

        task = asyncio.create_task(_local_video_to_mindmap_task(task_id, file_path, language))
        active_tasks[task_id] = task

        return {"task_id": task_id, "message": "本地文件思维导图任务已创建"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理本地路径时出错: {str(e)}")
        raise internal_error("本地思维导图任务创建失败")


async def _local_video_to_mindmap_task(task_id: str, file_path: str, language: str):
    try:
        async def progress(pct: int, msg: str):
            tasks[task_id].update({"progress": pct, "message": msg})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

        async def on_stage(stage: str):
            mapped = {
                "checking_subtitles": (3, "📄 正在检查内嵌字幕..."),
                "subtitle_ready": (40, "✅ 发现内嵌字幕，跳过音频转录"),
                "extracting_audio": (5, "正在提取音频..."),
                "transcribing_audio": (30, "🎤 正在转录音频..."),
            }.get(stage)
            if mapped:
                await progress(*mapped)

        result = await transcribe_local_media(
            file_path, TEMP_DIR, task_id, on_stage, include_metadata=True
        )

        await progress(80, "🧠 正在生成思维导图...")
        summarizer = ContentSummarizer()
        mindmap = await summarizer.generate_mindmap(result.transcript, language)

        tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "✨ 思维导图生成完成！",
            "mindmap": mindmap or "",
            "video_title": result.video_title,
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

    except asyncio.CancelledError:
        logger.info(f"本地思维导图任务 {task_id} 被取消")
        if task_id in tasks:
            tasks[task_id].update({"status": "cancelled", "message": "已取消"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

    except Exception as e:
        logger.error(f"本地思维导图任务 {task_id} 失败: {e}")
        tasks[task_id].update(task_failure("本地思维导图生成失败，请重试"))
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

    finally:
        active_tasks.pop(task_id, None)
