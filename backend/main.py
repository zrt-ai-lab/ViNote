from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
import tempfile
import asyncio
import logging
from pathlib import Path
from typing import Optional
import aiofiles
import uuid
import json
import re
from dotenv import load_dotenv

# 获取项目根目录并加载环境变量
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# 新的服务层导入
from backend.services.note_generator import NoteGenerator
from backend.services.video_preview_service import VideoPreviewService
from backend.services.video_download_service import VideoDownloadService
from backend.services.video_qa_service import VideoQAService
from backend.services.video_search_agent import VideoSearchAgent

# 配置日志 - 优化输出格式
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s | %(message)s',  # 简洁格式：级别 | 消息
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# 设置第三方库日志级别为WARNING，减少噪音
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('faster_whisper').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)

app = FastAPI(title="AI视频转录器", version="1.0.0")


# CORS中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 简单的速率限制实现
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    简单的速率限制中间件
    - 每个IP地址的请求限制
    - 使用滑动窗口算法
    """
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls  # 允许的请求数
        self.period = period  # 时间窗口（秒）
        self.clients = defaultdict(list)  # IP -> [timestamp, ...]
        
    async def dispatch(self, request: Request, call_next):
        # 获取客户端IP
        client_ip = request.client.host if request.client else "unknown"
        
        # 排除某些端点的速率限制
        excluded_paths = ["/", "/static", "/api/task-stream", "/api/download-stream"]
        if any(request.url.path.startswith(path) for path in excluded_paths):
            return await call_next(request)
        
        # 清理过期的请求记录
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.period)
        self.clients[client_ip] = [ts for ts in self.clients[client_ip] if ts > cutoff]
        
        # 检查是否超过限制
        if len(self.clients[client_ip]) >= self.calls:
            logger.warning(f"速率限制触发: IP {client_ip} ({len(self.clients[client_ip])} 请求/{self.period}秒)")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"请求过于频繁，请{self.period}秒后重试",
                    "retry_after": self.period
                }
            )
        
        # 记录本次请求
        self.clients[client_ip].append(now)
        
        # 定期清理长时间不活跃的客户端记录（避免内存泄漏）
        if len(self.clients) > 1000:
            inactive_clients = [
                ip for ip, timestamps in self.clients.items()
                if not timestamps or (now - timestamps[-1]).total_seconds() > 3600
            ]
            for ip in inactive_clients:
                del self.clients[ip]
        
        response = await call_next(request)
        
        # 添加速率限制响应头
        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(self.calls - len(self.clients[client_ip]))
        response.headers["X-RateLimit-Reset"] = str(int((now + timedelta(seconds=self.period)).timestamp()))
        
        return response

# 添加速率限制中间件
# 默认：每分钟100个请求
app.add_middleware(RateLimitMiddleware, calls=100, period=60)

# 定期清理过期SSE连接的后台任务
async def cleanup_stale_sse_connections():
    """定期清理断开或过期的SSE连接 - 只清理已完成/失败的任务连接"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟清理一次
            
            from datetime import datetime, timedelta
            current_time = datetime.now()
            stale_threshold = timedelta(hours=2)  # 2小时未活动视为过期（大幅延长）
            
            tasks_to_cleanup = []
            
            for task_id in list(sse_connections.keys()):
                # 首先检查任务状态
                task = tasks.get(task_id)
                
                # 只清理已完成或失败的任务连接
                if task:
                    task_status = task.get("status")
                    
                    # 如果任务还在处理中，绝不清理连接
                    if task_status == "processing":
                        logger.debug(f"任务 {task_id} 正在处理中，跳过清理")
                        continue
                    
                    # 只有当任务已完成、失败或取消，且连接超时时才清理
                    if task_status in ["completed", "error", "cancelled"]:
                        last_activity = sse_connection_last_activity.get(task_id)
                        
                        if last_activity and (current_time - last_activity) > stale_threshold:
                            tasks_to_cleanup.append(task_id)
                        elif not last_activity:
                            # 没有活动记录但任务已结束的也可以清理
                            tasks_to_cleanup.append(task_id)
                else:
                    # 任务记录都不存在了，可以清理连接
                    tasks_to_cleanup.append(task_id)
            
            # 清理过期连接
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

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化任务"""
    # 启动SSE连接清理任务
    asyncio.create_task(cleanup_stale_sse_connections())
    logger.info("SSE连接清理任务已启动")
    
    # 检查OpenAI连接性
    await check_openai_connection()

async def check_openai_connection():
    """检查OpenAI API连接性"""
    from backend.core.ai_client import get_openai_client
    from backend.config.ai_config import get_openai_config
    
    config = get_openai_config()
    
    # 检查配置
    if not config.is_configured:
        logger.warning("⚠️  OpenAI API 未配置")
        logger.warning("   请在 .env 文件中设置 OPENAI_API_KEY")
        logger.warning("   AI功能（文本优化、摘要生成、翻译等）将不可用")
        return
    
    logger.info("正在检查 OpenAI API 连接...")
    logger.info(f"   Base URL: {config.base_url}")
    logger.info(f"   Model: {config.model}")
    
    try:
        client = get_openai_client()
        if client is None:
            logger.error("❌ OpenAI 客户端初始化失败")
            return
        
        # 测试连接 - 发送一个简单的请求
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=config.model,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
            timeout=10
        )
        
        logger.info("✅ OpenAI API 连接成功！")
        logger.info(f"   响应模型: {response.model}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error("❌ OpenAI API 连接失败")
        
        # 详细的错误提示
        if "API key" in error_msg or "Unauthorized" in error_msg:
            logger.error("   错误原因: API Key 无效或未授权")
            logger.error("   请检查 .env 文件中的 OPENAI_API_KEY 是否正确")
        elif "timeout" in error_msg.lower():
            logger.error("   错误原因: 连接超时")
            logger.error("   请检查网络连接或 OPENAI_BASE_URL 配置")
        elif "Connection" in error_msg or "connect" in error_msg.lower():
            logger.error("   错误原因: 无法连接到服务器")
            logger.error(f"   请检查 Base URL: {config.base_url}")
        else:
            logger.error(f"   错误详情: {error_msg}")
        
        logger.warning("   AI功能将不可用，但基础转录功能仍可正常使用")

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")

# 创建临时目录
TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# 初始化新服务
video_preview_service = VideoPreviewService()
video_download_service = VideoDownloadService(TEMP_DIR / "downloads")
video_qa_service = VideoQAService()
video_search_agent = VideoSearchAgent()

# 存储任务状态 - 使用文件持久化
import json
import threading

TASKS_FILE = TEMP_DIR / "tasks.json"
tasks_lock = threading.Lock()

def load_tasks():
    """加载任务状态"""
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_tasks(tasks_data):
    """
    保存任务状态 - 使用原子写入防止数据损坏
    """
    try:
        with tasks_lock:
            # 使用临时文件进行原子写入
            temp_file = TASKS_FILE.with_suffix('.tmp')
            
            # 写入临时文件
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
            
            # 原子性地替换原文件
            temp_file.replace(TASKS_FILE)
            
            # 创建备份（保留最近3个备份）
            backup_dir = TEMP_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            # 生成备份文件名（带时间戳）
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"tasks_{timestamp}.json"
            
            # 复制到备份
            import shutil
            shutil.copy2(TASKS_FILE, backup_file)
            
            # 清理旧备份，只保留最近3个
            backups = sorted(backup_dir.glob("tasks_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old_backup in backups[3:]:
                old_backup.unlink()
                
    except Exception as e:
        logger.error(f"保存任务状态失败: {e}")

async def broadcast_task_update(task_id: str, task_data: dict):
    """向所有连接的SSE客户端广播任务状态更新"""
    logger.debug(f"广播任务更新: {task_id}, 状态: {task_data.get('status')}, 连接数: {len(sse_connections.get(task_id, []))}")
    if task_id in sse_connections:
        connections_to_remove = []
        for queue in sse_connections[task_id]:
            try:
                await queue.put(json.dumps(task_data, ensure_ascii=False))
            except Exception as e:
                logger.warning(f"发送消息到队列失败: {e}")
                connections_to_remove.append(queue)
        
        # 移除断开的连接
        for queue in connections_to_remove:
            sse_connections[task_id].remove(queue)
        
        # 如果没有连接了，清理该任务的连接列表
        if not sse_connections[task_id]:
            del sse_connections[task_id]

# 启动时加载任务状态
tasks = load_tasks()
# 存储正在处理的URL，防止重复处理
processing_urls = set()
# 存储活跃的任务对象，用于控制和取消
active_tasks = {}
# 存储SSE连接，用于实时推送状态更新
sse_connections = {}
# 记录连接的最后活动时间
sse_connection_last_activity = {}

def _sanitize_title_for_filename(title: str) -> str:
    """将视频标题清洗为安全的文件名片段。"""
    if not title:
        return "untitled"
    # 仅保留字母数字、下划线、连字符与空格
    safe = re.sub(r"[^\w\-\s]", "", title)
    # 压缩空白并转为下划线
    safe = re.sub(r"\s+", "_", safe).strip("._-")
    # 最长限制，避免过长文件名问题
    return safe[:80] or "untitled"

@app.get("/")
async def read_root():
    """返回前端页面"""
    return FileResponse(str(PROJECT_ROOT / "static" / "index.html"))

@app.post("/api/process-video")
async def process_video(
    url: str = Form(...),
    summary_language: str = Form(default="zh")
):
    """
    处理视频链接，返回任务ID
    """
    try:
        # 检查是否已经在处理相同的URL
        if url in processing_urls:
            # 查找现有任务
            for tid, task in tasks.items():
                if task.get("url") == url:
                    return {"task_id": tid, "message": "该视频正在处理中，请等待..."}
            
        # 生成唯一任务ID
        task_id = str(uuid.uuid4())
        
        # 标记URL为正在处理
        processing_urls.add(url)
        
        # 初始化任务状态
        tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "开始处理视频...",
            "script": None,
            "summary": None,
            "error": None,
            "url": url  # 保存URL用于去重
        }
        save_tasks(tasks)
        
        # 创建并跟踪异步任务
        task = asyncio.create_task(process_video_task(task_id, url, summary_language))
        active_tasks[task_id] = task
        
        return {"task_id": task_id, "message": "任务已创建，正在处理中..."}
        
    except Exception as e:
        logger.error(f"处理视频时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

async def process_video_task(task_id: str, url: str, summary_language: str):
    """
    异步处理视频任务 - 使用NoteGenerator服务
    """
    try:
        # 初始化NoteGenerator
        note_gen = NoteGenerator()
        
        # 定义进度回调函数
        async def progress_callback(progress: int, message: str):
            """更新任务进度并广播"""
            tasks[task_id].update({
                "status": "processing",
                "progress": progress,
                "message": message
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
        
        # 定义取消检查函数
        def cancel_check() -> bool:
            """检查任务是否被取消"""
            return task_id not in active_tasks or (
                task_id in active_tasks and active_tasks[task_id].cancelled()
            )
        
        # 调用NoteGenerator生成笔记
        result = await note_gen.generate_note(
            video_url=url,
            temp_dir=TEMP_DIR,
            summary_language=summary_language,
            progress_callback=progress_callback,
            cancel_check=cancel_check
        )
        
        # 构建任务结果（保持与旧格式100%兼容）
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
            "raw_script_filename": result["files"]["raw_transcript_filename"]
        }
        
        # 添加翻译信息（如果有）
        if "translation" in result:
            task_result.update({
                "translation": result["translation"],
                "translation_path": str(result["files"]["translation_path"]),
                "translation_filename": result["files"]["translation_filename"]
            })
        
        # 更新任务状态
        tasks[task_id].update(task_result)
        save_tasks(tasks)
        logger.debug(f"任务完成，准备广播最终状态: {task_id}")
        await broadcast_task_update(task_id, tasks[task_id])
        logger.debug(f"最终状态已广播: {task_id}")
        
        # 从处理列表中移除URL
        processing_urls.discard(url)
        
        # 从活跃任务列表中移除
        if task_id in active_tasks:
            del active_tasks[task_id]
            
    except asyncio.CancelledError:
        logger.info(f"任务 {task_id} 被取消")
        # 从处理列表中移除URL
        processing_urls.discard(url)
        
        # 从活跃任务列表中移除
        if task_id in active_tasks:
            del active_tasks[task_id]
        
        # 只有当任务还在tasks字典中时才更新状态
        if task_id in tasks:
            tasks[task_id].update({
                "status": "cancelled",
                "error": "用户取消任务",
                "message": "❌ 任务已取消"
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
        
    except Exception as e:
        logger.error(f"任务 {task_id} 处理失败: {str(e)}")
        # 从处理列表中移除URL
        processing_urls.discard(url)
        
        # 从活跃任务列表中移除
        if task_id in active_tasks:
            del active_tasks[task_id]
            
        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"处理失败: {str(e)}"
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    获取任务状态
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return tasks[task_id]

@app.get("/api/task-stream/{task_id}")
async def task_stream(task_id: str):
    """
    SSE实时任务状态流
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    async def event_generator():
        # 创建任务专用的队列
        queue = asyncio.Queue()
        
        # 将队列添加到连接列表
        if task_id not in sse_connections:
            sse_connections[task_id] = []
        sse_connections[task_id].append(queue)
        
        try:
            # 立即发送当前状态
            current_task = tasks.get(task_id, {})
            yield f"data: {json.dumps(current_task, ensure_ascii=False)}\n\n"
            
            # 持续监听状态更新
            while True:
                try:
                    # 等待状态更新，超时时间0.5秒（快速轮询）
                    data = await asyncio.wait_for(queue.get(), timeout=0.5)
                    yield f"data: {data}\n\n"
                    
                    # 如果任务完成或失败，结束流
                    task_data = json.loads(data)
                    if task_data.get("status") in ["completed", "error"]:
                        break
                        
                except asyncio.TimeoutError:
                    # 超时时发送心跳保持连接
                    yield f": heartbeat\n\n"
                    continue
                    
        except asyncio.CancelledError:
            logger.info(f"SSE连接被取消: {task_id}")
        except Exception as e:
            logger.error(f"SSE流异常: {e}")
        finally:
            # 清理连接
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
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

