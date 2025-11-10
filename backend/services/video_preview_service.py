"""
视频预览服务
获取视频信息而无需下载
"""
import logging
import asyncio
import re
import os
from typing import Dict
import yt_dlp

logger = logging.getLogger(__name__)


class VideoPreviewService:
    """视频预览服务"""
    
    def __init__(self):
        """初始化视频预览服务"""
        # 获取cookies文件路径（项目根目录）
        from pathlib import Path
        self.project_root = Path(__file__).parent.parent.parent
        self.bilibili_cookies = self.project_root / "bilibili_cookies.txt"
        
        # 初始化 YouTube API Helper
        from backend.utils.youtube_api_helper import YouTubeAPIHelper
        youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        self.youtube_helper = YouTubeAPIHelper(api_key=youtube_api_key)
        
        # 基础配置（不含 cookies） - 移除可能导致问题的 http_headers
        self.base_ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }
    
    def _get_cookies_for_url(self, url: str) -> str:
        """根据 URL 获取对应的 cookies 文件路径"""
        # 仅B站使用 cookies，YouTube 不使用（避免认证问题）
        if 'bilibili.com' in url or 'b23.tv' in url:
            if self.bilibili_cookies.exists():
                logger.info(f"使用 B站 cookies: {self.bilibili_cookies}")
                return str(self.bilibili_cookies)
        
        return None

    async def get_video_info(self, url: str) -> Dict:
        """
        获取视频信息 - 智能选择最佳方式
        YouTube: 优先使用 API (快速) → 降级到 yt-dlp
        其他平台: 直接使用 yt-dlp
        
        Args:
            url: 视频链接
            
        Returns:
            视频信息字典
        """
        try:
            logger.info(f"开始获取视频信息: {url}")
            
            # 判断是否为 YouTube 视频
            if self.youtube_helper.is_youtube_url(url):
                # 尝试使用 YouTube API (快速方案)
                api_info = await self._get_info_via_youtube_api(url)
                if api_info:
                    logger.info(f"✅ YouTube API 获取成功: {api_info['title']}")
                    return api_info
                
                # API 失败,降级到 yt-dlp
                logger.warning("⚠️ YouTube API 获取失败,降级使用 yt-dlp")
            
            # 非 YouTube 或 API 失败,使用 yt-dlp (通用方案)
            return await self._get_info_via_ytdlp(url)
            
        except Exception as e:
            logger.error(f"获取视频信息失败: {str(e)}")
            raise Exception(f"获取视频信息失败: {str(e)}")
    
    async def _get_info_via_youtube_api(self, url: str) -> Dict:
        """
        通过 YouTube API 获取视频信息 (仅 YouTube)
        
        Args:
            url: YouTube 视频链接
            
        Returns:
            视频信息字典或 None
        """
        if not self.youtube_helper.enabled:
            return None
        
        try:
            api_info = await self.youtube_helper.get_video_info_from_url(url)
            if not api_info:
                return None
            
            # API 返回的格式已经符合要求,添加 formats 字段(API 无法获取)
            api_info['formats'] = []  # API 模式下不提供下载格式
            
            return api_info
            
        except Exception as e:
            logger.warning(f"YouTube API 获取失败: {e}")
            return None
    
    async def _get_info_via_ytdlp(self, url: str) -> Dict:
        """
        通过 yt-dlp 获取视频信息 (通用方案,支持所有平台)
        
        Args:
            url: 视频链接
            
        Returns:
            视频信息字典
        """
        # 根据 URL 选择对应的 cookies
        ydl_opts = self.base_ydl_opts.copy()
        cookies_file = self._get_cookies_for_url(url)
        if cookies_file:
            ydl_opts['cookiefile'] = cookies_file
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, False)
        
        video_info = {
            'title': info.get('title', 'Unknown Title'),
            'duration': info.get('duration', 0),
            'duration_string': self._format_duration(info.get('duration', 0)),
            'description': info.get('description', '')[:500] + '...' if info.get('description', '') else '',
            'uploader': info.get('uploader', 'Unknown'),
            'upload_date': self._format_date(info.get('upload_date')),
            'view_count': info.get('view_count', 0),
            'view_count_string': self._format_view_count(info.get('view_count', 0)),
            'thumbnail': self._get_best_thumbnail(info.get('thumbnails', [])),
            'webpage_url': info.get('webpage_url', url),
            'extractor': info.get('extractor', 'unknown'),
            'formats': self._extract_download_formats(info.get('formats', [])),
            'embed_url': self._get_embed_url(url, info),
            'source': 'yt-dlp'  # 标记数据来源
        }
        
        logger.info(f"视频信息获取成功 (yt-dlp): {video_info['title']}")
        return video_info
    
    def _format_duration(self, duration) -> str:
        """格式化时长为可读字符串"""
        if not duration:
            return "未知"
        
        duration = int(duration)
        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def _format_date(self, date_str: str) -> str:
        """格式化上传日期"""
        if not date_str:
            return "未知"
        
        try:
            if len(date_str) == 8:
                year = date_str[:4]
                month = date_str[4:6]
                day = date_str[6:8]
                return f"{year}-{month}-{day}"
        except:
            pass
        
        return date_str
    
    def _format_view_count(self, view_count: int) -> str:
        """格式化观看次数"""
        if not view_count:
            return "0"
        
        if view_count >= 1000000:
            return f"{view_count/1000000:.1f}M"
        elif view_count >= 1000:
            return f"{view_count/1000:.1f}K"
        else:
            return str(view_count)
    
    def _get_best_thumbnail(self, thumbnails: list) -> str:
        """获取最佳缩略图URL"""
        if not thumbnails:
            return ""
        
        thumbnails_sorted = sorted(
            thumbnails, 
            key=lambda x: (x.get('width', 0) * x.get('height', 0)), 
            reverse=True
        )
        
        return thumbnails_sorted[0].get('url', '') if thumbnails_sorted else ''
    
    def _extract_download_formats(self, formats: list) -> list:
        """提取可下载的格式信息"""
        if not formats:
            return []
        
        video_formats = []
        seen_qualities = set()
        
        for fmt in formats:
            if fmt.get('vcodec') and fmt.get('vcodec') != 'none':
                height = fmt.get('height')
                if height and height not in seen_qualities:
                    video_formats.append({
                        'format_id': fmt.get('format_id'),
                        'ext': fmt.get('ext', 'mp4'),
                        'quality': f"{height}p",
                        'height': height,
                        'filesize': fmt.get('filesize'),
                        'filesize_string': self._format_filesize(fmt.get('filesize')),
                        'fps': fmt.get('fps'),
                        'vcodec': fmt.get('vcodec'),
                        'acodec': fmt.get('acodec')
                    })
                    seen_qualities.add(height)
        
        video_formats.sort(key=lambda x: x['height'], reverse=True)
        
        common_qualities = [2160, 1440, 1080, 720, 480, 360]
        filtered_formats = []
        
        for quality in common_qualities:
            for fmt in video_formats:
                if fmt['height'] == quality:
                    filtered_formats.append(fmt)
                    break
        
        return filtered_formats
    
    def _format_filesize(self, filesize: int) -> str:
        """格式化文件大小"""
        if not filesize:
            return "未知大小"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if filesize < 1024:
                return f"{filesize:.1f} {unit}"
            filesize /= 1024
        
        return f"{filesize:.1f} TB"
    
    def _get_embed_url(self, url: str, info: dict) -> str:
        """获取嵌入播放URL"""
        extractor = info.get('extractor', '').lower()
        
        # YouTube 嵌入支持
        if 'youtube' in extractor:
            video_id = info.get('id')
            if video_id:
                return f"https://www.youtube.com/embed/{video_id}"
        
        # Bilibili 嵌入支持
        if 'bilibili' in extractor:
            video_id = info.get('id')
            if video_id:
                # B站使用 player.bilibili.com 的嵌入播放器
                return f"https://player.bilibili.com/player.html?bvid={video_id}&high_quality=1&danmaku=0"
        
        return url
    
    def is_embeddable(self, url: str) -> bool:
        """判断视频是否支持嵌入播放"""
        youtube_pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/)'
        return bool(re.search(youtube_pattern, url))
