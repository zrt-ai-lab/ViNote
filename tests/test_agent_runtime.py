"""Offline lifecycle checks, including the real SDK against a local fake LLM."""
import asyncio
import http.client
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.agent_runtime.bridge import ToolBridge
from backend.agent_runtime.harness import AgentCleanupError, AgentRuntimeError, HarnessRuntime

SDK_AVAILABLE = importlib.util.find_spec('deepseek_harness') is not None
MODULE = 'backend.agent_runtime.harness'


def post(bridge, data, *, authorization=None, path='/tools/video_search'):
    connection = http.client.HTTPConnection('127.0.0.1', bridge.server.server_port, timeout=3)
    try:
        connection.request('POST', path, json.dumps(data).encode(), headers={
            'Content-Type': 'application/json',
            'Authorization': authorization if authorization is not None else 'Bearer ' + bridge.token,
        })
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class ToolBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dispatch = AsyncMock(return_value={'success': True})
        self.bridge = ToolBridge('session-fixture', self.dispatch, timeout=1, request_timeout=0.2)

    async def asyncTearDown(self):
        await self.bridge.aclose()
        self.assertFalse(self.bridge.thread.is_alive())
        self.assertFalse(self.bridge.pending)
        self.assertFalse(self.bridge.tasks)
        self.assertFalse(self.bridge.handlers)
        self.assertFalse(self.bridge.connections)

    async def test_authenticated_tool_uses_fixed_session_and_known_tool(self):
        status, result = await asyncio.to_thread(post, self.bridge, {
            'session_id': 'session-fixture', 'arguments': {'query': 'Python'},
        })
        self.assertEqual((status, result), (200, {'success': True}))
        self.dispatch.assert_awaited_once_with('video_search', {'query': 'Python'})

    async def test_non_ascii_auth_wrong_session_and_unknown_tool_are_rejected(self):
        payload = {'session_id': 'session-fixture', 'arguments': {}}
        cases = [
            (payload, {'authorization': 'Bearer caf\xe9'}, 401),
            ({**payload, 'session_id': 'other'}, {}, 400),
            (payload, {'path': '/tools/bash'}, 404),
            ({**payload, 'extra': True}, {}, 400),
            ({**payload, 'arguments': []}, {}, 400),
        ]
        for data, options, expected in cases:
            with self.subTest(options=options):
                status, _ = await asyncio.to_thread(post, self.bridge, data, **options)
                self.assertEqual(status, expected)
        self.dispatch.assert_not_awaited()

    async def test_slow_incomplete_headers_have_a_total_deadline(self):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.bridge.server.server_port)
        try:
            writer.write(b'POST /tools/video_search HTTP/1.1\r\nHost: localhost\r\n')
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), timeout=1), b'')
        finally:
            writer.close()
            await writer.wait_closed()
        self.dispatch.assert_not_awaited()

    async def test_closing_waits_for_actual_dispatch_finally_without_second_cancel(self):
        started = asyncio.Event()
        finalized = asyncio.Event()
        writes = []

        async def dispatch(*_args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.15)
                writes.append('final tool write')
                finalized.set()

        self.bridge.dispatch = dispatch
        request = asyncio.create_task(asyncio.to_thread(post, self.bridge, {
            'session_id': 'session-fixture', 'arguments': {},
        }))
        await asyncio.wait_for(started.wait(), timeout=2)
        await self.bridge.aclose()
        self.assertTrue(finalized.is_set())
        writes.clear()  # Equivalent to clearing the business session after runtime cleanup.
        await asyncio.sleep(0.03)
        self.assertEqual(writes, [])
        await asyncio.gather(request, return_exceptions=True)

    async def test_dispatch_failure_does_not_return_exception_text(self):
        self.bridge.dispatch = AsyncMock(side_effect=RuntimeError('synthetic-private-detail'))
        status, result = await asyncio.to_thread(post, self.bridge, {
            'session_id': 'session-fixture', 'arguments': {},
        })
        self.assertEqual(status, 500)
        self.assertNotIn('synthetic-private-detail', str(result))


