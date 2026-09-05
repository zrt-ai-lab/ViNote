"""Regression coverage for real-download defaults and subtitle fallback contracts."""
from pathlib import Path
from importlib.metadata import version
import os
import sysconfig
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from backend.services.video_downloader import VideoDownloader


class VideoDownloadDefaultsTests(unittest.IsolatedAsyncioTestCase):
    def test_youtube_runtime_dependencies_are_declared_and_installed(self):
        project = (Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text()
        self.assertIn('yt-dlp[default,deno]', project)
        self.assertTrue(version('yt-dlp-ejs'))
        self.assertTrue(version('deno'))

    def test_audio_download_uses_upstream_client_selection(self):
        options = VideoDownloader().base_ydl_opts
        self.assertNotIn('extractor_args', options)
        self.assertEqual(options['format'], 'bestaudio/best')
        self.assertTrue(options['noplaylist'])
        self.assertEqual(options['postprocessors'][0]['key'], 'FFmpegExtractAudio')

    def test_sdk_finds_managed_deno_without_host_path(self):
        from yt_dlp import YoutubeDL
        with patch.dict(os.environ, {'PATH': ''}):
            with YoutubeDL({'quiet': True, 'no_warnings': True}) as client:
                info = client._js_runtimes['deno'].info
        expected = Path(sysconfig.get_path('scripts')) / ('deno' + sysconfig.get_config_var('EXE'))
        self.assertIsNotNone(info)
        self.assertTrue(info.supported)
        self.assertEqual(Path(info.path).resolve(), expected.resolve())

    async def test_download_passes_default_clients_and_keeps_audio_contract(self):
        with TemporaryDirectory() as directory:
            calls = []
            class Client:
                def __init__(self, options):
                    self.options = options
                    calls.append(options)
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def extract_info(self, url, download):
                    return {'title': 'Public sample', 'duration': 19}
                def download(self, urls):
                    Path(self.options['outtmpl'].replace('%(ext)s', 'm4a')).write_bytes(b'fixture-audio')
            async def verify(path, *args):
                return path
            downloader = VideoDownloader()
            with patch('backend.services.video_downloader.yt_dlp.YoutubeDL', Client), patch.object(
                downloader, '_get_cookies_for_url', return_value=None,
            ), patch.object(downloader, '_verify_and_fix_audio', AsyncMock(side_effect=verify)):
                path, title = await downloader.download_video_audio('https://www.youtube.com/watch?v=fixture', Path(directory))
            self.assertEqual(title, 'Public sample')
            self.assertEqual(Path(path).read_bytes(), b'fixture-audio')
            self.assertNotIn('extractor_args', calls[0])
            self.assertNotIn('cookiefile', calls[0])

            cookie_path = str(Path(directory) / 'fixture-cookies.txt')
            with patch('backend.services.video_downloader.yt_dlp.YoutubeDL', Client), patch.object(
                downloader, '_get_cookies_for_url', return_value=cookie_path,
            ), patch.object(downloader, '_verify_and_fix_audio', AsyncMock(side_effect=verify)):
                await downloader.download_video_audio('https://www.bilibili.com/video/fixture', Path(directory))
            self.assertEqual(calls[-1]['cookiefile'], cookie_path)
            self.assertNotIn('extractor_args', calls[-1])

    async def test_missing_subtitle_file_returns_pair_for_audio_fallback(self):
        with TemporaryDirectory() as directory:
            calls = []
            class Client:
                def __init__(self, options):
                    calls.append(options)
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def extract_info(self, url, download):
                    return {'title': 'Public sample', 'subtitles': {'en': [{'ext': 'vtt', 'url': 'https://example.com/sub.vtt'}]}}
                def download(self, urls):
                    return 0
            downloader = VideoDownloader()
            with patch('backend.services.video_downloader.yt_dlp.YoutubeDL', Client), patch.object(
                downloader, '_get_cookies_for_url', return_value=None,
            ):
                result = await downloader.extract_subtitles('https://www.youtube.com/watch?v=fixture', Path(directory))
            self.assertEqual(result, (None, 'Public sample'))
            self.assertTrue(all('cookiefile' not in options for options in calls))

            cookie_path = str(Path(directory) / 'fixture-cookies.txt')
            calls.clear()
            with patch('backend.services.video_downloader.yt_dlp.YoutubeDL', Client), patch.object(
                downloader, '_get_cookies_for_url', return_value=cookie_path,
            ):
                result = await downloader.extract_subtitles('https://www.bilibili.com/video/fixture', Path(directory))
            self.assertEqual(result, (None, 'Public sample'))
            self.assertTrue(calls)
            self.assertTrue(all(options.get('cookiefile') == cookie_path for options in calls))


if __name__ == '__main__':
    unittest.main()
