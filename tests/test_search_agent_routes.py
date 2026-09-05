"""Public Agent API contracts with fake tools and an isolated session database."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agent_runtime.harness import AgentCleanupError
from backend.db import connection, schema
from backend.routers import search_agent as routes
from backend.services import search_session_repository as sessions
from backend.services.video_search_agent import VideoSearchAgent


def sse_events(response):
    return [json.loads(line.removeprefix('data: '))
            for line in response.text.splitlines() if line.startswith('data: ')]


class FakeAgent:
    def __init__(self):
        self.is_available = Mock(return_value=True)
        self.clear_conversation = AsyncMock()
        self.get_conversation = AsyncMock(return_value={
            'session_id': 'browser-session', 'messages': [], 'videos': [], 'updated_at': None,
        })
        self.chat_calls = []
        self.note_calls = []
        self.chat_events = [{'type': 'text_chunk', 'content': '找到视频。'}, {'type': 'done'}]
        self.note_events = [{'type': 'progress', 'progress': 50, 'message': '处理中'},
                            {'type': 'notes_complete', 'data': {'summary': 'Fixture note'}}]
        self.chat_error = None

    async def process_message(self, message, session_id):
        self.chat_calls.append((message, session_id))
        for event in self.chat_events:
            yield event
        if self.chat_error is not None:
            raise self.chat_error

    async def generate_notes_for_video(self, **kwargs):
        self.note_calls.append(kwargs)
        for event in self.note_events:
            yield event


class SearchAgentRouteTests(unittest.TestCase):
    def setUp(self):
        self.agent = FakeAgent()
        get_agent = patch.object(routes, 'get_video_search_agent', return_value=self.agent)
        get_agent.start()
        self.addCleanup(get_agent.stop)
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_post_routes_reject_malformed_json_and_non_object_bodies(self):
        endpoints = ['/api/search-agent-chat', '/api/search-agent-clear-session',
                     '/api/search-agent-generate-notes']
        for endpoint in endpoints:
            for raw in ('{invalid', '[]', 'null', '"message"', '42', 'true'):
                with self.subTest(endpoint=endpoint, raw=raw):
                    response = self.client.post(endpoint, content=raw, headers={'Content-Type': 'application/json'})
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json()['detail'], '请求必须是 JSON 对象')
        self.assertEqual(self.agent.chat_calls, [])
        self.assertEqual(self.agent.note_calls, [])
        self.agent.clear_conversation.assert_not_awaited()

    def test_chat_rejects_invalid_empty_and_oversized_messages(self):
        for message in (None, True, 1, [], {}, '', ' \n ', '文' * 8001):
            with self.subTest(message_type=type(message).__name__):
                response = self.client.post('/api/search-agent-chat', json={'message': message})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.agent.chat_calls, [])
        self.agent.is_available.assert_not_called()

    def test_chat_and_clear_reject_invalid_session_identifiers(self):
        for endpoint in ('/api/search-agent-chat', '/api/search-agent-clear-session'):
            for session_id in (None, True, 1, [], {}, '', 'a' * 129, '../path', 'a b', '中文', 'x\n'):
                with self.subTest(endpoint=endpoint, session_id=session_id):
                    response = self.client.post(endpoint, json={'message': '找视频', 'session_id': session_id})
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json()['detail'], '会话标识格式不正确')
        self.assertEqual(self.agent.chat_calls, [])
        self.agent.clear_conversation.assert_not_awaited()

    def test_missing_llm_returns_503_without_opening_a_stream(self):
        self.agent.is_available.return_value = False
        response = self.client.post('/api/search-agent-chat', json={'message': '找视频'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail'], 'AI服务暂时不可用，请稍后重试')
        self.assertEqual(self.agent.chat_calls, [])

    def test_chat_stream_keeps_existing_event_shapes_headers_and_unicode(self):
        self.agent.chat_events = [
            {'type': 'text_chunk', 'content': '找到一个视频。'},
            {'type': 'video_list', 'data': {'videos': [{'title': 'Python 入门', 'url': 'https://www.youtube.com/watch?v=fixture'}]}},
            {'type': 'done'},
        ]
        response = self.client.post('/api/search-agent-chat', json={
            'message': '  找 Python 视频  ', 'session_id': 'browser-session',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['content-type'].startswith('text/event-stream'))
        self.assertEqual(response.headers['cache-control'], 'no-cache')
        self.assertEqual(response.headers['connection'], 'keep-alive')
        self.assertEqual(sse_events(response), self.agent.chat_events)
        self.assertIn('Python 入门', response.text)
        self.assertEqual(self.agent.chat_calls, [('找 Python 视频', 'browser-session')])

    def test_chat_accepts_message_boundary_and_default_session(self):
        response = self.client.post('/api/search-agent-chat', json={'message': '文' * 8000})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.agent.chat_calls, [('文' * 8000, 'default')])

    def test_stream_failure_is_a_safe_sse_error_not_an_upstream_trace(self):
        marker = 'synthetic-private-provider-detail'
        self.agent.chat_events = [{'type': 'text_chunk', 'content': '正在搜索'}]
        self.agent.chat_error = RuntimeError(marker)
        with self.assertLogs(routes.logger, level='WARNING') as logs:
            response = self.client.post('/api/search-agent-chat', json={'message': '找视频'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sse_events(response), [
            {'type': 'text_chunk', 'content': '正在搜索'},
            {'type': 'error', 'content': '搜索对话失败，请重试'},
        ])
        self.assertNotIn(marker, response.text + str(logs.output))

    def test_clear_awaits_completion_before_returning_success(self):
        order = []

        async def clear(session_id):
            order.append(('started', session_id))
            await asyncio.sleep(0)
            order.append(('finished', session_id))

        self.agent.clear_conversation.side_effect = clear
        response = self.client.post('/api/search-agent-clear-session', json={'session_id': 'browser-session'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'message': '会话已清空', 'session_id': 'browser-session'})
        self.agent.clear_conversation.assert_awaited_once_with('browser-session')
        self.assertEqual(order, [('started', 'browser-session'), ('finished', 'browser-session')])

    def test_clear_cleanup_failure_returns_503_with_safe_detail(self):
        marker = 'synthetic-private-cleanup-detail'
        self.agent.clear_conversation.side_effect = AgentCleanupError(marker)
        response = self.client.post('/api/search-agent-clear-session', json={'session_id': 'browser-session'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail'], '会话清理未完成，请重启服务后重试')
        self.assertNotIn(marker, response.text)

    def test_overlapping_clear_request_returns_409_and_first_request_completes(self):
        started, release = threading.Event(), threading.Event()
        clearing = False

        async def clear(_session_id):
            nonlocal clearing
            if clearing:
                raise ValueError('synthetic-private-conflict-detail')
            clearing = True
            started.set()
            try:
                await asyncio.to_thread(release.wait, 5)
            finally:
                clearing = False

        self.agent.clear_conversation.side_effect = clear
        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(self.client.post, '/api/search-agent-clear-session', json={'session_id': 'browser-session'})
            try:
                self.assertTrue(started.wait(3))
                second = self.client.post('/api/search-agent-clear-session', json={'session_id': 'browser-session'})
                self.assertEqual(second.status_code, 409)
                self.assertEqual(second.json()['detail'], '会话正在清空，请稍后重试')
                self.assertFalse(first.done())
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3).status_code, 200)

    def test_notes_route_rejects_invalid_url_and_language_types(self):
        for video_url in (None, True, 1, [], {}, '', ' \n ', 'x' * 4097):
            with self.subTest(video_url_type=type(video_url).__name__):
                response = self.client.post('/api/search-agent-generate-notes', json={'video_url': video_url})
                self.assertEqual(response.status_code, 400)
        for language in (None, True, 1, [], {}, 'a' * 17):
            with self.subTest(language=language):
                response = self.client.post('/api/search-agent-generate-notes', json={
                    'video_url': 'https://www.youtube.com/watch?v=fixture', 'summary_language': language,
                })
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.agent.note_calls, [])

    def test_notes_stream_keeps_generation_id_and_progress_contract(self):
        response = self.client.post('/api/search-agent-generate-notes', json={
            'video_url': '  https://www.youtube.com/watch?v=fixture  ', 'summary_language': 'en',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['content-type'].startswith('text/event-stream'))
        events = sse_events(response)
        self.assertEqual(events[0]['type'], 'generation_id')
        self.assertEqual(UUID(events[0]['generation_id']).version, 4)
        self.assertEqual(events[1:], self.agent.note_events)
        self.assertEqual(len(self.agent.note_calls), 1)
        self.assertEqual(self.agent.note_calls[0], {
            'video_url': 'https://www.youtube.com/watch?v=fixture',
            'temp_dir': routes.TEMP_DIR, 'summary_language': 'en',
            'generation_id': events[0]['generation_id'],
        })

    def test_session_read_rejects_invalid_identifier_before_calling_agent(self):
        for session_id in ('a b', '中文', 'a' * 129):
            with self.subTest(session_id=session_id):
                response = self.client.get('/api/search-agent-session/' + session_id)
                self.assertEqual(response.status_code, 400)
        self.agent.get_conversation.assert_not_awaited()

    def test_session_read_uses_real_sqlite_projection_without_runtime_or_config(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(connection, 'DB_PATH', root / 'sessions.db'), patch.object(
                schema, 'DB_PATH', root / 'sessions.db',
            ), patch.object(schema, 'TEMP_DIR', root):
                asyncio.run(schema.init_db())
                record = asyncio.run(sessions.save('browser-session', [
                    {'role': 'system', 'content': 'synthetic-system-marker'},
                    {'role': 'user', 'content': '搜索视频', 'api_key': 'example-key'},
                    {'role': 'assistant', 'content': '找到一个视频', 'config': {'private': True}},
                ], [{'title': 'Fixture video', 'url': 'https://www.youtube.com/watch?v=fixture',
                     'platform': 'youtube', 'config': {'api_key': 'example-key'}}], search_state={
                    'query': 'synthetic-internal-state-marker', 'platform': 'youtube', 'page': 2, 'max_results': 5,
                }))

                async def actual_get(session_id):
                    return await VideoSearchAgent.get_conversation(None, session_id)

                self.agent.get_conversation.side_effect = actual_get
                response = self.client.get('/api/search-agent-session/browser-session')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(set(response.json()), {'session_id', 'messages', 'videos', 'updated_at'})
                self.assertEqual(response.json()['messages'], [
                    {'role': 'user', 'content': '搜索视频'}, {'role': 'assistant', 'content': '找到一个视频'},
                ])
                self.assertEqual(response.json()['videos'], [{
                    'title': 'Fixture video', 'url': 'https://www.youtube.com/watch?v=fixture', 'platform': 'youtube',
                }])
                for marker in ('runtime_session_id', record['runtime_session_id'], 'config', 'api_key',
                               'synthetic-system-marker', 'example-key', 'synthetic-internal-state-marker'):
                    self.assertNotIn(marker, response.text)
                missing = self.client.get('/api/search-agent-session/missing-session')
                self.assertEqual(missing.json(), {'session_id': 'missing-session', 'messages': [], 'videos': [], 'updated_at': None})


if __name__ == '__main__':
    unittest.main()
