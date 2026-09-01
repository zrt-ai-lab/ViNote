"""统一的公开错误响应，内部异常只写日志。"""
from fastapi import HTTPException


def internal_error(message: str = "请求处理失败，请重试") -> HTTPException:
    return HTTPException(status_code=500, detail=message)


def task_failure(message: str) -> dict[str, str]:
    return {
        "status": "error",
        "error": message,
        "message": message,
    }
