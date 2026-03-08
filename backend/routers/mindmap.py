import asyncio
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Form, Request
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

        downloader = VideoDownloader()
        
        # 先尝试提取字幕（无需下载音频）
        await progress(5, "📄 正在检查视频字幕...")
        subtitle_text = None
        video_title = None
        try:
            subtitle_text, video_title = await downloader.extract_subtitles(url, TEMP_DIR)
        except Exception as e:
            logger.warning(f"字幕提取异常: {e}")
        
        if subtitle_text:
            # 有字幕，跳过音频下载和转录
            logger.info(f"✅ 使用视频字幕替代转录，跳过音频下载")
            await progress(40, "✅ 已从字幕中提取文本，跳过音频下载")
            transcript = subtitle_text
        else:
            # 无字幕，下载音频并转录
            await progress(10, "🎬 无可用字幕，正在下载音频...")
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
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


async def _local_video_to_mindmap_task(task_id: str, file_path: str, language: str):
    from backend.utils.file_handler import extract_audio_from_file, cleanup_temp_audio

    try:
        async def progress(pct: int, msg: str):
            tasks[task_id].update({"progress": pct, "message": msg})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

        video_title = Path(file_path).stem

        await progress(5, "正在提取音频...")
        audio_path, needs_cleanup = await extract_audio_from_file(file_path, TEMP_DIR, task_id)

        try:
            await progress(30, "🎤 正在转录音频...")
            transcriber = AudioTranscriber()
            transcript = await transcriber.transcribe_audio(
                audio_path, video_title=video_title
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
        finally:
            cleanup_temp_audio(audio_path, needs_cleanup)

    except asyncio.CancelledError:
        logger.info(f"本地思维导图任务 {task_id} 被取消")
        if task_id in tasks:
            tasks[task_id].update({"status": "cancelled", "message": "已取消"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

    except Exception as e:
        logger.error(f"本地思维导图任务 {task_id} 失败: {e}")
        tasks[task_id].update({"status": "error", "error": str(e), "message": f"失败: {e}"})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

    finally:
        active_tasks.pop(task_id, None)
