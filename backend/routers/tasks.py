import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Form, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.core.state import (
    tasks, processing_urls, active_tasks, active_batches, sse_connections,
    save_tasks, broadcast_task_update, persist_completed_task,
    TEMP_DIR,
)
from backend.core.errors import internal_error, task_failure
from backend.services.note_generator import NoteGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _create_single_task(url: str, summary_language: str, batch_id: Optional[str] = None) -> str:
    """Create a single task entry in tasks dict and start processing. Returns task_id."""
    is_local = os.path.exists(url) and os.path.isfile(url)

    if is_local:
        from backend.utils.file_handler import MEDIA_EXTENSIONS
        file_ext = Path(url).suffix.lower()
        if file_ext not in MEDIA_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {file_ext}")

    task_id = str(uuid.uuid4())
    task_data = {
        "status": "processing",
        "progress": 0,
        "message": "开始处理本地文件..." if is_local else "开始处理视频...",
        "script": None,
        "summary": None,
        "error": None,
    }

    if is_local:
        task_data.update({"source": "local_path", "file_path": url})
    else:
        task_data["url"] = url
        processing_urls.add(url)

    if batch_id:
        task_data["batch_id"] = batch_id

    tasks[task_id] = task_data
    save_tasks(tasks)

    if is_local:
        coro = _process_local_path_task(task_id, url, summary_language)
    else:
        coro = _process_video_task(task_id, url, summary_language)

    task = asyncio.create_task(coro)
    active_tasks[task_id] = task
    return task_id


@router.post("/process-video")
async def process_video(
    url: str = Form(...),
    summary_language: str = Form(default="zh"),
):
    try:
        # 防御：如果收到本地文件路径，自动走本地处理流程
        if os.path.exists(url) and os.path.isfile(url):
            from backend.utils.file_handler import MEDIA_EXTENSIONS
            file_ext = Path(url).suffix.lower()
            if file_ext in MEDIA_EXTENSIONS:
                task_id = _create_single_task(url, summary_language)
                return {"task_id": task_id, "message": "检测到本地文件，已自动切换本地处理模式"}

        if url in processing_urls:
            for tid, task in tasks.items():
                if task.get("url") == url:
                    return {"task_id": tid, "message": "该视频正在处理中，请等待..."}

        task_id = _create_single_task(url, summary_language)
        return {"task_id": task_id, "message": "任务已创建，正在处理中..."}
    except Exception as e:
        logger.error(f"处理视频时出错: {str(e)}")
        raise internal_error("视频处理任务创建失败")


