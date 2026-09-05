import assert from 'node:assert/strict';
import test from 'node:test';
import { loadTypeScript } from './load-typescript.mjs';

const { getArtifactFilename, readStoredId, writeStoredId } = await loadTypeScript('../src/utils/taskRecovery.ts');
const { monitorProgress } = await loadTypeScript('../src/api/progress.ts');
const { downloadFile, HttpError, streamPost } = await loadTypeScript('../src/api/client.ts');

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(predicate, timeoutMs = 2000) {
  const deadline = performance.now() + timeoutMs;
  while (!predicate()) {
    assert.ok(performance.now() < deadline, 'expected progress did not arrive before timeout');
    await delay(5);
  }
}

test('downloads prefer returned names and support existing task responses', () => {
  const task = { short_id: 'abc123', safe_title: '示例视频', transcript_filename: 'actual.md' };
  assert.equal(getArtifactFilename(task, 'script'), 'actual.md');
  assert.equal(getArtifactFilename(task, 'summary'), 'summary_示例视频_abc123.md');
  assert.equal(getArtifactFilename({ script_path: '/tmp/legacy.md' }, 'script'), 'legacy.md');
  assert.equal(getArtifactFilename({ transcript_filename: '../secret.md' }, 'script'), '');
});

test('recovery storage holds only validated IDs and tolerates blocked storage', () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
  writeStoredId('task', 'ab12-cd34', storage);
  assert.equal(readStoredId('task', storage), 'ab12-cd34');
  writeStoredId('task', 'https://example.com/private', storage);
  assert.equal(readStoredId('task', storage), null);
  const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };
  assert.equal(readStoredId('task', blocked), null);
  assert.doesNotThrow(() => writeStoredId('task', 'abc123', blocked));
});

test('a download 404 is reported before creating a browser download', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: '文件不存在' }), { status: 404 }));
  await assert.rejects(downloadFile('missing.md'), (error) => error instanceof HttpError && error.status === 404 && error.message === '文件不存在');
});

test('successful downloads use a blob and retain the actual filename', async (t) => {
  let requested;
  let clicked = false;
  const anchor = { click() { clicked = true; } };
  t.mock.method(globalThis, 'fetch', async (url) => { requested = url; return new Response('# 笔记'); });
  t.mock.method(URL, 'createObjectURL', () => 'blob:download-fixture');
  const previousDocument = globalThis.document;
  globalThis.document = { createElement: () => anchor, body: { appendChild() {}, removeChild() {} } };
  try {
    await downloadFile('transcript_示例_ab12.md');
    assert.equal(requested, `/api/download/${encodeURIComponent('transcript_示例_ab12.md')}`);
    assert.equal(anchor.href, 'blob:download-fixture');
    assert.equal(anchor.download, 'transcript_示例_ab12.md');
    assert.equal(clicked, true);
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

test('aborting a chat stream prevents buffered events from altering another conversation', async (t) => {
  let push;
  t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({ start(controller) { push = controller; } })));
  const controller = streamPost('/api/qa/sessions/example/messages/stream', { question: '示例' }, () => assert.fail('aborted stream delivered content'), () => assert.fail('aborted stream completed'));
  await delay(1);
  controller.abort();
  push.enqueue(new TextEncoder().encode('data: {"content":"late"}\n\n'));
  push.close();
  await delay(2);
});

test('chat streams still deliver split unicode and a final event without a newline', async (t) => {
  const bytes = new TextEncoder().encode('data: {"content":"回答"}\r\n\r\ndata: {"done":true}');
  t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(bytes.slice(0, 20));
      controller.enqueue(bytes.slice(20));
      controller.close();
    },
  })));
  const events = [];
  await new Promise((resolve, reject) => streamPost('/api/example', {}, (event) => events.push(event), resolve, reject));
  assert.deepEqual(events, [{ content: '回答' }, { done: true }]);
});

test('a broken stream falls back to polling without inventing a failed task', async (t) => {
  const updates = [];
  const connections = [];
  let disconnect;
  let calls = 0;
  const stop = monitorProgress({
    load: async () => ({ status: ++calls > 1 ? 'completed' : 'processing' }),
    subscribe: (_onUpdate, onError) => { disconnect = onError; return { close() {} }; },
    isTerminal: (data) => data.status === 'completed',
    onUpdate: (data) => updates.push(data.status),
    onConnectionChange: (state) => connections.push(state),
    onUnavailable: () => assert.fail('network interruption is not a missing task'),
    intervalMs: 2,
  });
  t.after(stop);
  await waitFor(() => updates.length === 1 && typeof disconnect === 'function');
  disconnect();
  await waitFor(() => updates.includes('completed'));
  stop();
  assert.deepEqual(updates, ['processing', 'completed']);
  assert.ok(connections.includes('retrying'));
});

test('polls do not overlap and retry transient failures', async (t) => {
  let active = 0;
  let peak = 0;
  let attempts = 0;
  const updates = [];
  const stop = monitorProgress({
    load: async () => {
      peak = Math.max(peak, ++active);
      await delay(20);
      active--;
      if (++attempts === 1) throw new Error('offline');
      return { done: attempts === 3 };
    },
    isTerminal: (data) => data.done,
    onUpdate: (data) => updates.push(data.done),
    onConnectionChange() {},
    onUnavailable: () => assert.fail('transient error'),
    intervalMs: 2,
  });
  t.after(stop);
  await waitFor(() => updates.includes(true));
  stop();
  assert.equal(peak, 1);
  assert.equal(attempts, 3);
  assert.deepEqual(updates, [false, true]);
});

test('missing tasks stop retrying and disposed requests cannot update the page', async () => {
  let missingCalls = 0;
  let unavailable = 0;
  const stopMissing = monitorProgress({
    load: async () => { missingCalls++; throw Object.assign(new Error('任务不存在'), { status: 404 }); },
    isTerminal: () => false,
    onUpdate: () => assert.fail('missing task'),
    onConnectionChange() {},
    onUnavailable: () => unavailable++,
    intervalMs: 1,
  });
  await delay(10);
  stopMissing();
  assert.equal(missingCalls, 1);
  assert.equal(unavailable, 1);

  let finish;
  const stop = monitorProgress({
    load: () => new Promise((resolve) => { finish = resolve; }),
    isTerminal: () => false,
    onUpdate: () => assert.fail('disposed observer updated page'),
    onConnectionChange() {},
    onUnavailable() {},
  });
  stop();
  finish({ status: 'completed' });
  await delay(1);
});