def validate_download_filename(filename: str) -> bool:
    """
    验证文件名安全性 - 增强版
    
    Args:
        filename: 要验证的文件名
        
    Returns:
        True if 文件名安全，False otherwise
    """
    # 1. 检查文件扩展名白名单
    allowed_extensions = ['.md']
    if not any(filename.endswith(ext) for ext in allowed_extensions):
        return False
    
    # 2. 检查危险字符
    dangerous_chars = ['..', '/', '\\', '\0', ':', '*', '?', '"', '<', '>', '|']
    if any(char in filename for char in dangerous_chars):
        return False
    
    # 3. 检查文件名长度
    if len(filename) > 255:
        return False
    
    # 4. 检查文件名不为空
    if not filename or filename.strip() == '':
        return False
    
    # 5. 解析路径并确保在temp目录内
    try:
        file_path = (TEMP_DIR / filename).resolve()
        temp_dir_resolved = TEMP_DIR.resolve()
        
        # 确保解析后的路径在temp目录内
        if not str(file_path).startswith(str(temp_dir_resolved)):
            return False
    except Exception:
        return False
    
    return True

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """
    从temp目录下载文件 - 增强安全验证
    """
    try:
        # 增强的文件名验证
        if not validate_download_filename(filename):
            logger.warning(f"非法文件下载尝试: {filename}")
            raise HTTPException(status_code=400, detail="文件名格式无效或不安全")
        
        # 构建并解析文件路径
        file_path = (TEMP_DIR / filename).resolve()
        temp_dir_resolved = TEMP_DIR.resolve()
        
        # 二次验证：确保解析后的路径仍在temp目录内
        if not str(file_path).startswith(str(temp_dir_resolved)):
            logger.warning(f"路径遍历尝试: {filename} -> {file_path}")
            raise HTTPException(status_code=403, detail="访问被拒绝")
        
        # 检查文件是否存在
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查是否为文件（不是目录）
        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="无效的文件")
        
        # 记录下载日志
        logger.info(f"文件下载: {filename}")
        
        return FileResponse(
            file_path,
            filename=filename,
            media_type="text/markdown"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """
    取消并删除任务
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 如果任务还在运行，先取消它
    if task_id in active_tasks:
        task = active_tasks[task_id]
        if not task.done():
            task.cancel()
            logger.info(f"任务 {task_id} 已被取消")
        del active_tasks[task_id]
    
    # 从处理URL列表中移除
    task_url = tasks[task_id].get("url")
    if task_url:
        processing_urls.discard(task_url)
    
    # 删除任务记录
    del tasks[task_id]
    return {"message": "任务已取消并删除"}

@app.get("/api/tasks/active")
async def get_active_tasks():
    """
    获取当前活跃任务列表（用于调试）
    """
    active_count = len(active_tasks)
    processing_count = len(processing_urls)
    return {
        "active_tasks": active_count,
        "processing_urls": processing_count,
        "task_ids": list(active_tasks.keys())
    }

@app.get("/api/preview-video")
async def preview_video(url: str):
    """
    预览视频信息
    """
    try:
        video_info = await video_preview_service.get_video_info(url)
        return {"success": True, "data": video_info}
    except Exception as e:
        logger.error(f"预览视频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")

@app.post("/api/start-download")
async def start_download(data: dict):
    """
    开始下载视频
    """
    try:
        # 确保data不为None，并且有正确的结构
        if not data:
            raise HTTPException(status_code=400, detail="请求数据不能为空")
            
        url = data.get("url") if data else None
        quality = data.get("quality", "best[height<=720]") if data else "best[height<=720]"
        
        if not url:
            raise HTTPException(status_code=400, detail="URL参数必需")
        
        # 确保quality不为None
        if quality is None:
            quality = "best[height<=720]"
            
        logger.info(f"开始下载: url={url}, quality={quality}")
        download_id = await video_download_service.start_download(url, quality)
        return {"download_id": download_id, "message": "下载已开始"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"开始下载失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")

@app.get("/api/download-stream/{download_id}")
async def download_stream(download_id: str):
    """
    下载进度SSE流
    """
    async def event_generator():
        try:
            while True:
                status = video_download_service.get_download_status(download_id)
                if not status:
                    yield f"data: {json.dumps({'error': '下载任务不存在'})}\n\n"
                    break
                
                yield f"data: {json.dumps(status, ensure_ascii=False)}\n\n"
                
                if status.get('status') in ['completed', 'error', 'cancelled']:
                    break
                    
                await asyncio.sleep(0.5)
                
        except asyncio.CancelledError:
            logger.info(f"下载流连接被取消: {download_id}")
        except Exception as e:
            logger.error(f"下载流异常: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )

@app.get("/api/get-download/{download_id}")
async def get_download_file(download_id: str):
    """
    获取下载的文件 - 强制弹出另存为对话框
    """
    try:
        from urllib.parse import quote
        
        file_path = video_download_service.get_file_path(download_id)
        if not file_path or not Path(file_path).exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        filename = Path(file_path).name
        
        # URL编码文件名以支持中文和特殊字符
        # 使用RFC 5987编码格式：filename*=UTF-8''encoded_filename
        encoded_filename = quote(filename, safe='')
        
        return FileResponse(
            file_path,
            filename=filename,
            media_type="application/octet-stream",
            headers={
                # 同时提供两种格式以兼容不同浏览器
                "Content-Disposition": f"attachment; filename=\"{filename.encode('ascii', 'ignore').decode('ascii')}\"; filename*=UTF-8''{encoded_filename}"
            }
        )
    except Exception as e:
        logger.error(f"获取下载文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文件失败: {str(e)}")

@app.delete("/api/cancel-download/{download_id}")
async def cancel_download(download_id: str):
    """
    取消下载
    """
    try:
        success = await video_download_service.cancel_download(download_id)
        if success:
            return {"message": "下载已取消"}
        else:
            raise HTTPException(status_code=404, detail="下载任务不存在")
    except Exception as e:
        logger.error(f"取消下载失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"取消失败: {str(e)}")

@app.post("/api/transcribe-only")
async def transcribe_only(
    url: Optional[str] = Form(None),
    file_path: Optional[str] = Form(None)
):
    """
    仅转录视频音频（用于视频问答预处理）
    - 支持在线URL和本地路径两种模式
    - 只下载音频/读取本地文件 + 转录
    - 不生成摘要、不优化文本、不翻译
    - 速度更快，资源消耗更少
    """
    try:
        # 验证参数
        if not url and not file_path:
            raise HTTPException(status_code=400, detail="url或file_path参数必需")
        
        if url and file_path:
            raise HTTPException(status_code=400, detail="url和file_path不能同时提供")
        
        task_id = str(uuid.uuid4())
        
        # 确定处理模式
        if file_path:
            # 本地路径模式
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
            
            if not os.path.isfile(file_path):
                raise HTTPException(status_code=400, detail="路径不是有效的文件")
            
            tasks[task_id] = {
                "status": "processing",
                "progress": 0,
                "message": "开始转录本地文件...",
                "transcript": None,
                "error": None,
                "source": "local_path",
                "file_path": file_path
            }
            save_tasks(tasks)
            
            task = asyncio.create_task(transcribe_local_file_task(task_id, file_path))
            active_tasks[task_id] = task
        else:
            # URL模式
            tasks[task_id] = {
                "status": "processing",
                "progress": 0,
                "message": "开始转录视频...",
                "transcript": None,
                "error": None,
                "url": url
            }
            save_tasks(tasks)
            
            task = asyncio.create_task(transcribe_only_task(task_id, url))
            active_tasks[task_id] = task
        
        return {"task_id": task_id, "message": "转录任务已创建"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建转录任务时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

async def transcribe_local_file_task(task_id: str, file_path: str):
    """仅转录本地文件任务 - 轻量级版本（问答专用）"""
    from backend.services.audio_transcriber import AudioTranscriber
    import subprocess
    
    try:
        audio_transcriber = AudioTranscriber()
        
        # 获取文件名作为标题
        video_title = Path(file_path).stem
        
        # 判断是否为视频文件
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'}
        is_video = Path(file_path).suffix.lower() in video_exts
        
        # 1. 提取/准备音频 (0-40%)
        tasks[task_id].update({
            "progress": 5,
            "message": "正在提取音频..." if is_video else "正在准备音频..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        if is_video:
            # 从视频提取音频到临时文件
            audio_path = str(TEMP_DIR / f"{task_id}.wav")
            cmd = [
                'ffmpeg', '-i', file_path,
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',
                '-y', audio_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)
        else:
            # 直接使用音频文件
            audio_path = file_path
        
        tasks[task_id].update({
            "progress": 40,
            "message": "正在转录音频..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # 2. 转录音频 (40-100%)
        transcript = await audio_transcriber.transcribe_audio(audio_path)
        
        # 清理临时音频文件(如果是从视频提取的)
        if is_video and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except:
                pass
        
        # 完成
        tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "",
            "transcript": transcript,
            "video_title": video_title
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        if task_id in active_tasks:
            del active_tasks[task_id]
            
    except asyncio.CancelledError:
        logger.info(f"本地文件转录任务 {task_id} 被取消")
        if task_id in active_tasks:
            del active_tasks[task_id]
        if task_id in tasks:
            tasks[task_id].update({
                "status": "cancelled",
                "error": "用户取消任务",
                "message": "❌ 任务已取消"
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
    except Exception as e:
        logger.error(f"本地文件转录任务 {task_id} 失败: {str(e)}")
        if task_id in active_tasks:
            del active_tasks[task_id]
        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"转录失败: {str(e)}"
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

async def transcribe_only_task(task_id: str, url: str):
    """仅转录任务 - 轻量级版本（问答专用）"""
    from backend.services.video_downloader import VideoDownloader
    from backend.services.audio_transcriber import AudioTranscriber
    
    try:
        video_downloader = VideoDownloader()
        audio_transcriber = AudioTranscriber()
        
        # 1. 下载音频 (0-40%)
        tasks[task_id].update({
            "progress": 5,
            "message": ""
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        audio_path, video_title = await video_downloader.download_video_audio(url, TEMP_DIR)
        
        tasks[task_id].update({
            "progress": 40,
            "message": ""
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # 2. 转录音频 (40-100%)
        tasks[task_id].update({
            "progress": 45,
            "message": ""
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        transcript = await audio_transcriber.transcribe_audio(audio_path)
        
        # 清理音频文件
        try:
            Path(audio_path).unlink()
        except:
            pass
        
        # 完成
        tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "",
            "transcript": transcript,
            "video_title": video_title
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        if task_id in active_tasks:
            del active_tasks[task_id]
            
    except asyncio.CancelledError:
        logger.info(f"转录任务 {task_id} 被取消")
        if task_id in active_tasks:
            del active_tasks[task_id]
        if task_id in tasks:
            tasks[task_id].update({
                "status": "cancelled",
                "error": "用户取消任务",
                "message": "❌ 任务已取消"
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
    except Exception as e:
        logger.error(f"转录任务 {task_id} 失败: {str(e)}")
        if task_id in active_tasks:
            del active_tasks[task_id]
        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"转录失败: {str(e)}"
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

@app.post("/api/video-qa-stream")
async def video_qa_stream(request: Request):
    """
    基于视频转录文本的智能问答 - 流式输出
    """
    try:
        data = await request.json()
        question = data.get('question', '').strip()
        transcript = data.get('transcript', '').strip()
        video_url = data.get('video_url', '')
        
        if not question:
            raise HTTPException(status_code=400, detail="问题不能为空")
        
        if not transcript:
            raise HTTPException(status_code=400, detail="转录文本不能为空")
        
        # 检查问答服务是否可用
        if not video_qa_service.is_available():
            raise HTTPException(status_code=503, detail="AI服务暂时不可用，请稍后重试")
        
        logger.info(f"正在处理问答流: {question[:50]}...")
        
        async def event_generator():
            try:
                # 使用VideoQAService进行流式问答
                async for content in video_qa_service.answer_question_stream(question, transcript, video_url):
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                
                # 发送完成信号
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                
            except Exception as e:
                logger.error(f"问答流异常: {e}")
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"视频问答失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")

@app.post("/api/process-local-path")
async def process_local_path(request: Request):
    """
    处理本地文件路径（本地视频/音频转录）
    不需要下载,直接读取本地文件进行处理
    """
    try:
        data = await request.json()
        file_path = data.get('file_path', '').strip()
        summary_language = data.get('language', 'zh')
        
        if not file_path:
            raise HTTPException(status_code=400, detail="文件路径不能为空")
        
        # 验证文件是否存在
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
        
        # 验证是否为文件
        if not os.path.isfile(file_path):
            raise HTTPException(status_code=400, detail="路径不是有效的文件")
        
        # 验证文件格式
        valid_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv',
                          '.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext not in valid_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件格式: {file_ext}")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "开始处理本地文件...",
            "script": None,
            "summary": None,
            "error": None,
            "source": "local_path",
            "file_path": file_path
        }
        save_tasks(tasks)
        
        # 创建后台任务
        task = asyncio.create_task(process_local_path_task(task_id, file_path, summary_language))
        active_tasks[task_id] = task
        
        return {"task_id": task_id, "message": "本地文件处理任务已创建"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理本地路径时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

async def process_local_path_task(task_id: str, file_path: str, summary_language: str):
    """
    处理本地文件的后台任务
    """
    from backend.services.audio_transcriber import AudioTranscriber
    from backend.services.text_optimizer import TextOptimizer
    from backend.services.content_summarizer import ContentSummarizer
    from backend.services.text_translator import TextTranslator
    import subprocess
    
    try:
        # 获取文件名作为标题
        video_title = Path(file_path).stem
        
        # 判断是否为视频文件
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'}
        is_video = Path(file_path).suffix.lower() in video_exts
        
        # 1. 提取/准备音频 (0-20%)
        tasks[task_id].update({
            "progress": 5,
            "message": "正在提取音频..." if is_video else "正在准备音频..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        if is_video:
            # 从视频提取音频到临时文件
            audio_path = str(TEMP_DIR / f"{task_id}.wav")
            cmd = [
                'ffmpeg', '-i', file_path,
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',
                '-y', audio_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)
        else:
            # 直接使用音频文件
            audio_path = file_path
        
        tasks[task_id].update({"progress": 20})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # 2. 转录音频 (20-50%)
        tasks[task_id].update({
            "progress": 25,
            "message": "正在转录音频..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        audio_transcriber = AudioTranscriber()
        raw_transcript = await audio_transcriber.transcribe_audio(audio_path)
        
        # 清理临时音频文件(如果是从视频提取的)
        if is_video and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except:
                pass
        
        tasks[task_id].update({"progress": 50})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # 3. 优化文本 (50-70%)
        tasks[task_id].update({
            "progress": 55,
            "message": "正在优化文本..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        text_optimizer = TextOptimizer()
        optimized_transcript = await text_optimizer.optimize_transcript(raw_transcript)
        
        tasks[task_id].update({"progress": 70})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # 4. 生成摘要 (70-90%)
        tasks[task_id].update({
            "progress": 75,
            "message": "正在生成摘要..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        content_summarizer = ContentSummarizer()
        summary = await content_summarizer.summarize(optimized_transcript, summary_language)
        
        tasks[task_id].update({"progress": 90})
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # 5. 保存结果文件
        short_id = task_id.replace("-", "")[:6]
        safe_title = _sanitize_title_for_filename(video_title)
        
        # 保存文件
        transcript_filename = f"{short_id}_{safe_title}_笔记.md"
        summary_filename = f"{short_id}_{safe_title}_摘要.md"
        raw_transcript_filename = f"{short_id}_{safe_title}_原文.md"
        
        transcript_path = TEMP_DIR / transcript_filename
        summary_path = TEMP_DIR / summary_filename
        raw_transcript_path = TEMP_DIR / raw_transcript_filename
        
        async with aiofiles.open(transcript_path, 'w', encoding='utf-8') as f:
            await f.write(optimized_transcript)
        
        async with aiofiles.open(summary_path, 'w', encoding='utf-8') as f:
            await f.write(summary)
        
        async with aiofiles.open(raw_transcript_path, 'w', encoding='utf-8') as f:
            await f.write(raw_transcript)
        
        # 6. 完成
        tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "🎉 处理完成！",
            "video_title": video_title,
            "script": optimized_transcript,
            "summary": summary,
            "raw_script": raw_transcript,
            "script_path": str(transcript_path),
            "summary_path": str(summary_path),
            "short_id": short_id,
            "safe_title": safe_title,
            "summary_language": summary_language,
            "raw_script_filename": raw_transcript_filename
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        if task_id in active_tasks:
            del active_tasks[task_id]
            
    except asyncio.CancelledError:
        logger.info(f"本地文件处理任务 {task_id} 被取消")
        if task_id in active_tasks:
            del active_tasks[task_id]
        if task_id in tasks:
            tasks[task_id].update({
                "status": "cancelled",
                "error": "用户取消任务",
                "message": "❌ 任务已取消"
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
    except Exception as e:
        logger.error(f"本地文件处理任务 {task_id} 失败: {str(e)}")
        if task_id in active_tasks:
            del active_tasks[task_id]
        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"处理失败: {str(e)}"
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

@app.post("/api/search-agent-chat")
async def search_agent_chat(request: Request):
    """
    视频搜索Agent聊天接口 - 流式响应
    支持智能视频搜索和对话
    """
    try:
        data = await request.json()
        message = data.get('message', '').strip()
        session_id = data.get('session_id', 'default')
        
        if not message:
            raise HTTPException(status_code=400, detail="消息不能为空")
        
        if not video_search_agent.is_available():
            raise HTTPException(status_code=503, detail="AI服务暂时不可用，请稍后重试")
        
        logger.info(f"处理Agent消息: {message[:50]}...")
        
        async def event_generator():
            try:
                async for event in video_search_agent.process_message(message, session_id):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Agent聊天异常: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索Agent聊天失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

@app.post("/api/search-agent-generate-notes")
async def search_agent_generate_notes(request: Request):
    """
    为选中的视频生成笔记 - 流式响应
    在搜索Agent中选择视频后调用此接口生成笔记
    """
    try:
        data = await request.json()
        video_url = data.get('video_url', '').strip()
        summary_language = data.get('summary_language', 'zh')
        
        if not video_url:
            raise HTTPException(status_code=400, detail="视频URL不能为空")
        
        # 生成任务ID
        generation_id = str(uuid.uuid4())
        logger.info(f"为视频生成笔记: {video_url}, 任务ID: {generation_id}")
        
        async def event_generator():
            try:
                # 首先发送任务ID
                yield f"data: {json.dumps({'type': 'generation_id', 'generation_id': generation_id}, ensure_ascii=False)}\n\n"
                
                # 流式生成笔记
                async for event in video_search_agent.generate_notes_for_video(
                    video_url=video_url,
                    temp_dir=TEMP_DIR,
                    summary_language=summary_language,
                    generation_id=generation_id
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"生成笔记异常: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成笔记失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

@app.delete("/api/search-agent-cancel-generation/{generation_id}")
async def cancel_note_generation(generation_id: str):
    """
    取消笔记生成任务
    """
    try:
        success = video_search_agent.cancel_generation(generation_id)
        if success:
            logger.info(f"笔记生成任务已取消: {generation_id}")
            return {"message": "任务已取消", "generation_id": generation_id}
        else:
            raise HTTPException(status_code=404, detail="任务不存在或已完成")
    except Exception as e:
        logger.error(f"取消笔记生成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"取消失败: {str(e)}")

@app.post("/api/search-agent-clear-session")
async def search_agent_clear_session(request: Request):
    """
    清空指定会话的对话历史
    """
    try:
        data = await request.json()
        session_id = data.get('session_id', 'default')
        
        video_search_agent.clear_conversation(session_id)
        logger.info(f"已清空会话: {session_id}")
        
        return {"message": "会话已清空", "session_id": session_id}
        
    except Exception as e:
        logger.error(f"清空会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")

@app.get("/api/proxy-image")
async def proxy_image(url: str):
    """
    图片代理接口 - 解决B站等平台的防盗链问题
    """
    try:
        import httpx
        from urllib.parse import unquote
        
        # URL解码
        image_url = unquote(url)
        
        # 验证URL格式
        if not image_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="无效的图片URL")
        
        # 设置请求头，伪装成正常浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',  # B站防盗链关键
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        # 根据URL设置不同的Referer
        if 'bilibili.com' in image_url or 'hdslb.com' in image_url:
            headers['Referer'] = 'https://www.bilibili.com/'
        elif 'youtube.com' in image_url or 'ytimg.com' in image_url:
            headers['Referer'] = 'https://www.youtube.com/'
        
        # 请求图片
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(image_url, headers=headers)
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="获取图片失败")
            
            # 获取内容类型
            content_type = response.headers.get('content-type', 'image/jpeg')
            
            # 返回图片内容
            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # 缓存24小时
                    "Access-Control-Allow-Origin": "*"
                }
            )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="图片请求超时")
    except httpx.HTTPError as e:
        logger.error(f"代理图片请求失败: {e}")
        raise HTTPException(status_code=500, detail=f"代理请求失败: {str(e)}")
    except Exception as e:
        logger.error(f"代理图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"代理失败: {str(e)}")

@app.post("/api/dev-tools/generate-cookies-stream")
async def generate_cookies_stream(request: Request):
    """
    开发者工具: 将B站Cookies转换为Netscape格式 - 流式输出
    """
    from backend.core.ai_client import get_async_openai_client
    from backend.config.ai_config import get_openai_config
    import re
    
    try:
        data = await request.json()
        cookies_text = data.get('cookies_text', '').strip()
        
        if not cookies_text:
            raise HTTPException(status_code=400, detail="Cookies内容不能为空")
        
        # 获取全局AI配置和客户端
        config = get_openai_config()
        client = get_async_openai_client()
        
        if not client:
            raise HTTPException(status_code=503, detail="AI服务不可用")
        
        prompt = f"""请将以下 B 站 Cookies 转换为标准的 Netscape HTTP Cookie File 格式。

输入 Cookies:
{cookies_text}

严格要求：
1. 第一行：# Netscape HTTP Cookie File
2. 第二行：# This file is generated by yt-dlp.  Do not edit.
3. 第三行：空行
4. 从第四行开始，每个 cookie 占一行，字段顺序严格为：
   domain[TAB]flag[TAB]path[TAB]secure[TAB]expiration[TAB]name[TAB]value
5. 所有字段之间必须使用制表符（Tab）分隔，而不是空格。
6. 固定字段值：
   - domain = .bilibili.com
   - flag = TRUE
   - path = /
   - secure = FALSE
   - expiration = 1893456000
7. 从输入中提取所有 cookie 的 name 和 value。
8. 绝对不要输出任何Markdown代码块标记（如```），不要输出任何解释文字，只输出纯文本内容。
9. 直接从第一个字符开始输出"# Netscape HTTP Cookie File"。

期望输出格式示例：

# Netscape HTTP Cookie File
# This file is generated by yt-dlp.  Do not edit.

.bilibili.com	TRUE	/	FALSE	1893456000	_uuid	value1
.bilibili.com	TRUE	/	FALSE	1893456000	SESSDATA	value2
"""

        async def event_generator():
            try:
                # 流式调用AI
                stream = await client.chat.completions.create(
                    model=config.model,
                    messages=[
                        {
                            "role": "system", 
                            "content": "你是Netscape Cookie格式转换专家。只输出标准格式的cookie文件内容，不添加任何解释。"
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0,
                    stream=True
                )
                
                full_content = ""
                async for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_content += content
                        # 流式推送每个字符
                        yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                
                # 发送完成信号
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                
                logger.info(f"Cookies转换流式输出完成")
                
            except Exception as e:
                logger.error(f"流式转换失败: {e}")
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cookies转换失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8999)