async def _process_video_task(task_id: str, url: str, summary_language: str):
    try:
        note_gen = NoteGenerator()

        async def progress_callback(progress: int, message: str):
            tasks[task_id].update({"status": "processing", "progress": progress, "message": message})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

        def cancel_check() -> bool:
            return task_id not in active_tasks or (
                task_id in active_tasks and active_tasks[task_id].cancelled()
            )

        result = await note_gen.generate_note(
            video_url=url,
            temp_dir=TEMP_DIR,
            summary_language=summary_language,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

        short_id = result["short_id"]
        safe_title = result["safe_title"]

        task_result = {
            "status": "completed",
            "progress": 100,
            "message": (
                "处理完成（部分 AI 能力已降级）"
                if result.get("warnings") else "🎉 笔记生成完成！"
            ),
            "video_title": result["video_title"],
            "script": result["optimized_transcript"],
            "summary": result["summary"],
            "script_path": str(result["files"]["transcript_path"]),
            "summary_path": str(result["files"]["summary_path"]),
            "transcript_filename": result["files"]["transcript_filename"],
            "summary_filename": result["files"]["summary_filename"],
            "short_id": short_id,
            "safe_title": safe_title,
            "detected_language": result["detected_language"],
            "summary_language": result["summary_language"],
            "raw_script": result["raw_transcript"],
            "raw_script_filename": result["files"]["raw_transcript_filename"],
            "mindmap": result.get("mindmap", ""),
            "mindmap_filename": result["files"].get("mindmap_filename"),
            "warnings": result.get("warnings", []),
        }

        if "translation" in result:
            task_result.update({
                "translation": result["translation"],
                "translation_path": str(result["files"]["translation_path"]),
                "translation_filename": result["files"]["translation_filename"],
            })

        tasks[task_id].update(task_result)
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

        processing_urls.discard(url)
        active_tasks.pop(task_id, None)

        # 先持久化到 SQLite（auto_tag 需要 note 已存在）
        await persist_completed_task(task_id, tasks.get(task_id, task_result))

        # 自动打标签（需要 SQLite 中已有 note 记录）
        try:
            from backend.services.tag_service import auto_tag_from_summary
            summary_text = result.get("summary", "")
            if summary_text:
                await auto_tag_from_summary(short_id, summary_text, result.get("video_title", ""))
        except Exception as e:
            logger.warning(f"自动标签失败: {e}")

    except asyncio.CancelledError:
        logger.info(f"任务 {task_id} 被取消")
        processing_urls.discard(url)
        active_tasks.pop(task_id, None)
        if task_id in tasks:
            tasks[task_id].update({"status": "cancelled", "error": "用户取消任务", "message": "❌ 任务已取消"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

    except Exception as e:
        logger.error(f"任务 {task_id} 处理失败: {str(e)}")
        processing_urls.discard(url)
        active_tasks.pop(task_id, None)
        tasks[task_id].update(task_failure("视频处理失败，请重试"))
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])


@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    # 1. 先查内存（处理中/刚完成的任务）
    if task_id in tasks:
        return tasks[task_id]

    # 2. 回退到 SQLite（已持久化的任务）
    from backend.services.note_repository import get_note, get_note_by_task_id
    # 先尝试直接作为 short_id 查
    note = await get_note(task_id)
    # 再尝试用 task_id（完整UUID）查
    if not note:
        note = await get_note_by_task_id(task_id)
    if note:
        short_id = note["short_id"]
        result = {
            "status": "completed",
            "progress": 100,
            "message": (
                "处理完成（部分 AI 能力已降级）"
                if note.get("warnings") else "已完成"
            ),
            "video_title": note.get("title", ""),
            "short_id": note["short_id"],
            "safe_title": note.get("safe_title", ""),
            "warnings": note.get("warnings", []),
        }

        # 索引中的产物名是唯一契约；不按标题猜测，更不能读到同名笔记。
        for field, stored, filename_key in (
            ("summary", "summary_file", "summary_filename"),
            ("script", "transcript_file", "transcript_filename"),
            ("raw_script", "raw_transcript_file", "raw_script_filename"),
            ("translation", "translation_file", "translation_filename"),
            ("mindmap", "mindmap_file", "mindmap_filename"),
        ):
            filename = note.get(stored)
            if not filename or Path(filename).name != filename:
                continue
            path = (TEMP_DIR / filename).resolve()
            if path.parent != TEMP_DIR.resolve() or not path.is_file():
                continue
            result[field] = await asyncio.to_thread(path.read_text, encoding="utf-8")
            result[filename_key] = filename
        return result

    raise HTTPException(status_code=404, detail="任务不存在")


@router.get("/task-stream/{task_id}")
async def task_stream(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        queue = asyncio.Queue()
        if task_id not in sse_connections:
            sse_connections[task_id] = []
        sse_connections[task_id].append(queue)

        try:
            current_task = tasks.get(task_id, {})
            yield f"data: {json.dumps(current_task, ensure_ascii=False)}\n\n"

            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {data}\n\n"
                    task_data = json.loads(data)
                    if task_data.get("status") in ["completed", "error"]:
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
        except asyncio.CancelledError:
            logger.info(f"SSE连接被取消: {task_id}")
        except Exception as e:
            logger.error(f"SSE流异常: {e}")
        finally:
            if task_id in sse_connections and queue in sse_connections[task_id]:
                sse_connections[task_id].remove(queue)
                if not sse_connections[task_id]:
                    del sse_connections[task_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task_id in active_tasks:
        task = active_tasks[task_id]
        if not task.done():
            task.cancel()
            logger.info(f"任务 {task_id} 已被取消")
        del active_tasks[task_id]

    task_url = tasks[task_id].get("url")
    if task_url:
        processing_urls.discard(task_url)

    del tasks[task_id]
    return {"message": "任务已取消并删除"}


@router.get("/tasks/active")
async def get_active_tasks():
    return {
        "active_tasks": len(active_tasks),
        "processing_urls": len(processing_urls),
        "task_ids": list(active_tasks.keys()),
    }


@router.get("/tasks/completed")
async def get_completed_tasks(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = Query(default=None, max_length=500),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    from backend.services.note_repository import list_notes
    return await list_notes(
        category=category,
        tag=tag,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/tasks/{task_id}/content")
async def get_task_content(task_id: str, field: str = "summary"):
    import re

    if field not in {"summary", "script", "transcript", "raw"}:
        raise HTTPException(status_code=400, detail="不支持的内容类型")
    field_to_prefix = {
        "summary": "summary",
        "script": "transcript",
        "transcript": "transcript",
        "raw": "raw",
    }
    prefix = field_to_prefix.get(field, field)

    # 1. 从 temp 目录按 short_id 查找文件
    for f in TEMP_DIR.iterdir():
        if not f.is_file() or f.suffix != ".md" or f.resolve().parent != TEMP_DIR.resolve():
            continue
        if re.match(rf"^{re.escape(prefix)}_.+_{re.escape(task_id)}\.md$", f.name):
            content = await asyncio.to_thread(f.read_text, encoding="utf-8")
            if content.strip():
                return {"content": content}

    # 2. 从内存中查找
    for tid, t in tasks.items():
        short = t.get("short_id") or tid.replace("-", "")[:6]
        if short == task_id and t.get("status") == "completed":
            field_map = {
                "summary": t.get("summary", ""),
                "script": t.get("script", ""),
                "transcript": t.get("script") or t.get("transcript") or t.get("raw_script", ""),
            }
            content = field_map.get(field, "")
            if content:
                return {"content": content}

    # 3. 从 SQLite 查找存储的文件名（兼容 short_id 不匹配的历史数据）
    from backend.services.note_repository import get_note, get_note_by_task_id
    note = await get_note(task_id)
    if not note:
        note = await get_note_by_task_id(task_id)
    if note:
        field_to_db_col = {
            "summary": "summary_file",
            "script": "transcript_file",
            "transcript": "transcript_file",
            "raw": "raw_transcript_file",
        }
        db_filename = None
        col = field_to_db_col.get(field)
        if col:
            db_filename = note.get(col)
        if db_filename and Path(db_filename).name == db_filename:
            fpath = (TEMP_DIR / db_filename).resolve()
            if fpath.parent == TEMP_DIR.resolve() and fpath.is_file():
                content = await asyncio.to_thread(fpath.read_text, encoding="utf-8")
                if content.strip():
                    return {"content": content}

        # 用 note 中的 short_id 再扫一遍文件系统
        note_short_id = note.get("short_id", "")
        if note_short_id and note_short_id != task_id:
            for f in TEMP_DIR.iterdir():
                if not f.is_file() or f.suffix != ".md" or f.resolve().parent != TEMP_DIR.resolve():
                    continue
                if re.match(rf"^{re.escape(prefix)}_.+_{re.escape(note_short_id)}\.md$", f.name):
                    content = await asyncio.to_thread(f.read_text, encoding="utf-8")
                    if content.strip():
                        return {"content": content}

    raise HTTPException(status_code=404, detail=f"未找到 {field} 内容")


@router.post("/process-local-path")
async def process_local_path(request: Request):
    try:
        data = await request.json()
        file_path = data.get("file_path", "").strip()
        summary_language = data.get("language", "zh")

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
            "script": None,
            "summary": None,
            "error": None,
            "source": "local_path",
            "file_path": file_path,
        }
        save_tasks(tasks)

        task = asyncio.create_task(_process_local_path_task(task_id, file_path, summary_language))
        active_tasks[task_id] = task

        return {"task_id": task_id, "message": "本地文件处理任务已创建"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理本地路径时出错: {str(e)}")
        raise internal_error("本地文件处理任务创建失败")


async def _process_local_path_task(task_id: str, file_path: str, summary_language: str):
    from backend.utils.file_handler import extract_audio_from_file, cleanup_temp_audio, extract_embedded_subtitles

    try:
        video_title = Path(file_path).stem

        async def progress_callback(progress: int, message: str):
            tasks[task_id].update({"status": "processing", "progress": progress, "message": message})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

        # 先尝试提取内嵌字幕
        await progress_callback(3, "📄 正在检查内嵌字幕...")
        subtitle_text = None
        try:
            subtitle_text = await extract_embedded_subtitles(file_path)
        except Exception as e:
            logger.warning(f"内嵌字幕提取异常: {e}")

        if subtitle_text:
            # 有字幕：跳过音频提取，直接用字幕
            logger.info(f"✅ 本地视频发现内嵌字幕，跳过音频提取和ASR")
            await progress_callback(10, "✅ 发现内嵌字幕，跳过音频转录")

            note_gen = NoteGenerator()

            def cancel_check() -> bool:
                return task_id not in active_tasks or (
                    task_id in active_tasks and active_tasks[task_id].cancelled()
                )

            result = await note_gen.generate_note(
                video_url=f"file://{file_path}",
                temp_dir=TEMP_DIR,
                summary_language=summary_language,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
                subtitle_text_override=subtitle_text,
                video_title_override=video_title,
            )
        else:
            # 无字幕：提取音频走 ASR
            await progress_callback(5, "正在提取音频...")
            audio_path, needs_cleanup = await extract_audio_from_file(file_path, TEMP_DIR, task_id)

            try:
                note_gen = NoteGenerator()

                def cancel_check() -> bool:
                    return task_id not in active_tasks or (
                        task_id in active_tasks and active_tasks[task_id].cancelled()
                    )

                result = await note_gen.generate_note(
                    video_url=f"file://{file_path}",
                    temp_dir=TEMP_DIR,
                    summary_language=summary_language,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                    audio_path_override=audio_path,
                    video_title_override=video_title,
                )
            finally:
                cleanup_temp_audio(audio_path, needs_cleanup)

        short_id = result["short_id"]
        safe_title = result["safe_title"]

        task_result = {
            "status": "completed",
            "progress": 100,
            "message": (
                "处理完成（部分 AI 能力已降级）"
                if result.get("warnings") else "🎉 处理完成！"
            ),
            "video_title": result["video_title"],
            "script": result["optimized_transcript"],
            "summary": result["summary"],
            "script_path": str(result["files"]["transcript_path"]),
            "summary_path": str(result["files"]["summary_path"]),
            "transcript_filename": result["files"]["transcript_filename"],
            "summary_filename": result["files"]["summary_filename"],
            "short_id": short_id,
            "safe_title": safe_title,
            "detected_language": result["detected_language"],
            "summary_language": result["summary_language"],
            "raw_script": result["raw_transcript"],
            "raw_script_filename": result["files"]["raw_transcript_filename"],
            "mindmap": result.get("mindmap", ""),
            "mindmap_filename": result["files"].get("mindmap_filename"),
            "warnings": result.get("warnings", []),
        }

        if "translation" in result:
            task_result.update({
                "translation": result["translation"],
                "translation_path": str(result["files"]["translation_path"]),
                "translation_filename": result["files"]["translation_filename"],
            })

        tasks[task_id].update(task_result)
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        active_tasks.pop(task_id, None)

        # 先持久化到 SQLite（auto_tag 需要 note 已存在）
        await persist_completed_task(task_id, tasks.get(task_id, task_result))

        # 自动打标签（需要 SQLite 中已有 note 记录）
        try:
            from backend.services.tag_service import auto_tag_from_summary
            summary_text = result.get("summary", "")
            if summary_text:
                await auto_tag_from_summary(short_id, summary_text, result.get("video_title", ""))
        except Exception as e:
            logger.warning(f"自动标签失败: {e}")

    except asyncio.CancelledError:
        logger.info(f"本地文件处理任务 {task_id} 被取消")
        active_tasks.pop(task_id, None)
        if task_id in tasks:
            tasks[task_id].update({"status": "cancelled", "error": "用户取消任务", "message": "❌ 任务已取消"})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
    except Exception as e:
        logger.error(f"本地文件处理任务 {task_id} 失败: {str(e)}")
        active_tasks.pop(task_id, None)
        tasks[task_id].update(task_failure("本地文件处理失败，请重试"))
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])


# ── Batch processing ──────────────────────────────────────────────

class BatchRequest(BaseModel):
    urls: list[str]
    summary_language: str = "zh"


@router.post("/batch-process")
async def batch_process(req: BatchRequest):
    urls = list(dict.fromkeys(u.strip() for u in req.urls if u.strip()))
    if not urls:
        raise HTTPException(status_code=400, detail="URL列表不能为空")
    if len(urls) > 20:
        raise HTTPException(status_code=400, detail="单次最多支持20个URL")

    batch_id = uuid.uuid4().hex
    from backend.config.settings import get_settings
    concurrency = max(1, min(get_settings().BATCH_CONCURRENCY, len(urls)))
    semaphore = asyncio.Semaphore(concurrency)

    # Collect task info before creating tasks (to avoid auto-start race)
    task_entries: list[tuple[str, str]] = []  # (url, summary_language)
    for url in urls:
        task_entries.append((url, req.summary_language))

    # Create task entries in tasks dict (queued, not started yet)
    task_ids: list[str] = []
    for url, lang in task_entries:
        is_local = os.path.exists(url) and os.path.isfile(url)
        task_id = str(uuid.uuid4())
        task_data = {
            "status": "queued",
            "progress": 0,
            "message": "排队等待中...",
            "script": None,
            "summary": None,
            "error": None,
            "batch_id": batch_id,
        }
        if is_local:
            task_data.update({"source": "local_path", "file_path": url})
        else:
            task_data["url"] = url
        tasks[task_id] = task_data
        task_ids.append(task_id)

    save_tasks(tasks)
    coordinator = asyncio.create_task(
        _batch_process(batch_id, task_ids, task_entries, semaphore)
    )
    active_batches[batch_id] = coordinator

    return {"batch_id": batch_id, "task_ids": task_ids, "total": len(task_ids)}


async def _batch_process(
    batch_id: str,
    task_ids: list[str],
    task_entries: list[tuple[str, str]],
    semaphore: asyncio.Semaphore,
):
    """Run batch sub-tasks with concurrency control via semaphore."""

    async def _run_one(tid: str, url: str, lang: str):
        try:
            async with semaphore:
                if tid not in tasks or tasks[tid].get("status") == "cancelled":
                    return
                tasks[tid].update({"status": "processing", "message": "开始处理..."})
                save_tasks(tasks)
                await broadcast_task_update(tid, tasks[tid])

                is_local = os.path.exists(url) and os.path.isfile(url)
                if is_local:
                    coro = _process_local_path_task(tid, url, lang)
                else:
                    if url in processing_urls:
                        tasks[tid].update({
                            "status": "error",
                            "error": "视频正在处理中",
                            "message": "跳过重复任务",
                        })
                        save_tasks(tasks)
                        await broadcast_task_update(tid, tasks[tid])
                        return
                    processing_urls.add(url)
                    coro = _process_video_task(tid, url, lang)
                inner = asyncio.create_task(coro)
                active_tasks[tid] = inner
                try:
                    await inner
                finally:
                    active_tasks.pop(tid, None)
        except asyncio.CancelledError:
            if tid in tasks and tasks[tid].get("status") in {"queued", "processing"}:
                tasks[tid].update({
                    "status": "cancelled", "error": "用户取消批次", "message": "批次已取消",
                })
                save_tasks(tasks)
                await broadcast_task_update(tid, tasks[tid])
            raise
        except Exception as e:
            logger.error(f"批次 {batch_id} 子任务 {tid} 异常: {e}")

    try:
        await asyncio.gather(
            *[_run_one(tid, url, lang) for tid, (url, lang) in zip(task_ids, task_entries)],
            return_exceptions=True,
        )
        logger.info(f"批次 {batch_id} 全部处理完成")
    finally:
        active_batches.pop(batch_id, None)


@router.delete("/batch/{batch_id}")
async def cancel_batch(batch_id: str):
    matching = [(tid, task) for tid, task in tasks.items() if task.get("batch_id") == batch_id]
    coordinator = active_batches.get(batch_id)
    if not matching and not coordinator:
        raise HTTPException(status_code=404, detail="批次不存在")

    if coordinator and not coordinator.done():
        coordinator.cancel()
        try:
            await coordinator
        except asyncio.CancelledError:
            pass

    cancelled = 0
    for tid, task_data in matching:
        if task_data.get("status") not in {"queued", "processing"}:
            continue
        running = active_tasks.get(tid)
        if running and not running.done():
            running.cancel()
        task_data.update({"status": "cancelled", "error": "用户取消批次", "message": "批次已取消"})
        await broadcast_task_update(tid, task_data)
        cancelled += 1
    if cancelled:
        save_tasks(tasks)
    cancelled_total = sum(
        1 for _, task in matching if task.get("status") == "cancelled"
    )
    return {"message": "批次已取消", "cancelled": cancelled_total}


@router.get("/batch-status/{batch_id}")
async def get_batch_status(batch_id: str):
    batch_tasks = []

    # 1. 从内存查（处理中/排队的任务）
    for tid, t in tasks.items():
        if t.get("batch_id") != batch_id:
            continue
        batch_tasks.append({
            "task_id": tid,
            "short_id": t.get("short_id") or tid.replace("-", "")[:6],
            "video_title": t.get("video_title") or t.get("url") or t.get("file_path") or "未知",
            "status": t.get("status", "processing"),
            "progress": t.get("progress", 0),
            "message": t.get("message", ""),
            "error": t.get("error"),
        })

    # 2. 从 SQLite 查（已完成并持久化的任务）
    from backend.services.note_repository import list_notes_by_batch
    in_memory_short_ids = {t["short_id"] for t in batch_tasks}
    try:
        db_notes = await list_notes_by_batch(batch_id)
        for note in db_notes:
            if note["task_id"] in in_memory_short_ids:
                continue
            batch_tasks.append({
                "task_id": note["task_id"],
                "short_id": note["task_id"],
                "video_title": note.get("video_title", "未知"),
                "status": "completed",
                "progress": 100,
                "message": "已完成",
                "error": None,
            })
    except Exception as e:
        logger.warning(f"查询 SQLite 批次任务失败: {e}")

    if not batch_tasks:
        raise HTTPException(status_code=404, detail="批次不存在")

    total = len(batch_tasks)
    completed = sum(1 for t in batch_tasks if t["status"] == "completed")
    failed = sum(1 for t in batch_tasks if t["status"] == "error")
    processing = sum(1 for t in batch_tasks if t["status"] in {"queued", "processing"})
    cancelled = sum(1 for t in batch_tasks if t["status"] == "cancelled")

    return {
        "batch_id": batch_id,
        "total": total,
        "completed": completed,
        "failed": failed,
        "cancelled": cancelled,
        "processing": processing,
        "tasks": batch_tasks,
    }


class ScanDirRequest(BaseModel):
    directory: str
    recursive: bool = False


@router.post("/scan-directory")
async def scan_directory(req: ScanDirRequest):
    """扫描本地目录，返回所有支持的媒体文件列表"""
    from backend.utils.file_handler import MEDIA_EXTENSIONS

    dir_path = Path(req.directory.strip())
    if not dir_path.exists():
        raise HTTPException(status_code=404, detail=f"目录不存在: {req.directory}")
    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail="路径不是有效的目录")

    files = []
    pattern = dir_path.rglob("*") if req.recursive else dir_path.iterdir()
    for f in pattern:
        if not f.is_file():
            continue
        if f.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        try:
            size = f.stat().st_size
            files.append({
                "path": str(f),
                "name": f.name,
                "size": size,
                "size_display": f"{size / (1024 * 1024):.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB",
            })
        except Exception:
            continue

    files.sort(key=lambda x: x["name"])
    return {"directory": str(dir_path), "files": files, "total": len(files)}
