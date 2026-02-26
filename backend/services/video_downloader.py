"""
视频下载服务
使用yt-dlp下载视频并转换为音频，支持字幕提取
"""
import os
import re
import yt_dlp
import logging
import asyncio
import subprocess
import shlex
import uuid
from pathlib import Path
from typing import Tuple, Optional, List

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
            # YouTube 403 修复：使用 android_vr 客户端绕过限制 (fix #4 #5)
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_vr', 'web']
                }
            },
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

    async def extract_subtitles(
        self,
        url: str,
        output_dir: Optional[Path] = None,
        preferred_langs: Optional[List[str]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        从视频中提取字幕（优先人工字幕，其次AI/自动字幕）

        支持 YouTube、Bilibili 等平台。B站字幕以 ai-zh/ai-en 等形式
        存在于 subtitles 字段中，且数据直接内嵌在 info['subtitles'] 的 data 字段。

        Args:
            url: 视频URL
            output_dir: 输出目录
            preferred_langs: 优先语言列表，如 ['zh', 'en', 'ja']

        Returns:
            (字幕文本, 视频标题) — 如果无字幕则字幕文本为 None
        """
        if output_dir is None:
            output_dir = settings.TEMP_DIR

        output_dir.mkdir(exist_ok=True)

        if preferred_langs is None:
            preferred_langs = ['zh-Hans', 'zh-Hant', 'zh', 'en', 'ja', 'ko']

        try:
            # 第一步：获取视频信息，检查可用字幕
            # 注意：必须启用 writesubtitles/writeautomaticsub，否则 yt-dlp 不会拉取字幕信息
            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'allsubtitles': True,
                'noplaylist': True,  # 合集只取单个视频，避免遍历所有分P导致卡死
            }
            
            cookies_file = self._get_cookies_for_url(url)
            if cookies_file:
                info_opts['cookiefile'] = cookies_file

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, False)

            manual_subs = info.get('subtitles') or {}
            auto_subs = info.get('automatic_captions') or {}
            video_title = info.get('title', 'unknown')

            # 选择最佳字幕：优先人工字幕
            chosen_lang, is_auto, sub_source_dict = self._choose_best_subtitle(
                manual_subs, auto_subs, preferred_langs
            )

            if not chosen_lang:
                logger.info(f"视频 '{video_title}' 无可用字幕")
                return None, video_title

            sub_source = "AI生成" if chosen_lang.startswith('ai-') else ("自动生成" if is_auto else "人工")
            logger.info(f"📄 找到{sub_source}字幕: {chosen_lang}")

            # 第二步：尝试从 info 内嵌数据中直接读取字幕（B站等平台）
            subtitle_text = self._try_extract_inline_subtitle(sub_source_dict, chosen_lang)
            
            if not subtitle_text:
                # 内嵌数据不可用，通过下载字幕文件获取
                unique_id = str(uuid.uuid4())[:8]
                sub_output = str(output_dir / f"sub_{unique_id}")

                sub_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'skip_download': True,
                    'writesubtitles': not is_auto,
                    'writeautomaticsub': is_auto,
                    'subtitleslangs': [chosen_lang],
                    'subtitlesformat': 'srt/vtt/ass/best',
                    'outtmpl': sub_output,
                    'noplaylist': True,
                }
                
                if cookies_file:
                    sub_opts['cookiefile'] = cookies_file

                with yt_dlp.YoutubeDL(sub_opts) as ydl:
                    await asyncio.to_thread(ydl.download, [url])

                # 查找下载的字幕文件
                sub_file = self._find_subtitle_file(output_dir, f"sub_{unique_id}")
                if not sub_file:
                    logger.warning("字幕下载后未找到文件")
                    return None

                subtitle_text = self._parse_subtitle_file(sub_file)

                # 清理字幕文件
                try:
                    os.remove(sub_file)
                except Exception:
                    pass

            if not subtitle_text or len(subtitle_text.strip()) < 10:
                logger.warning("字幕内容为空或过短")
                return None, video_title

            logger.info(f"✅ 字幕提取成功（{sub_source}，{chosen_lang}），共 {len(subtitle_text)} 字符")
            return subtitle_text, video_title

        except Exception as e:
            logger.warning(f"字幕提取失败: {e}")
            return None, None

    def _try_extract_inline_subtitle(self, source_dict: dict, lang: str) -> Optional[str]:
        """
        尝试从 yt-dlp info 中直接读取内嵌字幕数据
        
        B站等平台的字幕数据直接存在 subtitles[lang][0]['data'] 中，
        无需额外下载。
        """
        try:
            formats = source_dict.get(lang)
            if not formats:
                return None
            
            for fmt in formats:
                data = fmt.get('data')
                if data and isinstance(data, str) and len(data) > 10:
                    ext = fmt.get('ext', 'srt')
                    logger.info(f"📄 从内嵌数据读取字幕（{ext}格式，{len(data)} 字符）")
                    
                    if ext == 'srt':
                        return self._parse_srt(data)
                    elif ext == 'vtt':
                        return self._parse_vtt(data)
                    elif ext == 'ass' or ext == 'ssa':
                        return self._parse_ass(data)
                    else:
                        # 尝试自动检测
                        if 'WEBVTT' in data[:50]:
                            return self._parse_vtt(data)
                        else:
                            return self._parse_srt(data)
            
            return None
        except Exception as e:
            logger.warning(f"读取内嵌字幕数据失败: {e}")
            return None

    def _choose_best_subtitle(
        self,
        manual_subs: dict,
        auto_subs: dict,
        preferred_langs: List[str],
    ) -> Tuple[Optional[str], bool, dict]:
        """
        选择最佳字幕语言
        
        支持标准语言码（zh, en）和带前缀的语言码（ai-zh, ai-en 等B站格式）
        
        Returns:
            (语言代码, 是否为自动字幕, 来源字典)
        """
        # 排除弹幕（danmaku）
        filtered_manual = {k: v for k, v in manual_subs.items() if k != 'danmaku'}
        
        def _match_lang(available_langs: dict, lang: str) -> Optional[str]:
            """在可用语言中查找匹配项"""
            # 精确匹配
            if lang in available_langs:
                return lang
            # 前缀匹配: zh 匹配 zh-Hans, zh-Hant 等
            for avail in available_langs:
                if avail.startswith(lang) or avail.startswith(f'{lang}-'):
                    return avail
            # AI前缀匹配: zh 匹配 ai-zh（B站格式）
            ai_key = f'ai-{lang}'
            if ai_key in available_langs:
                return ai_key
            # AI前缀模糊匹配: zh 匹配 ai-zh-Hans 等
            for avail in available_langs:
                if avail.startswith(ai_key):
                    return avail
            return None
        
        # 优先从人工字幕中查找（排除 ai- 前缀的，那些是AI生成的）
        real_manual = {k: v for k, v in filtered_manual.items() if not k.startswith('ai-')}
        for lang in preferred_langs:
            found = _match_lang(real_manual, lang)
            if found:
                return found, False, filtered_manual

        # 其次从人工字幕中查找AI生成的（B站 ai-zh 等在 subtitles 中）
        ai_manual = {k: v for k, v in filtered_manual.items() if k.startswith('ai-')}
        for lang in preferred_langs:
            found = _match_lang(ai_manual, lang)
            if found:
                return found, False, filtered_manual

        # 再从自动字幕（automatic_captions）中查找
        for lang in preferred_langs:
            found = _match_lang(auto_subs, lang)
            if found:
                return found, True, auto_subs

        # 最后，如果有任何人工字幕（非弹幕），取第一个
        if filtered_manual:
            first_lang = next(iter(filtered_manual))
            return first_lang, False, filtered_manual

        # 如果有任何自动字幕，取第一个
        if auto_subs:
            first_lang = next(iter(auto_subs))
            return first_lang, True, auto_subs

        return None, False, {}

    def _find_subtitle_file(self, directory: Path, prefix: str) -> Optional[str]:
        """查找字幕文件"""
        sub_extensions = ['.srt', '.vtt', '.ass', '.ssa', '.sub', '.json3']
        for f in directory.iterdir():
            if f.stem.startswith(prefix) or prefix in f.stem:
                if f.suffix.lower() in sub_extensions:
                    return str(f)
        # 更宽泛的匹配
        for f in directory.iterdir():
            if prefix in f.name and f.is_file():
                return str(f)
        return None

    def _parse_subtitle_file(self, filepath: str) -> Optional[str]:
        """
        解析字幕文件为带时间戳的文本
        
        支持 SRT、VTT 格式
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
            except Exception:
                return None

        ext = Path(filepath).suffix.lower()

        if ext == '.srt':
            return self._parse_srt(content)
        elif ext == '.vtt':
            return self._parse_vtt(content)
        elif ext == '.ass' or ext == '.ssa':
            return self._parse_ass(content)
        else:
            # 尝试自动检测格式
            if 'WEBVTT' in content[:50]:
                return self._parse_vtt(content)
            elif re.search(r'\d+\s*\n\d{2}:\d{2}:\d{2}', content[:200]):
                return self._parse_srt(content)
            else:
                return self._parse_srt(content)

    def _parse_srt(self, content: str) -> str:
        """解析 SRT 字幕"""
        segments = []
        # SRT 格式: 序号\n时间-->时间\n文本\n\n
        pattern = re.compile(
            r'(\d+)\s*\n'
            r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n'
            r'((?:(?!\n\n|\d+\s*\n\d{2}:\d{2}:\d{2}).)+)',
            re.DOTALL
        )
        
        for match in pattern.finditer(content):
            start_str = match.group(2).replace(',', '.')
            end_str = match.group(3).replace(',', '.')
            text = match.group(4).strip()
            # 去除 HTML 标签
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('\n', ' ').strip()
            if text:
                start_sec = self._timestamp_to_seconds(start_str)
                end_sec = self._timestamp_to_seconds(end_str)
                segments.append((start_sec, end_sec, text))

        return self._merge_and_format_segments(segments)

    def _parse_vtt(self, content: str) -> str:
        """解析 VTT 字幕"""
        segments = []
        # 移除 VTT 头部
        content = re.sub(r'^WEBVTT.*?\n\n', '', content, flags=re.DOTALL)
        # 移除样式块
        content = re.sub(r'STYLE\s*\n.*?\n\n', '', content, flags=re.DOTALL)
        # 移除 NOTE 块
        content = re.sub(r'NOTE\s*\n.*?\n\n', '', content, flags=re.DOTALL)

        pattern = re.compile(
            r'(?:\d+\s*\n)?'  # 可选的序号
            r'(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*'
            r'(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})'
            r'(?:\s+[^\n]*)?\s*\n'  # 可选的位置信息
            r'((?:(?!\n\n|\d{2}:\d{2}).)+)',
            re.DOTALL
        )

        for match in pattern.finditer(content):
            start_str = match.group(1)
            end_str = match.group(2)
            text = match.group(3).strip()
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('\n', ' ').strip()
            if text:
                start_sec = self._timestamp_to_seconds(start_str)
                end_sec = self._timestamp_to_seconds(end_str)
                segments.append((start_sec, end_sec, text))

        return self._merge_and_format_segments(segments)

    def _parse_ass(self, content: str) -> str:
        """解析 ASS/SSA 字幕"""
        segments = []
        # 匹配 Dialogue 行
        pattern = re.compile(
            r'Dialogue:\s*\d+,'
            r'(\d+:\d{2}:\d{2}\.\d{2}),'
            r'(\d+:\d{2}:\d{2}\.\d{2}),'
            r'[^,]*,[^,]*,\d+,\d+,\d+,[^,]*,'
            r'(.*?)$',
            re.MULTILINE
        )

        for match in pattern.finditer(content):
            start_str = match.group(1)
            end_str = match.group(2)
            text = match.group(3).strip()
            # 去除 ASS 样式标签
            text = re.sub(r'\{[^}]+\}', '', text)
            text = text.replace('\\N', ' ').replace('\\n', ' ')
            text = text.strip()
            if text:
                start_sec = self._timestamp_to_seconds(start_str)
                end_sec = self._timestamp_to_seconds(end_str)
                segments.append((start_sec, end_sec, text))

        segments.sort(key=lambda x: x[0])
        return self._merge_and_format_segments(segments)

    def _timestamp_to_seconds(self, timestamp: str) -> float:
        """将时间戳字符串转换为秒数"""
        try:
            parts = timestamp.replace(',', '.').split(':')
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
            elif len(parts) == 2:
                m, s = parts
                return int(m) * 60 + float(s)
            else:
                return float(parts[0])
        except (ValueError, IndexError):
            return 0.0

    def _merge_and_format_segments(self, segments: list) -> str:
        """
        合并相邻的重复/近似字幕段，并格式化为 Markdown
        
        字幕通常每行很短且有大量重叠，需要去重合并
        """
        if not segments:
            return ""

        # 去重：移除完全相同的连续文本
        deduped = []
        prev_text = ""
        for start, end, text in segments:
            if text != prev_text:
                deduped.append((start, end, text))
                prev_text = text

        # 按时间段合并相邻文本（每30秒为一段）
        merged = []
        current_start = deduped[0][0] if deduped else 0
        current_end = deduped[0][1] if deduped else 0
        current_texts = []
        merge_interval = 30.0  # 每30秒合并为一段

        for start, end, text in deduped:
            if start - current_start > merge_interval and current_texts:
                merged.append((current_start, current_end, ' '.join(current_texts)))
                current_start = start
                current_texts = []
            current_end = end
            current_texts.append(text)

        if current_texts:
            merged.append((current_start, current_end, ' '.join(current_texts)))

        # 格式化为 Markdown
        lines = []
        for start, end, text in merged:
            start_fmt = self._format_time_display(start)
            end_fmt = self._format_time_display(end)
            lines.append(f"**{start_fmt} - {end_fmt}**  ")
            lines.append(text)
            lines.append("")

        return '\n'.join(lines)

    def _format_time_display(self, seconds: float) -> str:
        """将秒数格式化为 HH:MM:SS 或 MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

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
