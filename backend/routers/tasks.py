import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import StreamingResponse

from backend.core.state import (
    tasks, processing_urls, active_tasks, sse_connections,
    save_tasks, broadcast_task_update,
    TEMP_DIR,
)
from backend.services.note_generator import NoteGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


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
                task_id = str(uuid.uuid4())
                tasks[task_id] = {
                    "status": "processing",
                    "progress": 0,
                    "message": "开始处理本地文件...",
                    "script": None,
                    "summary": None,
                    "error": None,
                    "source": "local_path",
                    "file_path": url,
                }
                save_tasks(tasks)
                task = asyncio.create_task(_process_local_path_task(task_id, url, summary_language))
                active_tasks[task_id] = task
                return {"task_id": task_id, "message": "检测到本地文件，已自动切换本地处理模式"}

        if url in processing_urls:
            for tid, task in tasks.items():
                if task.get("url") == url:
                    return {"task_id": tid, "message": "该视频正在处理中，请等待..."}

        task_id = str(uuid.uuid4())
        processing_urls.add(url)

        tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "开始处理视频...",
            "script": None,
            "summary": None,
            "error": None,
            "url": url,
        }
        save_tasks(tasks)

        task = asyncio.create_task(_process_video_task(task_id, url, summary_language))
        active_tasks[task_id] = task

        return {"task_id": task_id, "message": "任务已创建，正在处理中..."}
    except Exception as e:
        logger.error(f"处理视频时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


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

        short_id = task_id.replace("-", "")[:6]
        safe_title = result["safe_title"]

        task_result = {
            "status": "completed",
            "progress": 100,
            "message": "🎉 笔记生成完成！",
            "video_title": result["video_title"],
            "script": result["optimized_transcript"],
            "summary": result["summary"],
            "script_path": str(result["files"]["transcript_path"]),
            "summary_path": str(result["files"]["summary_path"]),
            "short_id": short_id,
            "safe_title": safe_title,
            "detected_language": result["detected_language"],
            "summary_language": result["summary_language"],
            "raw_script": result["raw_transcript"],
            "raw_script_filename": result["files"]["raw_transcript_filename"],
            "mindmap": result.get("mindmap", ""),
            "mindmap_filename": result["files"].get("mindmap_filename"),
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
        tasks[task_id].update({"status": "error", "error": str(e), "message": f"处理失败: {str(e)}"})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])


@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tasks[task_id]


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
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Cache-Control",
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
async def get_completed_tasks():
    import re

    results_map: dict = {}

    for f in TEMP_DIR.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        name = f.stem
        # 文件名格式: {type}_{title}_{shortid}  例如 summary_蛋炒饭_cf8fe8
        match = re.match(r"^(summary|transcript|raw|mindmap)_(.+)_([a-f0-9]{6})$", name)
        if not match:
            continue
        file_type, title, short_id = match.group(1), match.group(2), match.group(3)

        if short_id not in results_map:
            results_map[short_id] = {
                "task_id": short_id,
                "video_title": title.replace("_", " "),
                "has_summary": False,
                "has_transcript": False,
                "files": {},
            }

        entry = results_map[short_id]
        entry["files"][file_type] = f.name
        if file_type == "summary":
            entry["has_summary"] = True
        if file_type in ("transcript", "raw"):
            entry["has_transcript"] = True

    for tid, t in tasks.items():
        if t.get("status") != "completed":
            continue
        sid = tid.replace("-", "")[:6]
        if sid in results_map:
            continue
        has_summary = bool(t.get("summary"))
        has_transcript = bool(t.get("transcript") or t.get("script") or t.get("raw_script"))
        if not (has_summary or has_transcript):
            continue
        results_map[sid] = {
            "task_id": sid,
            "video_title": t.get("video_title", "未命名"),
            "has_summary": has_summary,
            "has_transcript": has_transcript,
            "files": {},
            "_from_memory": True,
            "_full_task_id": tid,
        }

    results = []
    for entry in results_map.values():
        results.append({
            "task_id": entry["task_id"],
            "video_title": entry["video_title"],
            "type": "notes" if entry["has_summary"] else "qa",
            "has_summary": entry["has_summary"],
            "has_transcript": entry["has_transcript"],
        })

    return {"tasks": results}


@router.get("/tasks/{task_id}/content")
async def get_task_content(task_id: str, field: str = "summary"):
    import re

    # 优先从 temp 目录按 short_id 查找文件
    field_to_prefix = {
        "summary": "summary",
        "script": "transcript",
        "transcript": "raw",
    }
    prefix = field_to_prefix.get(field, field)

    for f in TEMP_DIR.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        if re.match(rf"^{re.escape(prefix)}_.+_{re.escape(task_id)}\.md$", f.name):
            content = f.read_text(encoding="utf-8")
            if content.strip():
                return {"content": content}

    for tid, t in tasks.items():
        if tid.replace("-", "")[:6] == task_id and t.get("status") == "completed":
            field_map = {
                "summary": t.get("summary", ""),
                "script": t.get("script", ""),
                "transcript": t.get("transcript") or t.get("raw_script", ""),
            }
            content = field_map.get(field, "")
            if content:
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
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


async def _process_local_path_task(task_id: str, file_path: str, summary_language: str):
    from backend.utils.file_handler import extract_audio_from_file, cleanup_temp_audio

    try:
        video_title = Path(file_path).stem

        async def progress_callback(progress: int, message: str):
            tasks[task_id].update({"status": "processing", "progress": progress, "message": message})
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

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

        short_id = task_id.replace("-", "")[:6]
        safe_title = result["safe_title"]

        task_result = {
            "status": "completed",
            "progress": 100,
            "message": "🎉 处理完成！",
            "video_title": result["video_title"],
            "script": result["optimized_transcript"],
            "summary": result["summary"],
            "script_path": str(result["files"]["transcript_path"]),
            "summary_path": str(result["files"]["summary_path"]),
            "short_id": short_id,
            "safe_title": safe_title,
            "detected_language": result["detected_language"],
            "summary_language": result["summary_language"],
            "raw_script": result["raw_transcript"],
            "raw_script_filename": result["files"]["raw_transcript_filename"],
            "mindmap": result.get("mindmap", ""),
            "mindmap_filename": result["files"].get("mindmap_filename"),
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
        tasks[task_id].update({"status": "error", "error": str(e), "message": f"处理失败: {str(e)}"})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
