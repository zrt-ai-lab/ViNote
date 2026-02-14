"""
HTTP 中间件 — 速率限制
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    滑动窗口速率限制中间件
    默认：每个 IP 每分钟 100 次请求
    """

    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"

        excluded_paths = ["/", "/static", "/api/task-stream", "/api/download-stream"]
        if any(request.url.path.startswith(path) for path in excluded_paths):
            return await call_next(request)

        now = datetime.now()
        cutoff = now - timedelta(seconds=self.period)
        self.clients[client_ip] = [
            ts for ts in self.clients[client_ip] if ts > cutoff
        ]

        if len(self.clients[client_ip]) >= self.calls:
            logger.warning(
                f"速率限制触发: IP {client_ip} "
                f"({len(self.clients[client_ip])} 请求/{self.period}秒)"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"请求过于频繁，请{self.period}秒后重试",
                    "retry_after": self.period,
                },
            )

        self.clients[client_ip].append(now)

        # 定期清理长时间不活跃的客户端
        if len(self.clients) > 1000:
            inactive_clients = [
                ip
                for ip, timestamps in self.clients.items()
                if not timestamps
                or (now - timestamps[-1]).total_seconds() > 3600
            ]
            for ip in inactive_clients:
                del self.clients[ip]

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(
            self.calls - len(self.clients[client_ip])
        )
        response.headers["X-RateLimit-Reset"] = str(
            int((now + timedelta(seconds=self.period)).timestamp())
        )

        return response
