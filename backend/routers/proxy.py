import logging
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/proxy-image")
async def proxy_image(url: str):
    try:
        image_url = unquote(url)

        if not image_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="无效的图片URL")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        if "bilibili.com" in image_url or "hdslb.com" in image_url:
            headers["Referer"] = "https://www.bilibili.com/"
        elif "youtube.com" in image_url or "ytimg.com" in image_url:
            headers["Referer"] = "https://www.youtube.com/"

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(image_url, headers=headers)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="获取图片失败")

            content_type = response.headers.get("content-type", "image/jpeg")
            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*"},
            )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="图片请求超时")
    except httpx.HTTPError as e:
        logger.error(f"代理图片请求失败: {e}")
        raise HTTPException(status_code=500, detail=f"代理请求失败: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"代理图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"代理失败: {str(e)}")
