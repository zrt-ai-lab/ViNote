"""
视频下载服务
使用yt-dlp下载视频并转换为音频
"""
import os
import yt_dlp
import logging
import asyncio
import subprocess
import shlex
import uuid
from pathlib import Path
from typing import Tuple, Dict, Optional

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VideoDownloader:
    """视频下载服务"""

    def __init__(self):
        """初始化yt-dlp配置"""
        # 获取cookies文件路径（项目根目录）
        self.project_root = Path(__file__).parent.parent.parent
        self.bilibili_cookies = self.project_root / "bilibili_cookies.txt"
        
        # 基础配置（不含 cookies）- 移除可能导致YouTube问题的http_headers
        self.base_ydl_opts = {
            'format': 'bestaudio/best',  # 优先下载最佳音频源
            'outtmpl': '%(title)s.%(ext)s',
            'retries': 10,  # 增加重试次数
            'fragment_retries': 10,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                # 直接在提取阶段转换为单声道 16k（空间小且稳定）
                'preferredcodec': 'm4a',
                'preferredquality': '192'
            }],
            # 全局FFmpeg参数：单声道 + 16k 采样率 + faststart
            'postprocessor_args': ['-ac', '1', '-ar', '16000', '-movflags', '+faststart'],
            'prefer_ffmpeg': True,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,  # 强制只下载单个视频，不下载播放列表
        }
    
    def _get_cookies_for_url(self, url: str) -> str:
        """根据 URL 获取对应的 cookies 文件路径"""
        # 仅B站使用 cookies，YouTube 不使用（避免认证问题）
        if 'bilibili.com' in url or 'b23.tv' in url:
            if self.bilibili_cookies.exists():
                logger.info(f"使用 B站 cookies: {self.bilibili_cookies}")
                return str(self.bilibili_cookies)
        
        return None

    async def download_video_audio(
        self,
        url: str,
        output_dir: Optional[Path] = None
    ) -> Tuple[str, str]:
        """
        下载视频并转换为音频格式

        Args:
            url: 视频URL
            output_dir: 输出目录，默认使用配置的TEMP_DIR

        Returns:
            (音频文件路径, 视频标题)

        Raises:
            Exception: 下载或转换失败
        """
        if output_dir is None:
            output_dir = settings.TEMP_DIR

        try:
            # 创建输出目录
            output_dir.mkdir(exist_ok=True)

            # 生成唯一的文件名
            unique_id = str(uuid.uuid4())[:8]
            output_template = str(output_dir / f"audio_{unique_id}.%(ext)s")

            # 更新yt-dlp选项
            ydl_opts = self.base_ydl_opts.copy()
            ydl_opts['outtmpl'] = output_template
            
            # 根据 URL 选择对应的 cookies
            cookies_file = self._get_cookies_for_url(url)
            if cookies_file:
                ydl_opts['cookiefile'] = cookies_file

            logger.info(f"📥 开始提取音频: {url[:60]}...")

            # 在线程池中执行yt-dlp操作（避免阻塞事件循环）
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 获取视频信息
                info = await asyncio.to_thread(ydl.extract_info, url, False)
                video_title = info.get('title', 'unknown')
                expected_duration = info.get('duration') or 0
                logger.info(f"🎬 视频标题: {video_title}")

                # 下载视频
                await asyncio.to_thread(ydl.download, [url])

            # 查找生成的m4a文件
            audio_file = str(output_dir / f"audio_{unique_id}.m4a")

            if not os.path.exists(audio_file):
                # 如果m4a文件不存在，查找其他音频格式
                for ext in ['webm', 'mp4', 'mp3', 'wav']:
                    potential_file = str(output_dir / f"audio_{unique_id}.{ext}")
                    if os.path.exists(potential_file):
                        audio_file = potential_file
                        break
                else:
                    raise Exception("未找到下载的音频文件")

            # 校验时长，如果和源视频差异较大，尝试一次ffmpeg规范化重封装
            audio_file = await self._verify_and_fix_audio(
                audio_file,
                expected_duration,
                output_dir,
                unique_id
            )

            logger.info(f"✅ 音频提取完成")
            return audio_file, video_title

        except Exception as e:
            logger.error(f"❌ 音频提取失败: {str(e)}")
            raise Exception(f"音频提取失败: {str(e)}")

    async def _verify_and_fix_audio(
        self,
        audio_file: str,
        expected_duration: float,
        output_dir: Path,
        unique_id: str
    ) -> str:
        """
        验证并修复音频文件时长

        Args:
            audio_file: 音频文件路径
            expected_duration: 期望时长（秒）
            output_dir: 输出目录
            unique_id: 唯一标识

        Returns:
            音频文件路径（可能是修复后的新文件）
        """
        try:
            # 获取实际时长
            probe_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(audio_file)}"
            out = subprocess.check_output(probe_cmd, shell=True).decode().strip()
            actual_duration = float(out) if out else 0.0
        except Exception:
            actual_duration = 0.0

        # 检查时长差异
        if expected_duration and actual_duration and abs(actual_duration - expected_duration) / expected_duration > 0.1:
            logger.warning(
                f"音频时长异常，期望{expected_duration}s，实际{actual_duration}s，尝试重封装修复…"
            )
            try:
                fixed_path = str(output_dir / f"audio_{unique_id}_fixed.m4a")
                fix_cmd = f"ffmpeg -y -i {shlex.quote(audio_file)} -vn -c:a aac -b:a 160k -movflags +faststart {shlex.quote(fixed_path)}"
                subprocess.check_call(fix_cmd, shell=True)

                # 用修复后的文件替换
                audio_file = fixed_path

                # 重新探测
                out2 = subprocess.check_output(
                    probe_cmd.replace(shlex.quote(audio_file.rsplit('.', 1)[0] + '.m4a'), shlex.quote(audio_file)),
                    shell=True
                ).decode().strip()
                actual_duration2 = float(out2) if out2 else 0.0
                logger.info(f"重封装完成，新时长≈{actual_duration2:.2f}s")
            except Exception as e:
                logger.error(f"重封装失败：{e}")

        return audio_file

    def get_video_info(self, url: str) -> Dict[str, any]:
        """
        获取视频信息（同步方法，用于预览）

        Args:
            url: 视频URL

        Returns:
            视频信息字典

        Raises:
            Exception: 获取信息失败
        """
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'upload_date': info.get('upload_date', ''),
                    'description': info.get('description', ''),
                    'view_count': info.get('view_count', 0),
                    'thumbnail': info.get('thumbnail', ''),
                }
        except Exception as e:
            logger.error(f"获取视频信息失败: {str(e)}")
            raise Exception(f"获取视频信息失败: {str(e)}")