@unittest.skipUnless(SDK_AVAILABLE, 'DeepSeek Harness SDK is not installed')
class HarnessLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name) / 'runtime'
        self.config = SimpleNamespace(base_url='http://127.0.0.1:1/v1/chat/completions', api_key='fixture', model='fixture-model')
        self.session_id = str(uuid4())

    async def asyncTearDown(self):
        if self.home.exists():
            self.assertEqual(list(self.home.iterdir()), [])
        self.directory.cleanup()

    async def test_constructor_failure_still_closes_bridge_and_temporary_home(self):
        bridges = []

        def bridge(*args, **kwargs):
            value = ToolBridge(*args, **kwargs)
            bridges.append(value)
            return value

        with patch(MODULE + '.ToolBridge', side_effect=bridge), patch(
            'deepseek_harness.DeepSeekHarness', side_effect=RuntimeError('synthetic-private-detail'),
        ):
            with self.assertRaises(AgentRuntimeError) as failure:
                await HarnessRuntime(self.config, self.home).run('query', self.session_id, AsyncMock(), lambda _: None)
        self.assertNotIn('synthetic-private-detail', str(failure.exception))
        self.assertEqual(len(bridges), 1)
        self.assertFalse(bridges[0].thread.is_alive())

    async def test_system_prompt_and_stream_filter_are_preserved(self):
        events, options = [], []

        class FakeSdk:
            def __init__(_self, **kwargs):
                options.append(kwargs)

            def start_session(_self, session_id):
                def run(_prompt, on_notification):
                    for event_session, data in [
                        ('other', {'chunk': {'type': 'text-delta', 'text': 'hidden'}}),
                        (session_id, None),
                        (session_id, {'chunk': {'type': 'text-delta', 'text': 'answer'}}),
                    ]:
                        on_notification(SimpleNamespace(method='session.event', payload={
                            'sessionId': event_session, 'event': {'type': 'assistant/chunk', 'data': data},
                        }))
                    return SimpleNamespace(finish_reason='completed', final_response='answer')
                return SimpleNamespace(run=run)

            def close(_self):
                pass

        with patch('deepseek_harness.DeepSeekHarness', FakeSdk):
            result = await HarnessRuntime(self.config, self.home, system_prompt='ViNote system fixture').run(
                'query', self.session_id, AsyncMock(), events.append,
            )
        self.assertEqual(result, 'answer')
        self.assertEqual(events, [{'type': 'text_chunk', 'content': 'answer'}])
        self.assertEqual(options[0]['env']['VINOTE_AGENT_SYSTEM_PROMPT'], 'ViNote system fixture')
        self.assertEqual(options[0]['env']['VINOTE_LLM_BASE_URL'], 'http://127.0.0.1:1/v1')

    async def test_close_exception_still_terminates_owned_process(self):
        processes = []

        class BrokenCloseSdk:
            def __init__(_self, **_kwargs):
                _self.client = SimpleNamespace(_proc=None)

            def start_session(_self, _session_id):
                _self.client._proc = subprocess.Popen(
                    [sys.executable, '-c', 'import time; time.sleep(60)'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                processes.append(_self.client._proc)
                return SimpleNamespace(run=lambda *_args, **_kwargs: SimpleNamespace(finish_reason='completed', final_response='ok'))

            def close(_self):
                raise RuntimeError('synthetic-private-shutdown-detail')

        with patch('deepseek_harness.DeepSeekHarness', BrokenCloseSdk):
            result = await HarnessRuntime(self.config, self.home).run('query', self.session_id, AsyncMock(), lambda _: None)
        self.assertEqual(result, 'ok')
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(all(pipe.closed for pipe in (processes[0].stdin, processes[0].stdout, processes[0].stderr)))

    async def test_cleanup_failure_has_distinct_safe_error(self):
        class FakeSdk:
            def __init__(_self, **_kwargs): pass
            def start_session(_self, _session_id):
                return SimpleNamespace(run=lambda *_args, **_kwargs: SimpleNamespace(finish_reason='completed', final_response='ok'))
            def close(_self): pass

        original = ToolBridge.aclose

        async def failing_close(bridge):
            await original(bridge)
            raise RuntimeError('synthetic-private-cleanup-detail')

        with patch('deepseek_harness.DeepSeekHarness', FakeSdk), patch.object(ToolBridge, 'aclose', failing_close):
            with self.assertRaises(AgentCleanupError) as failure:
                await HarnessRuntime(self.config, self.home).run('query', self.session_id, AsyncMock(), lambda _: None)
        self.assertNotIn('synthetic-private-cleanup-detail', str(failure.exception))

    async def test_cancel_during_initialization_cannot_start_a_later_turn(self):
        started, release = threading.Event(), threading.Event()
        processes, turns = [], []

        class InitializingSdk:
            def __init__(_self, **_kwargs):
                _self.client = SimpleNamespace(_proc=None)

            def start_session(_self, _session_id):
                started.set()
                release.wait(3)
                _self.client._proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
                processes.append(_self.client._proc)

                def run(*_args, **_kwargs):
                    turns.append('unexpected turn')
                    return SimpleNamespace(finish_reason='completed', final_response='unexpected')
                return SimpleNamespace(run=run)

            def close(_self):
                if _self.client._proc is not None:
                    _self.client._proc.terminate()
                    _self.client._proc.wait(timeout=2)

        with patch('deepseek_harness.DeepSeekHarness', InitializingSdk):
            task = asyncio.create_task(HarnessRuntime(self.config, self.home).run(
                'query', self.session_id, AsyncMock(), lambda _: None,
            ))
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            await asyncio.sleep(0)
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(turns, [])
        self.assertTrue(processes)
        self.assertIsNotNone(processes[0].poll())


@unittest.skipUnless(SDK_AVAILABLE, 'DeepSeek Harness SDK is not installed')
class RealSdkOfflineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from deepseek_harness import DeepSeekHarness

        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name) / 'runtime'
        self.session_id = str(uuid4())
        self.processes, self.requests, self.sdk_clients = [], [], []
        self.request_started = threading.Event()
        self.release_response = threading.Event()
        self.mode = 'normal'
        owner = self

        class TrackingSdk(DeepSeekHarness):
            def __init__(sdk, **kwargs):
                super().__init__(**kwargs)
                owner.sdk_clients.append(sdk.client)
                original_start = sdk.client.start

                def start():
                    original_start()
                    process = sdk.client._proc
                    if process is not None and process not in owner.processes:
                        owner.processes.append(process)

                sdk.client.start = start

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append(data)
                owner.request_started.set()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                if owner.mode == 'stall':
                    owner.release_response.wait(10)
                    return
                has_result = any(message.get('role') == 'tool' for message in data['messages'])
                if not has_result or owner.mode == 'loop':
                    delta = {'tool_calls': [{'index': 0, 'id': 'fixture-tool-call', 'type': 'function', 'function': {
                        'name': 'video_search', 'arguments': '{"query":"Python","platform":"youtube"}',
                    }}]}
                    reason = 'tool_calls'
                else:
                    delta, reason = {'content': 'Found a matching video.'}, 'stop'
                try:
                    for delta_value, finish in [(delta, None), ({}, reason)]:
                        frame = {'id': 'fixture-response', 'object': 'chat.completion.chunk', 'created': 1,
                                 'model': 'fixture-model', 'choices': [{'index': 0, 'delta': delta_value, 'finish_reason': finish}]}
                        self.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n')
                except OSError:
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = SimpleNamespace(base_url=f'http://127.0.0.1:{self.server.server_port}/v1', api_key='example-key', model='fixture-model')
        self.sdk_patch = patch('deepseek_harness.DeepSeekHarness', TrackingSdk)
        self.sdk_patch.start()

    async def asyncTearDown(self):
        self.sdk_patch.stop()
        self.release_response.set()
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
        self.thread.join(timeout=2)
        for process in self.processes:
            self.assertIsNotNone(process.poll(), f'SDK process {process.pid} remains alive')
            for name in ('stdin', 'stdout', 'stderr'):
                pipe = getattr(process, name)
                self.assertIsNotNone(pipe)
                self.assertTrue(pipe.closed, f'SDK process {process.pid} left {name} open')
        for client in self.sdk_clients:
            for name in ('_reader_thread', '_stderr_thread'):
                reader = getattr(client, name, None)
                if reader is not None:
                    self.assertFalse(reader.is_alive(), f'SDK {name} remains alive')
        if self.home.exists():
            self.assertEqual(list(self.home.iterdir()), [])
        self.directory.cleanup()

    async def test_real_sdk_runs_tool_then_summary_with_exact_tool_allowlist(self):
        dispatch = AsyncMock(return_value={'success': True, 'results': [{'title': 'Python video', 'index': 0}]})
        events = []
        result = await HarnessRuntime(self.config, self.home, timeout=15, system_prompt='ViNote test system prompt').run(
            'Find Python videos.', self.session_id, dispatch, events.append,
        )
        self.assertEqual(result, 'Found a matching video.')
        self.assertEqual(len(self.requests), 2)
        dispatch.assert_awaited_once_with('video_search', {'query': 'Python', 'platform': 'youtube'})
        self.assertIn({'type': 'text_chunk', 'content': result}, events)
        for request in self.requests:
            self.assertEqual(sorted(tool['function']['name'] for tool in request['tools']), ['generate_notes', 'video_search'])
            self.assertEqual(request['messages'][0]['content'], 'ViNote test system prompt')

    async def test_real_sdk_step_limit_stops_endless_model_tool_calls(self):
        self.mode = 'loop'
        with self.assertRaises(AgentRuntimeError):
            await HarnessRuntime(self.config, self.home, timeout=15, max_steps=2).run(
                'Find videos.', self.session_id, AsyncMock(return_value={'success': True}), lambda _: None,
            )
        self.assertEqual(len(self.requests), 2)

    async def test_real_sdk_initialization_failure_still_closes_captured_pipes(self):
        self.config.model = ''
        with self.assertRaises(AgentRuntimeError):
            await HarnessRuntime(self.config, self.home, timeout=10).run(
                'Find videos.', self.session_id, AsyncMock(), lambda _: None,
            )
        self.assertTrue(self.processes)
        self.assertEqual(self.requests, [])

    async def test_real_sdk_timeout_reaps_process_and_removes_runtime_home(self):
        self.mode = 'stall'
        started = time.monotonic()
        with self.assertRaises(AgentRuntimeError):
            await HarnessRuntime(self.config, self.home, timeout=8).run(
                'Find videos.', self.session_id, AsyncMock(), lambda _: None,
            )
        self.assertTrue(self.request_started.is_set())
        self.assertTrue(self.processes)
        self.assertLess(time.monotonic() - started, 15)

    async def test_real_sdk_double_cancel_waits_for_tool_cleanup_and_reaps_process(self):
        started, finalized = asyncio.Event(), asyncio.Event()
        writes = []

        async def dispatch(*_args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.15)
                writes.append('finalized')
                finalized.set()

        task = asyncio.create_task(HarnessRuntime(self.config, self.home, timeout=15).run(
            'Find videos.', self.session_id, dispatch, lambda _: None,
        ))
        await asyncio.wait_for(started.wait(), timeout=20)
        task.cancel()
        await asyncio.sleep(0.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finalized.is_set())
        writes.clear()
        await asyncio.sleep(0.03)
        self.assertEqual(writes, [])
        self.assertTrue(self.processes)


if __name__ == '__main__':
    unittest.main()
