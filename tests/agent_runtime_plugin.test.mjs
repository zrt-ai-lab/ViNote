import assert from 'node:assert/strict';
import test from 'node:test';
import {apply} from '../backend/agent_runtime/plugin/index.mjs';

process.env.VINOTE_AGENT_BRIDGE_URL = 'http://127.0.0.1:45678';
process.env.VINOTE_AGENT_BRIDGE_TOKEN = 'p'.repeat(32);
process.env.VINOTE_AGENT_MAX_STEPS = '2';
process.env.VINOTE_AGENT_TOOL_TIMEOUT_MS = '20';

function mount() {
  const tools = new Map();
  const hooks = new Map();
  apply({tools: {register(tool) { tools.set(tool.name, tool); }, schemas() { return [...tools.values()]; }}, on(name, cb) { hooks.set(name, cb); }});
  return {tools, hooks};
}
const execution = () => ({agent: {session: {id: 'trusted-session-id'}}, signal: new AbortController().signal});

test('registers exactly the two business tools', () => assert.deepEqual([...mount().tools.keys()], ['video_search', 'generate_notes']));

test('uses the runtime session identity and authenticated fixed bridge', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:45678/tools/video_search');
    assert.equal(options.headers.Authorization, 'Bearer ' + 'p'.repeat(32));
    assert.equal(options.redirect, 'error');
    assert.deepEqual(JSON.parse(options.body), {session_id: 'trusted-session-id', arguments: {query: 'video', platform: 'all', page: 2, max_results: 5}});
    return Response.json({success: true, results: []});
  };
  assert.deepEqual(await mount().tools.get('video_search').execute({query: 'video', platform: 'all', page: 2, max_results: 5}, execution()), {success: true, results: []});
});

test('rejects injected session, invalid index and out-of-range searches', async () => {
  const {tools} = mount();
  for (const args of [{query: 'video', session_id: 'attacker'}, {query: 'video', page: 0}, {query: 'video', page: 11}, {query: 'video', max_results: 21}, {query: 'video', platform: 'vimeo'}, {query: ''}, {query: 'a'.repeat(201)}]) {
    await assert.rejects(tools.get('video_search').execute(args, execution()));
  }
  await assert.rejects(tools.get('generate_notes').execute({video_index: -1}, execution()));
});

test('hard step gate stops before another model call', async () => {
  const hook = mount().hooks.get('agent/pre-step');
  assert.equal(await hook({step: 2, agent: {}}, async () => 42), 42);
  await assert.rejects(hook({step: 3, agent: {}}, () => assert.fail('must not continue')), /AGENT_STEP_LIMIT/);
});

test('unexpected tools fail closed', async () => {
  const {tools, hooks} = mount();
  tools.set('bash', {name: 'bash'});
  await assert.rejects(hooks.get('agent/pre-step')({step: 1, agent: {}}, () => assert.fail('must not continue')), /unexpected tool/);
});

test('tool timeout aborts and sanitizes transport errors', async () => {
  globalThis.fetch = (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('private endpoint'))));
  await assert.rejects(mount().tools.get('video_search').execute({query: 'video'}, execution()), /ViNote business tool timed out/);
});

test('caller cancellation aborts the bridge request', async () => {
  globalThis.fetch = (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('private detail'))));
  const controller = new AbortController();
  const pending = mount().tools.get('video_search').execute({query: 'video'}, {...execution(), signal: controller.signal});
  controller.abort();
  await assert.rejects(pending, /ViNote business tool cancelled/);
});

test('non-loopback bridge endpoints are rejected', () => {
  process.env.VINOTE_AGENT_BRIDGE_URL = 'http://example.com:45678';
  try {
    assert.throws(mount, /loopback/);
  } finally {
    process.env.VINOTE_AGENT_BRIDGE_URL = 'http://127.0.0.1:45678';
  }
});
