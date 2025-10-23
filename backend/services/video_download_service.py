"""
视频下载服务
支持进度跟踪和并发下载
"""
import logging
import asyncio
import uuid
import threading
from pathlib import Path
from typing import Dict, Optional, Callable
from datetime import datetime
import yt_dlp

logger = logging.getLogger(__name__)


class VideoDownloadService:
    """视频下载服务 """
    
    def __init__(self, download_dir: Path):
        """
        初始化下载服务
        
        Args:
            download_dir: 下载目录路径
        """
        self.download_dir = download_dir
        self.download_dir.mkdir(exist_ok=True)
        
        self.active_downloads: Dict[str, Dict] = {}
        self.download_callbacks: Dict[str, list] = {}
        self._lock = threading.Lock()
    
    async def start_download(self, url: str, quality: str, download_id: str = None) -> str:
        """
        开始下载视频
        
        Args:
            url: 视频链接
            quality: 视频质量
            download_id: 下载ID（可选）
            
        Returns:
            下载ID
        """
        if download_id is None:
            download_id = str(uuid.uuid4())
        
        try:
            self._init_download_status(download_id, url, quality)
            task = asyncio.create_task(self._download_video(download_id, url, quality))
            
            with self._lock:
                self.active_downloads[download_id]['task'] = task
            
            logger.info(f"下载任务已启动: {download_id}")
            return download_id
            
        except Exception as e:
            logger.error(f"启动下载失败: {str(e)}")
            self._update_download_status(download_id, {
                'status': 'error',
                'error': str(e)
            })
            raise
    
    def _init_download_status(self, download_id: str, url: str, quality: str):
        """初始化下载状态"""
        with self._lock:
            self.active_downloads[download_id] = {
                'id': download_id,
                'url': url,
                'quality': quality,
                'status': 'initializing',
                'progress': 0.0,
                'speed': '',
                'eta': '',
                'downloaded_bytes': 0,
                'total_bytes': 0,
                'filename': '',
                'filepath': '',
                'current_operation': 'initializing',
                'error': None,
                'created_at': datetime.now().isoformat(),
                'task': None,
                'cancel_event': threading.Event()
            }
    
    async def _download_video(self, download_id: str, url: str, quality: str):
        """执行实际的视频下载"""
        try:
            self._update_download_status(download_id, {
                'status': 'downloading',
                'current_operation': 'downloading',
                'progress': 0.0
            })
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            short_id = download_id[:8]
            output_template = str(self.download_dir / f"video_{timestamp}_{short_id}_%(title)s.%(ext)s")
            
            # B站兼容的格式选择策略
            if not quality or quality == "best":
                format_selector = "best[ext=mp4]/best/bestvideo+bestaudio"
            elif quality and "height" in quality:
                try:
                    height_limit = quality.split("<=")[1].replace("]", "") if "<=" in quality else "720"
                    format_selector = f"best[height<={height_limit}][ext=mp4]/best[height<={height_limit}]/bestvideo[height<={height_limit}]+bestaudio"
                except (IndexError, AttributeError):
                    format_selector = "best[ext=mp4]/best/bestvideo+bestaudio"
            else:
                format_selector = f"{quality}[ext=mp4]/{quality}/best" if quality else "best[ext=mp4]/best/bestvideo+bestaudio"
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'progress_hooks': [self._create_progress_hook(download_id)],
                'postprocessor_hooks': [self._create_postprocessor_hook(download_id)],
                'quiet': True,
                'no_warnings': True,
                'no_color': True,
                'merge_output_format': 'mp4',  # 合并音视频为mp4
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                # B站专用请求头
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/'
                },
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await asyncio.to_thread(ydl.download, [url])
            
            downloaded_file = self._find_downloaded_file(download_id)
            
            if downloaded_file:
                self._update_download_status(download_id, {
                    'status': 'completed',
                    'current_operation': 'completed',
                    'progress': 100.0,
                    'filepath': str(downloaded_file),
                    'filename': downloaded_file.name
                })
                logger.info(f"下载完成: {download_id} -> {downloaded_file}")
            else:
                raise Exception("未找到下载的文件")
                
        except Exception as e:
            logger.error(f"下载失败 {download_id}: {str(e)}")
            self._update_download_status(download_id, {
                'status': 'error',
                'error': str(e)
            })
    
    def _create_progress_hook(self, download_id: str):
        """创建进度回调函数"""
        def progress_hook(d):
            try:
                with self._lock:
                    if download_id in self.active_downloads:
                        cancel_event = self.active_downloads[download_id].get('cancel_event')
                        if cancel_event and cancel_event.is_set():
                            logger.info(f"下载被用户取消: {download_id}")
                            raise yt_dlp.utils.DownloadCancelled("用户取消下载")
                
                if d['status'] == 'downloading':
                    if 'total_bytes' in d and d['total_bytes']:
                        progress = (d['downloaded_bytes'] / d['total_bytes']) * 100
                    elif 'total_bytes_estimate' in d and d['total_bytes_estimate']:
                        progress = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
                    else:
                        progress = 0.0
                    
                    speed = d.get('_speed_str', '').strip() or '0B/s'
                    eta = d.get('_eta_str', '').strip() or '--:--'
                    
                    self._update_download_status(download_id, {
                        'progress': round(progress, 1),
                        'speed': speed,
                        'eta': eta,
                        'downloaded_bytes': d.get('downloaded_bytes', 0),
                        'total_bytes': d.get('total_bytes') or d.get('total_bytes_estimate', 0),
                        'filename': d.get('filename', '').split('/')[-1] if d.get('filename') else ''
                    })
                    
                elif d['status'] == 'finished':
                    self._update_download_status(download_id, {
                        'current_operation': 'processing',
                        'progress': 95.0
                    })
                    
            except Exception as e:
                logger.error(f"进度回调错误 {download_id}: {e}")
                raise
        
        return progress_hook
    
    def _create_postprocessor_hook(self, download_id: str):
        """创建后处理回调函数"""
        def postprocessor_hook(d):
            try:
                if d['status'] == 'started':
                    self._update_download_status(download_id, {
                        'current_operation': 'processing'
                    })
                elif d['status'] == 'finished':
                    self._update_download_status(download_id, {
                        'current_operation': 'finalizing',
                        'progress': 98.0
                    })
            except Exception as e:
                logger.error(f"后处理回调错误 {download_id}: {e}")
        
        return postprocessor_hook
    
    def _find_downloaded_file(self, download_id: str) -> Optional[Path]:
        """查找下载完成的文件"""
        try:
            with self._lock:
                if download_id in self.active_downloads:
                    filename = self.active_downloads[download_id].get('filename')
                    if filename:
                        file_path = self.download_dir / filename
                        if file_path.exists():
                            return file_path
            
            short_id = download_id[:8]
            pattern = f"video_*_{short_id}_*"
            matching_files = list(self.download_dir.glob(pattern))
            
            if matching_files:
                return max(matching_files, key=lambda f: f.stat().st_mtime)
            
            return None
            
        except Exception as e:
            logger.error(f"查找下载文件失败 {download_id}: {e}")
            return None
    
    def _update_download_status(self, download_id: str, updates: Dict):
        """更新下载状态"""
        with self._lock:
            if download_id in self.active_downloads:
                self.active_downloads[download_id].update(updates)
                
                if download_id in self.download_callbacks:
                    clean_status = self.active_downloads[download_id].copy()
                    if 'task' in clean_status:
                        del clean_status['task']
                    if 'cancel_event' in clean_status:
                        del clean_status['cancel_event']
                    
                    for callback in self.download_callbacks[download_id]:
                        try:
                            asyncio.create_task(callback(clean_status))
                        except Exception as e:
                            logger.error(f"回调函数执行失败: {e}")
    
    def get_download_status(self, download_id: str) -> Optional[Dict]:
        """获取下载状态"""
        with self._lock:
            if download_id in self.active_downloads:
                status = self.active_downloads[download_id].copy()
                if 'task' in status:
                    del status['task']
                if 'cancel_event' in status:
                    del status['cancel_event']
                return status
            return None
    
    async def cancel_download(self, download_id: str) -> bool:
        """取消下载"""
        try:
            logger.info(f"开始取消下载: {download_id}")
            
            task_to_cancel = None
            cancel_event = None
            download_exists = False
            
            with self._lock:
                if download_id in self.active_downloads:
                    download_exists = True
                    download_info = self.active_downloads[download_id]
                    task_to_cancel = download_info.get('task')
                    cancel_event = download_info.get('cancel_event')
            
            if not download_exists:
                logger.warning(f"下载任务不存在: {download_id}")
                return False
            
            if cancel_event:
                cancel_event.set()
            
            if task_to_cancel and not task_to_cancel.done():
                task_to_cancel.cancel()
                try:
                    await asyncio.wait_for(task_to_cancel, timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    logger.info(f"下载任务已取消: {download_id}")
                except Exception as e:
                    logger.warning(f"取消任务时出现异常: {e}")
            
            await self._cleanup_partial_downloads(download_id)
            
            self._update_download_status(download_id, {
                'status': 'cancelled',
                'current_operation': 'cancelled',
                'progress': 0.0,
                'speed': '',
                'eta': '',
                'error': None
            })
            
            logger.info(f"下载已成功取消: {download_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消下载失败 {download_id}: {e}")
            return False
    
    async def _cleanup_partial_downloads(self, download_id: str):
        """清理未完成的下载文件"""
        try:
            short_id = download_id[:8]
            patterns = [
                f"video_*_{short_id}_*.part",
                f"video_*_{short_id}_*.ytdl",
                f"video_*_{short_id}_*.temp.*",
            ]
            
            files_to_delete = []
            for pattern in patterns:
                files_to_delete.extend(self.download_dir.glob(pattern))
            
            for file_path in files_to_delete:
                try:
                    if file_path.exists():
                        await asyncio.to_thread(file_path.unlink)
                        logger.info(f"已删除临时文件: {file_path}")
                except Exception as e:
                    logger.warning(f"删除临时文件失败 {file_path}: {e}")
            
            if files_to_delete:
                logger.info(f"清理了 {len(files_to_delete)} 个临时文件")
            
        except Exception as e:
            logger.error(f"清理临时文件失败 {download_id}: {e}")
    
    def get_file_path(self, download_id: str) -> Optional[str]:
        """获取下载文件路径"""
        with self._lock:
            download_info = self.active_downloads.get(download_id)
            if download_info and download_info.get('status') == 'completed':
                return download_info.get('filepath')
        return None
    
    def list_active_downloads(self) -> list:
        """列出所有活跃的下载"""
        with self._lock:
            result = []
            for info in self.active_downloads.values():
                clean_info = info.copy()
                if 'task' in clean_info:
                    del clean_info['task']
                if 'cancel_event' in clean_info:
                    del clean_info['cancel_event']
                result.append(clean_info)
            return result
