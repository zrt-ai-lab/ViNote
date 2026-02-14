"""
应用生命周期 — 启动/关闭事件
"""
import asyncio
import logging
from datetime import datetime, timedelta

from backend.core.state import (
    sse_connections,
    sse_connection_last_activity,
    tasks,
)

logger = logging.getLogger(__name__)


async def cleanup_stale_sse_connections():
    """定期清理断开或过期的 SSE 连接（只清理已完成/失败的任务连接）"""
    while True:
        try:
            await asyncio.sleep(300)

            current_time = datetime.now()
            stale_threshold = timedelta(hours=2)
            tasks_to_cleanup = []

            for task_id in list(sse_connections.keys()):
                task = tasks.get(task_id)

                if task:
                    task_status = task.get("status")

                    if task_status == "processing":
                        logger.debug(f"任务 {task_id} 正在处理中，跳过清理")
                        continue

                    if task_status in ["completed", "error", "cancelled"]:
                        last_activity = sse_connection_last_activity.get(task_id)
                        if last_activity and (current_time - last_activity) > stale_threshold:
                            tasks_to_cleanup.append(task_id)
                        elif not last_activity:
                            tasks_to_cleanup.append(task_id)
                else:
                    tasks_to_cleanup.append(task_id)

            for task_id in tasks_to_cleanup:
                if task_id in sse_connections:
                    logger.info(f"清理已完成任务的SSE连接: {task_id}")
                    del sse_connections[task_id]
                if task_id in sse_connection_last_activity:
                    del sse_connection_last_activity[task_id]

            if tasks_to_cleanup:
                logger.info(f"已清理 {len(tasks_to_cleanup)} 个已完成任务的SSE连接")

        except Exception as e:
            logger.error(f"清理SSE连接时出错: {e}")


async def check_openai_connection():
    """检查 OpenAI API 连接性"""
    from backend.core.ai_client import get_openai_client
    from backend.config.ai_config import get_openai_config

    config = get_openai_config()

    if not config.is_configured:
        logger.warning("OpenAI API 未配置，AI功能不可用")
        return

    try:
        client = get_openai_client()
        if client is None:
            logger.error("❌ OpenAI 客户端初始化失败")
            return

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=config.model,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
            timeout=10,
        )

        logger.info(f"OpenAI API 就绪 ({config.model})")

    except Exception as e:
        error_msg = str(e)
        if "API key" in error_msg or "Unauthorized" in error_msg:
            logger.error("OpenAI API Key 无效")
        elif "timeout" in error_msg.lower():
            logger.error("OpenAI API 连接超时")
        elif "Connection" in error_msg or "connect" in error_msg.lower():
            logger.error(f"OpenAI API 无法连接: {config.base_url}")
        else:
            logger.error(f"OpenAI API 异常: {error_msg}")


async def startup_event():
    asyncio.create_task(cleanup_stale_sse_connections())
    asyncio.create_task(check_openai_connection())
