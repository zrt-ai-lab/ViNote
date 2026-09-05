import json
import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from backend.core.state import (
    get_video_download_service, validate_download_filename, TEMP_DIR,
)
from backend.core.errors import internal_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/start-download")
async def start_download(data: dict):
    try:
        if not data:
            raise HTTPException(status_code=400, detail="请求数据不能为空")

        url = data.get("url")
        quality = data.get("quality", "best[height<=720]")
        if not url:
            raise HTTPException(status_code=400, detail="URL参数必需")
        if quality is None:
            quality = "best[height<=720]"

        logger.info(f"开始下载: url={url}, quality={quality}")
        download_id = await get_video_download_service().start_download(url, quality)
        return {"download_id": download_id, "message": "下载已开始"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"开始下载失败: {str(e)}")
        raise internal_error("下载任务启动失败")


@router.get("/download-stream/{download_id}")
async def download_stream(download_id: str):
    import asyncio

    async def event_generator():
        try:
            while True:
                status = get_video_download_service().get_download_status(download_id)
                if not status:
                    yield f"data: {json.dumps({'error': '下载任务不存在'})}\n\n"
                    break
                yield f"data: {json.dumps(status, ensure_ascii=False)}\n\n"
                if status.get("status") in ["completed", "error", "cancelled"]:
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info(f"下载流连接被取消: {download_id}")
        except Exception as e:
            logger.error(f"下载流异常: {e}")
            yield f"data: {json.dumps({'error': '下载状态读取失败'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/get-download/{download_id}")
async def get_download_file(download_id: str):
    try:
        file_path = get_video_download_service().get_file_path(download_id)
        if not file_path:
            raise HTTPException(status_code=404, detail="文件不存在")
        file_path = Path(file_path).resolve()
        if file_path.parent != (TEMP_DIR / "downloads").resolve():
            raise HTTPException(status_code=403, detail="访问被拒绝")
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")

        filename = Path(file_path).name
        encoded_filename = quote(filename, safe="")
        ascii_filename = filename.encode("ascii", "ignore").decode("ascii")
        ascii_filename = ascii_filename.replace("\r", "").replace("\n", "").replace('"', "")

        return FileResponse(
            file_path,
            filename=filename,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{ascii_filename or 'download'}\"; "
                    f"filename*=UTF-8''{encoded_filename}"
                )
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取下载文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文件失败")


@router.delete("/cancel-download/{download_id}")
async def cancel_download(download_id: str):
    try:
        success = await get_video_download_service().cancel_download(download_id)
        if success:
            return {"message": "下载已取消"}
        else:
            raise HTTPException(status_code=404, detail="下载任务不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消下载失败: {str(e)}")
        raise HTTPException(status_code=500, detail="取消下载失败")


@router.get("/download/{filename}")
async def download_file(filename: str):
    try:
        if not validate_download_filename(filename):
            logger.warning(f"非法文件下载尝试: {filename}")
            raise HTTPException(status_code=400, detail="文件名格式无效或不安全")

        file_path = (TEMP_DIR / filename).resolve()
        temp_dir_resolved = TEMP_DIR.resolve()

        if file_path.parent != temp_dir_resolved:
            logger.warning(f"路径遍历尝试: {filename} -> {file_path}")
            raise HTTPException(status_code=403, detail="访问被拒绝")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="无效的文件")

        logger.info(f"文件下载: {filename}")
        return FileResponse(file_path, filename=filename, media_type="text/markdown")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        raise HTTPException(status_code=500, detail="文件下载失败")
