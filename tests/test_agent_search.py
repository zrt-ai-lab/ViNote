"""Offline SDK business-flow regressions with isolated SQLite and fake tools."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.db import connection, schema
from backend.services import note_search, search_session_repository as sessions
from backend.services import video_search_agent as agent_module
from backend.services.search_providers.local_provider import LocalSearchProvider
from backend.services.search_providers.manager import SearchProviderManager


class DirectSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialization_uses_direct_search_once(self):
        provider = LocalSearchProvider()
        provider.initialize = AsyncMock(return_value=True)
        with patch('backend.services.search_providers.manager.LocalSearchProvider', return_value=provider):
            manager = SearchProviderManager()
            await manager.initialize()
            await manager.initialize()
        provider.initialize.assert_awaited_once()
        self.assertEqual(manager.providers, [provider])

    async def test_missing_search_dependency_is_a_visible_failure(self):
        provider = SimpleNamespace(initialize=AsyncMock(return_value=False))
        with patch('backend.services.search_providers.manager.LocalSearchProvider', return_value=provider):
            result = await SearchProviderManager().execute_search('python')
        self.assertFalse(result['success'])
        self.assertEqual(result['results'], [])
        self.assertTrue(result['error'])

    async def test_manager_deduplicates_results_and_preserves_search_arguments(self):
        provider = LocalSearchProvider()
        video = {'url': 'https://www.youtube.com/watch?v=fixture', 'title': 'Fixture'}
        provider.search = AsyncMock(return_value={'success': True, 'results': [video, video]})
        manager = SearchProviderManager()
        manager.providers = [provider]
        manager._initialized = True
        result = await manager.execute_search('python', platform='youtube', page=2)
        provider.search.assert_awaited_once_with('python', platform='youtube', page=2)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['providers'], ['local'])

    async def test_provider_failure_does_not_expose_internal_error(self):
        provider = LocalSearchProvider()
        provider.search = AsyncMock(side_effect=RuntimeError('internal fixture error'))
        manager = SearchProviderManager()
        manager.providers = [provider]
        manager._initialized = True
        result = await manager.execute_search('python')
        self.assertFalse(result['success'])
        self.assertNotIn('internal fixture error', result['error'])


class AgentSearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for target, name, value in (
            (connection, 'DB_PATH', self.root / 'agent.db'),
            (schema, 'DB_PATH', self.root / 'agent.db'),
            (schema, 'TEMP_DIR', self.root),
            (note_search, 'TEMP_DIR', self.root),
            (agent_module, 'TEMP_DIR', self.root),
        ):
            mocked = patch.object(target, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        config = patch.object(agent_module, 'get_openai_config', return_value=SimpleNamespace(is_configured=True))
        config.start()
        self.addCleanup(config.stop)
        await schema.init_db()
        self.first_video = {'title': 'First lesson', 'url': 'https://www.youtube.com/watch?v=fixture1'}
        self.second_video = {'title': 'Second lesson', 'url': 'https://www.youtube.com/watch?v=fixture2'}
        self.manager = SimpleNamespace(execute_search=AsyncMock(return_value={
            'success': True, 'results': [self.first_video, self.second_video],
        }))
        note_id = '1234567890abcdef1234567890abcdef'
        note_files = {}
        for kind, prefix in (('transcript', 'transcript'), ('summary', 'summary'), ('raw_transcript', 'raw')):
            filename = f'{prefix}_fixture_{note_id}.md'
            (self.root / filename).write_text('Fixture note content', encoding='utf-8')
            note_files[kind + '_filename'] = filename
        self.notes = SimpleNamespace(generate_note=AsyncMock(return_value={
            'short_id': note_id, 'safe_title': 'fixture',
            'video_title': 'Fixture note', 'optimized_transcript': 'Transcript',
            'summary': 'Summary', 'raw_transcript': 'Raw transcript',
            'detected_language': 'en', 'summary_language': 'zh', 'files': note_files,
        }))
        factory = patch.object(agent_module, 'NoteGenerator', return_value=self.notes)
        factory.start()
        self.addCleanup(factory.stop)

    def make_agent(self, run=None):
        runtime = SimpleNamespace(run=AsyncMock(side_effect=run, return_value='已完成。'))
        with patch.object(agent_module, 'HarnessRuntime', return_value=runtime):
            agent = agent_module.VideoSearchAgent(self.manager)
        self.addAsyncCleanup(agent.aclose)
        return agent, runtime

    async def collect(self, agent, message='搜索 Python 视频', session_id='fixture-session'):
        return [event async for event in agent.process_message(message, session_id)]

    async def test_clear_releases_session_even_when_old_stream_is_not_consumed(self):
        async def run(prompt, runtime_id, dispatch, emit):
            emit({'type': 'thinking', 'content': 'working'})
            await asyncio.Event().wait()
        agent, runtime = self.make_agent(run)
        stream = agent.process_message('search', 'paused-stream')
        self.assertEqual((await anext(stream))['type'], 'thinking')
        await agent.clear_conversation('paused-stream')
        self.assertNotIn('paused-stream', agent._turns)
        runtime.run.side_effect = None
        events = await self.collect(agent, 'new request', 'paused-stream')
        self.assertNotIn('error', [event['type'] for event in events])
        await stream.aclose()

    async def test_failed_next_page_keeps_last_successful_search_and_video_indexes(self):
        state = {'query': 'python', 'platform': 'youtube', 'page': 1, 'max_results': 2}
        await sessions.save('fixture-session', [], [self.first_video], search_state=state)
        self.manager.execute_search.return_value = {'success': False, 'error': '平台限制'}
        async def run(prompt, runtime_id, dispatch, emit):
            result = await dispatch('video_search', {**state, 'page': 2})
            self.assertFalse(result['success'])
            self.assertTrue(result['previous_results_retained'])
            self.assertEqual(result['count'], 0)
            return '第 2 页暂时不可用，请重试。'
        agent, _ = self.make_agent(run)
        events = await self.collect(agent, '下一页')
        self.assertNotIn('video_list', [event['type'] for event in events])
        saved = await sessions.get('fixture-session')
        self.assertEqual(saved['search_state'], state)
        self.assertEqual(saved['videos'], [self.first_video])

    async def test_clear_before_worker_starts_does_not_leave_stream_waiting_forever(self):
        agent, runtime = self.make_agent()
        stream = agent.process_message('search', 'early-clear')
        consumer = asyncio.create_task(anext(stream))
        clear = asyncio.create_task(agent.clear_conversation('early-clear'))
        await asyncio.wait_for(clear, timeout=2)
        with self.assertRaises(StopAsyncIteration):
            await asyncio.wait_for(consumer, timeout=2)
        runtime.run.assert_not_awaited()
        self.assertNotIn('early-clear', agent._turns)
        await stream.aclose()

    async def test_incomplete_runtime_cleanup_blocks_clear_and_followup(self):
        agent, _ = self.make_agent(agent_module.AgentCleanupError('cleanup failed'))
        events = await self.collect(agent)
        self.assertIn('error', [event['type'] for event in events])
        with self.assertRaises(agent_module.AgentCleanupError):
            await agent.clear_conversation('fixture-session')
        self.assertTrue((await sessions.get('fixture-session'))['messages'])
        events = await self.collect(agent)
        self.assertEqual(events[0]['type'], 'error')

    async def test_runtime_tool_call_streams_video_results_and_persists_display_history(self):
        calls = []

        async def run(prompt, runtime_id, dispatch, emit):
            calls.append((json.loads(prompt), runtime_id))
            result = await dispatch('video_search', {'query': 'python', 'platform': 'youtube'})
            self.assertEqual(result['count'], 2)
            self.assertEqual([video['index'] for video in result['videos']], [0, 1])
            emit({'type': 'text_chunk', 'content': '找到两个'})
            emit({'type': 'text_chunk', 'content': '视频。'})
            return '找到两个视频。'

        agent, runtime = self.make_agent(run)
        events = await self.collect(agent)
        self.assertNotIn('error', [event['type'] for event in events])
        self.assertEqual(events[-1], {'type': 'done'})
        self.assertEqual(''.join(event['content'] for event in events if event['type'] == 'text_chunk'), '找到两个视频。')
        videos = next(event['data']['videos'] for event in events if event['type'] == 'video_list')
        self.assertEqual([video['title'] for video in videos], ['First lesson', 'Second lesson'])
        record = await sessions.get('fixture-session')
        self.assertEqual(record['videos'], videos)
        self.assertEqual(record['messages'], [{'role': 'user', 'content': '搜索 Python 视频'},
                                               {'role': 'assistant', 'content': '找到两个视频。'}])
        self.assertEqual(calls[0][1], record['runtime_session_id'])
        self.assertEqual(calls[0][0]['current_user_request'], '搜索 Python 视频')
        runtime.run.assert_awaited_once()
        self.manager.execute_search.assert_awaited_once_with('python', platform='youtube', page=1, max_results=5)

    async def test_all_platform_partial_failure_reports_real_failure_and_keeps_successful_videos(self):
        async def search(query, *, platform, page, max_results):
            if platform == 'bilibili':
                return {'success': False, 'error': '平台请求受限，请稍后重试', 'results': []}
            return {'success': True, 'results': [self.first_video]}

        self.manager.execute_search.side_effect = search
        tool_results = []

        async def run(prompt, runtime_id, dispatch, emit):
            result = await dispatch('video_search', {'query': 'python', 'platform': 'all'})
            tool_results.append(result)
            return 'YouTube 找到 1 个视频，B站请求受限。'

        agent, _ = self.make_agent(run)
        events = await self.collect(agent)
        result = tool_results[0]
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['errors'], [{'platform': 'bilibili', 'message': '平台请求受限，请稍后重试'}])
        self.assertTrue(any(event['type'] == 'thinking' and 'bilibili' in event['content']
                            and '请求受限' in event['content'] for event in events))
        self.assertEqual({call.kwargs['platform'] for call in self.manager.execute_search.await_args_list},
                         {'youtube', 'bilibili'})
        self.assertEqual(len((await sessions.get('fixture-session'))['videos']), 1)

    async def test_new_agent_instance_restores_history_search_state_and_current_video_index(self):
        async def search_turn(prompt, runtime_id, dispatch, emit):
            await dispatch('video_search', {'query': 'python', 'platform': 'youtube', 'page': 2, 'max_results': 2})
            return '找到两节课程。'

        first, _ = self.make_agent(search_turn)
        await self.collect(first)
        saved = await sessions.get('fixture-session')
        prompts = []

        async def note_turn(prompt, runtime_id, dispatch, emit):
            context = json.loads(prompt)['conversation_context']
            prompts.append(context)
            self.assertEqual(runtime_id, saved['runtime_session_id'])
            result = await dispatch('generate_notes', {'video_index': 1})
            self.assertTrue(result['success'])
            return '已为第二个视频生成笔记。'

        restored, _ = self.make_agent(note_turn)
        events = await self.collect(restored, '给第二个视频生成笔记')
        self.assertEqual(prompts[0]['last_search'], {'query': 'python', 'platform': 'youtube', 'page': 2, 'max_results': 2})
        self.assertEqual(prompts[0]['messages'], saved['messages'])
        self.assertEqual(prompts[0]['current_videos'][1], {'index': 1, 'title': 'Second lesson', 'platform': 'youtube'})
        self.notes.generate_note.assert_awaited_once()
        self.assertEqual(self.notes.generate_note.await_args.kwargs['video_url'], self.second_video['url'])
        self.manager.execute_search.assert_awaited_once()
        self.assertIn('notes_complete', [event['type'] for event in events])
        self.assertEqual(len((await sessions.get('fixture-session'))['messages']), 4)

    async def test_search_then_generate_notes_in_one_turn_uses_the_replaced_current_list(self):
        await sessions.save('fixture-session', [], [self.second_video], search_state={
            'query': 'old query', 'platform': 'youtube', 'page': 1, 'max_results': 1,
        })
        self.manager.execute_search.return_value = {'success': True, 'results': [self.first_video]}
        dispatch_results = []

        async def run(prompt, runtime_id, dispatch, emit):
            dispatch_results.append(await dispatch('video_search', {
                'query': 'python', 'platform': 'youtube', 'page': 3, 'max_results': 1,
            }))
            dispatch_results.append(await dispatch('generate_notes', {'video_index': 0}))
            return '已搜索并生成第一条笔记。'

        agent, _ = self.make_agent(run)
        events = await self.collect(agent, '搜索 Python 并给第一个视频生成笔记')
        self.assertTrue(all(result['success'] for result in dispatch_results))
        self.assertEqual(self.notes.generate_note.await_args.kwargs['video_url'], self.first_video['url'])
        kinds = [event['type'] for event in events]
        self.assertLess(kinds.index('video_list'), kinds.index('notes_complete'))
        self.assertEqual(kinds[-1], 'done')
        record = await sessions.get('fixture-session')
        self.assertEqual([video['url'] for video in record['videos']], [self.first_video['url']])
        self.assertEqual(record['search_state']['page'], 3)

    async def test_clear_cancels_and_waits_for_active_turn_before_resetting_all_state(self):
        entered, stopped = asyncio.Event(), asyncio.Event()

        async def run(prompt, runtime_id, dispatch, emit):
            await dispatch('video_search', {'query': 'python', 'platform': 'youtube'})
            emit({'type': 'text_chunk', 'content': '正在处理'})
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        agent, _ = self.make_agent(run)
        old = await sessions.get_or_create('fixture-session')
        events = []

        async def consume():
            try:
                async for event in agent.process_message('搜索视频', 'fixture-session'):
                    events.append(event)
            except asyncio.CancelledError:
                pass

        consumer = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            await asyncio.wait_for(agent.clear_conversation('fixture-session'), timeout=2)
            await asyncio.wait_for(consumer, timeout=2)
            self.assertTrue(stopped.is_set())
            record = await sessions.get('fixture-session')
            self.assertNotEqual(record['runtime_session_id'], old['runtime_session_id'])
            self.assertEqual(record['messages'], [])
            self.assertEqual(record['videos'], [])
            self.assertEqual(record['search_state'], {})
            self.assertEqual(agent._turns, {})
            self.assertIn('cancelled', [event['type'] for event in events])
            self.assertEqual(events[-1], {'type': 'done'})
            self.assertEqual((await agent.get_conversation('fixture-session'))['messages'], [])
        finally:
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)

    async def test_invalid_tool_names_platforms_and_indexes_execute_no_business_action(self):
        await sessions.save('fixture-session', [], [self.first_video])
        requests = [
            ('shell', {'command': 'not a supported tool'}),
            ('video_search', {'query': 'python', 'platform': 'private-network'}),
            ('video_search', {'query': 'python', 'platform': ['youtube']}),
            ('video_search', {'query': 'python', 'page': True}),
            ('video_search', {'query': 'python', 'page': 0}),
            ('video_search', {'query': 'python', 'max_results': 21}),
            ('video_search', {'query': 'python', 'arbitrary_url': 'http://127.0.0.1'}),
            ('generate_notes', {'video_index': -1}),
            ('generate_notes', {'video_index': 1}),
            ('generate_notes', {'video_index': True}),
            ('generate_notes', {'video_index': '0'}),
            ('generate_notes', {'video_index': 0, 'video_url': 'http://127.0.0.1'}),
        ]
        results = []

        async def run(prompt, runtime_id, dispatch, emit):
            for name, arguments in requests:
                results.append(await dispatch(name, arguments))
            return '这些操作无法执行。'

        agent, _ = self.make_agent(run)
        events = await self.collect(agent)
        self.assertEqual(len(results), len(requests))
        self.assertTrue(all(result['success'] is False and result['error'] for result in results))
        self.manager.execute_search.assert_not_awaited()
        self.notes.generate_note.assert_not_awaited()
        self.assertNotIn('generation_id', [event['type'] for event in events])
        self.assertNotIn('video_list', [event['type'] for event in events])

    async def test_clear_also_waits_for_inflight_note_generation_to_stop(self):
        entered, stopped = asyncio.Event(), asyncio.Event()
        await sessions.save('fixture-session', [], [self.first_video])

        async def generate_note(**kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        self.notes.generate_note.side_effect = generate_note

        async def run(prompt, runtime_id, dispatch, emit):
            await dispatch('generate_notes', {'video_index': 0})
            return 'unreachable after cancellation'

        agent, _ = self.make_agent(run)

        async def consume():
            try:
                return await self.collect(agent, '生成第一条笔记')
            except asyncio.CancelledError:
                return []

        consumer = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            await asyncio.wait_for(agent.clear_conversation('fixture-session'), timeout=2)
            await asyncio.wait_for(consumer, timeout=2)
            self.assertTrue(stopped.is_set())
            self.assertEqual(agent.active_generation_tasks, {})
            self.assertEqual(agent.generation_cancel_flags, {})
            self.assertEqual((await sessions.get('fixture-session'))['messages'], [])
            self.assertEqual((await sessions.get('fixture-session'))['videos'], [])
        finally:
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)

    async def test_nonplatform_or_credential_urls_never_enter_current_video_indexes(self):
        self.manager.execute_search.return_value = {'success': True, 'results': [
            {'title': 'Local', 'url': 'http://127.0.0.1/private'},
            {'title': 'Userinfo', 'url': 'https://fixture:fixture@www.youtube.com/watch?v=fixture'},
            {'title': 'Unexpected port', 'url': 'https://www.youtube.com:8080/watch?v=fixture'},
            self.first_video,
        ]}

        async def run(prompt, runtime_id, dispatch, emit):
            result = await dispatch('video_search', {'query': 'python', 'platform': 'youtube'})
            self.assertEqual(result['count'], 1)
            self.assertEqual(result['videos'][0]['index'], 0)
            return '找到一个视频。'

        agent, _ = self.make_agent(run)
        await self.collect(agent)
        self.assertEqual([video['url'] for video in (await sessions.get('fixture-session'))['videos']],
                         [self.first_video['url']])

    async def test_user_message_length_and_empty_inputs_are_rejected_before_runtime(self):
        agent, runtime = self.make_agent()
        for message in ('', ' \n ', 'x' * 8001, None, 123):
            with self.subTest(length=len(message) if isinstance(message, str) else None):
                events = await self.collect(agent, message)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]['type'], 'error')
        runtime.run.assert_not_awaited()
        self.assertIsNone(await sessions.get('fixture-session'))
        for index, message in enumerate(('x', 'x' * 8000)):
            events = await self.collect(agent, message, session_id=f'boundary-{index}')
            self.assertEqual(events[-1], {'type': 'done'})
            self.assertEqual((await sessions.get(f'boundary-{index}'))['messages'][0]['content'], message)
        self.assertEqual(runtime.run.await_count, 2)

    async def test_old_runtime_id_cannot_overwrite_a_reset_session(self):
        old = await sessions.get_or_create('stale-turn')
        reset = await sessions.reset('stale-turn')
        with self.assertRaisesRegex(ValueError, 'cleared'):
            await sessions.save('stale-turn', [{'role': 'user', 'content': 'old work'}], [self.first_video],
                                expected_runtime_id=old['runtime_session_id'])
        self.assertEqual(await sessions.get('stale-turn'), reset)
        saved = await sessions.save('stale-turn', [{'role': 'user', 'content': 'new work'}], [],
                                    expected_runtime_id=reset['runtime_session_id'])
        self.assertEqual(saved['messages'][0]['content'], 'new work')

    async def test_search_state_is_whitelisted_persisted_and_cleared(self):
        search_state = {'query': 'python', 'platform': 'all', 'page': 2, 'max_results': 5}
        record = await sessions.save('search-state', [], [], search_state={
            **search_state, 'config': {'credential': 'synthetic marker'}, 'tool_messages': ['internal'],
        })
        self.assertEqual(record['search_state'], search_state)
        self.assertEqual((await sessions.get('search-state'))['search_state'], search_state)
        async with connection.get_db() as db:
            row = await (await db.execute(
                'SELECT search_state_json FROM search_agent_sessions WHERE session_id = ?', ('search-state',),
            )).fetchone()
        self.assertNotIn('synthetic marker', row[0])
        self.assertNotIn('tool_messages', row[0])
        self.assertEqual((await sessions.reset('search-state'))['search_state'], {})


if __name__ == '__main__':
    unittest.main()
