"""
YouTube Data API v3 辅助工具
用于快速获取 YouTube 视频信息,减少对 yt-dlp 的依赖
"""
import re
import logging
import asyncio
from typing import Optional, Dict
import httpx
from datetime import timedelta

logger = logging.getLogger(__name__)


class YouTubeAPIHelper:
    """YouTube Data API v3 辅助类"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 YouTube API 客户端
        
        Args:
            api_key: YouTube Data API v3 密钥
        """
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.enabled = bool(api_key)
        
        if not self.enabled:
            logger.warning("YouTube API 未配置,将使用 yt-dlp 降级方案")
    
    def is_youtube_url(self, url: str) -> bool:
        """
        判断是否为 YouTube URL
        
        Args:
            url: 视频链接
            
        Returns:
            True if YouTube URL, False otherwise
        """
        youtube_patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/v/([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in youtube_patterns:
            if re.search(pattern, url):
                return True
        return False
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """
        从 YouTube URL 提取视频 ID
        
        Args:
            url: YouTube 视频链接
            
        Returns:
            视频 ID 或 None
        """
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/v/([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def parse_duration(self, duration_str: str) -> int:
        """
        解析 ISO 8601 时长格式 (如 PT1H2M30S)
        
        Args:
            duration_str: ISO 8601 格式时长
            
        Returns:
            秒数
        """
        if not duration_str:
            return 0
        
        try:
            # 移除 PT 前缀
            duration_str = duration_str.replace('PT', '')
            
            hours = 0
            minutes = 0
            seconds = 0
            
            # 解析小时
            if 'H' in duration_str:
                hours_match = re.search(r'(\d+)H', duration_str)
                if hours_match:
                    hours = int(hours_match.group(1))
            
            # 解析分钟
            if 'M' in duration_str:
                minutes_match = re.search(r'(\d+)M', duration_str)
                if minutes_match:
                    minutes = int(minutes_match.group(1))
            
            # 解析秒
            if 'S' in duration_str:
                seconds_match = re.search(r'(\d+)S', duration_str)
                if seconds_match:
                    seconds = int(seconds_match.group(1))
            
            return hours * 3600 + minutes * 60 + seconds
        except Exception as e:
            logger.error(f"解析时长失败: {duration_str}, {e}")
            return 0
    
    def format_duration(self, seconds: int) -> str:
        """
        格式化时长为可读字符串
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化后的时长字符串 (如 01:23:45)
        """
        if not seconds:
            return "00:00"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def format_view_count(self, view_count: int) -> str:
        """
        格式化观看次数
        
        Args:
            view_count: 观看次数
            
        Returns:
            格式化后的字符串
        """
        if not view_count:
            return "0"
        
        if view_count >= 1000000:
            return f"{view_count/1000000:.1f}M"
        elif view_count >= 1000:
            return f"{view_count/1000:.1f}K"
        else:
            return str(view_count)
    
    async def get_video_details(self, video_id: str) -> Optional[Dict]:
        """
        通过 API 获取视频详细信息
        
        Args:
            video_id: YouTube 视频 ID
            
        Returns:
            视频信息字典或 None
        """
        if not self.enabled:
            return None
        
        try:
            url = f"{self.base_url}/videos"
            params = {
                "part": "snippet,contentDetails,statistics",
                "id": video_id,
                "key": self.api_key
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error(f"YouTube API 请求失败: {response.status_code}")
                    return None
                
                data = response.json()
                
                if not data.get("items"):
                    logger.warning(f"未找到视频: {video_id}")
                    return None
                
                item = data["items"][0]
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                statistics = item.get("statistics", {})
                
                # 解析时长
                duration_iso = content_details.get("duration", "")
                duration_seconds = self.parse_duration(duration_iso)
                
                # 获取最佳缩略图
                thumbnails = snippet.get("thumbnails", {})
                thumbnail_url = (
                    thumbnails.get("maxres", {}).get("url") or
                    thumbnails.get("standard", {}).get("url") or
                    thumbnails.get("high", {}).get("url") or
                    thumbnails.get("medium", {}).get("url") or
                    ""
                )
                
                # 构建统一格式的视频信息
                video_info = {
                    "title": snippet.get("title", "Unknown Title"),
                    "duration": duration_seconds,
                    "duration_string": self.format_duration(duration_seconds),
                    "description": snippet.get("description", "")[:500] + "..." if snippet.get("description", "") else "",
                    "uploader": snippet.get("channelTitle", "Unknown"),
                    "upload_date": snippet.get("publishedAt", "")[:10].replace("-", ""),  # 转换为 YYYYMMDD
                    "view_count": int(statistics.get("viewCount", 0)),
                    "view_count_string": self.format_view_count(int(statistics.get("viewCount", 0))),
                    "thumbnail": thumbnail_url,
                    "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
                    "extractor": "youtube",
                    "embed_url": f"https://www.youtube.com/embed/{video_id}",
                    "source": "youtube_api"  # 标记数据来源
                }
                
                logger.info(f"✅ YouTube API 获取成功: {video_info['title']}")
                return video_info
                
        except httpx.TimeoutException:
            logger.warning(f"YouTube API 请求超时: {video_id}")
            return None
        except Exception as e:
            logger.error(f"YouTube API 请求异常: {e}")
            return None
    
    async def get_video_info_from_url(self, url: str) -> Optional[Dict]:
        """
        从 URL 获取视频信息
        
        Args:
            url: YouTube 视频链接
            
        Returns:
            视频信息字典或 None
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            return None
        
        return await self.get_video_details(video_id)
