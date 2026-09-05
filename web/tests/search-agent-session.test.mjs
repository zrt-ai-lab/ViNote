import assert from 'node:assert/strict';
import test from 'node:test';
import { loadTypeScript } from './load-typescript.mjs';

const { getSearchSessionId, restoreSearchMessages, createSessionGuard, groupSearchVideos, updateSearchMessage, getNoteWarnings } = await loadTypeScript('../src/pages/searchAgentSession.ts');

test('search session IDs survive remounts and storage contains only the opaque ID', () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const first = getSearchSessionId(storage);
  assert.match(first, /^[A-Za-z0-9_-]{1,128}$/);
  assert.equal(getSearchSessionId(storage), first);
  assert.deepEqual([...values.values()], [first]);
});

test('invalid stored IDs and unavailable storage do not block search', () => {
  const writes = [];
  const invalid = { getItem: () => '../../private', setItem: (_key, value) => writes.push(value) };
  const valid = getSearchSessionId(invalid);
  assert.match(valid, /^[A-Za-z0-9_-]{1,128}$/);
  assert.deepEqual(writes, [valid]);
  const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.match(getSearchSessionId(blocked), /^[A-Za-z0-9_-]{1,128}$/);
});

test('history restoration preserves roles and attaches last videos only once', () => {
  const videos = [{ title: 'Bilibili', url: 'https://example.com/1', platform: 'bilibili' },
    { title: 'YouTube', url: 'https://example.com/2', platform: 'youtube' }];
  const session = { session_id: 'fixture', updated_at: '2026-09-05T01:02:03Z', messages: [
    { role: 'user', content: 'Find videos' }, { role: 'assistant', content: 'Found videos' },
    { role: 'user', content: 'More please' },
  ], videos };
  const restored = restoreSearchMessages(session);
  assert.equal(restored.length, 3);
  assert.deepEqual(restored.map(({ role, content }) => ({ role, content })), session.messages);
  assert.equal(restored.filter((message) => message.allVideos).length, 1);
  assert.deepEqual(restored[1].allVideos, videos);
  assert.deepEqual(Object.keys(restored[1].videosByPlatform), ['bilibili', 'youtube']);
  assert.equal(restored[1].timestamp.toISOString(), '2026-09-05T01:02:03.000Z');
});

test('an empty session remains empty and videos without text still render', () => {
  assert.deepEqual(restoreSearchMessages({ messages: [], videos: [] }), []);
  const videos = [{ title: 'Video', url: 'https://example.com/1' }];
  const restored = restoreSearchMessages({ messages: [], videos });
  assert.equal(restored.length, 1);
  assert.equal(restored[0].role, 'assistant');
  assert.equal(restored[0].content, '');
  assert.deepEqual(restored[0].videosByPlatform.unknown, videos);
});

test('session invalidation rejects old restoration and stream callbacks but allows new work', () => {
  const guard = createSessionGuard();
  const oldRequest = guard.capture();
  assert.equal(oldRequest(), true);
  guard.invalidate();
  const newRequest = guard.capture();
  assert.equal(oldRequest(), false);
  assert.equal(newRequest(), true);
  guard.invalidate();
  assert.equal(newRequest(), false);
});

test('concurrent note and chat streams only update their own assistant message', () => {
  const messages = [
    { id: 'user', role: 'user', content: 'Search' },
    { id: 'note-one', role: 'assistant', content: '' },
    { id: 'note-two', role: 'assistant', content: '' },
    { id: 'chat', role: 'assistant', content: '' },
  ];
  const current = createSessionGuard().capture();
  let updated = updateSearchMessage(messages, 'note-one', (message) => ({ ...message, progress: 30, generationId: 'gen-one' }), current);
  updated = updateSearchMessage(updated, 'note-two', (message) => ({ ...message, notesResult: { summary: 'Second note' }, generationId: 'gen-two' }), current);
  updated = updateSearchMessage(updated, 'chat', (message) => ({ ...message, content: 'Chat answer' }), current);
  assert.equal(updated[1].progress, 30);
  assert.equal(updated[1].generationId, 'gen-one');
  assert.equal(updated[1].notesResult, undefined);
  assert.equal(updated[1].content, '');
  assert.equal(updated[2].notesResult.summary, 'Second note');
  assert.equal(updated[2].progress, undefined);
  assert.equal(updated[2].generationId, 'gen-two');
  assert.equal(updated[3].content, 'Chat answer');
  assert.equal(updated[3].notesResult, undefined);
  assert.equal(messages[1].progress, undefined);
  assert.equal(updateSearchMessage(updated, 'user', () => assert.fail('user message changed'), current), updated);
});

test('queued updates cannot repopulate a cleared session or mutate a newer session', () => {
  const guard = createSessionGuard();
  const oldRequest = guard.capture();
  const cleared = [];
  guard.invalidate();
  assert.equal(updateSearchMessage(cleared, 'old', () => assert.fail('cleared message recreated'), oldRequest), cleared);
  const newer = [{ id: 'old', role: 'assistant', content: 'new session' }];
  assert.equal(updateSearchMessage(newer, 'old', () => assert.fail('new session changed'), oldRequest), newer);
  assert.equal(updateSearchMessage(newer, 'missing', () => assert.fail('missing message created'), guard.capture()), newer);
});

test('a later empty video list removes earlier cards from the same response', () => {
  const videos = [{ title: 'Old video', url: 'https://example.com/1', platform: 'youtube' }];
  const messages = [{ id: 'chat', role: 'assistant', allVideos: videos, videosByPlatform: groupSearchVideos(videos) }];
  const updated = updateSearchMessage(messages, 'chat', (message) => ({
    ...message, allVideos: [], videosByPlatform: groupSearchVideos([]),
  }), createSessionGuard().capture());
  assert.deepEqual(updated[0].allVideos, []);
  assert.deepEqual(Object.keys(updated[0].videosByPlatform), []);
  assert.equal(messages[0].allVideos.length, 1);
});

test('note warnings distinguish generated files from failed library persistence', () => {
  assert.equal(getNoteWarnings({ persisted: true }), '');
  assert.equal(getNoteWarnings({}), '');
  const text = getNoteWarnings({ persisted: false, warnings: ['摘要使用降级结果', '摘要使用降级结果'] });
  assert.match(text, /文件已生成，但未保存到笔记库/);
  assert.equal(text.split('摘要使用降级结果').length, 2);
});
