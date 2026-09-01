import asyncio
import ipaddress
import logging
import socket
from urllib.parse import unquote, urljoin, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
ALLOWED_IMAGE_HOST_SUFFIXES = (
    "bilibili.com",
    "hdslb.com",
    "youtube.com",
    "ytimg.com",
    "ggpht.com",
)


async def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="无效的图片URL")
    hostname = parsed.hostname.rstrip(".").lower()
    if not any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in ALLOWED_IMAGE_HOST_SUFFIXES
    ):
        raise HTTPException(status_code=400, detail="不支持的图片来源")

    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise HTTPException(status_code=502, detail="图片地址无法解析") from exc

    if not addresses or any(
        not ipaddress.ip_address(item[4][0]).is_global for item in addresses
    ):
        raise HTTPException(status_code=400, detail="不允许访问本机或内网图片地址")


@router.get("/proxy-image")
async def proxy_image(url: str):
    try:
        image_url = unquote(url)

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

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                await _validate_public_url(image_url)
                async with client.stream("GET", image_url, headers=headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise HTTPException(status_code=502, detail="图片重定向地址缺失")
                        image_url = urljoin(image_url, location)
                        continue
                    if response.status_code != 200:
                        raise HTTPException(status_code=502, detail="获取图片失败")

                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .lower()
                    )
                    if not content_type.startswith("image/") or content_type == "image/svg+xml":
                        raise HTTPException(status_code=400, detail="目标地址未返回受支持的图片")
                    content_length = response.headers.get("content-length")
                    if content_length and content_length.isdigit():
                        if int(content_length) > MAX_IMAGE_BYTES:
                            raise HTTPException(status_code=413, detail="图片文件过大")

                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > MAX_IMAGE_BYTES:
                            raise HTTPException(status_code=413, detail="图片文件过大")
                        content.extend(chunk)
                    return Response(
                        content=bytes(content),
                        media_type=content_type,
                        headers={
                            "Cache-Control": "public, max-age=86400",
                            "X-Content-Type-Options": "nosniff",
                        },
                    )
            raise HTTPException(status_code=502, detail="图片重定向次数过多")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="图片请求超时")
    except httpx.HTTPError as e:
        logger.error(f"代理图片请求失败: {e}")
        raise HTTPException(status_code=502, detail="图片服务请求失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"代理图片失败: {e}")
        raise HTTPException(status_code=500, detail="图片代理处理失败")
