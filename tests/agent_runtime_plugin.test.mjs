import assert from 'node:assert/strict';
import test from 'node:test';
import { apply } from '../backend/agent_runtime/plugin/index.mjs';

process.env.VINOTE_AGENT_BRIDGE_URL = 'http://127.0.0.1:45678';
process.env.VINOTE_AGENT_BRIDGE_TOKEN = 'p'.repeat(32);
process.env.VINOTE_AGENT_MAX_STEPS = '2';
process.env.VINOTE_AGENT_TOOL_TIMEOUT_MS = '20';

function mount() {
  const tools = new Map();
  const hooks = new Map();
  apply({ tools: { register(tool) { tools.set(tool.name, tool); }, schemas() { return [...tools.values()]; } }, on(name, callback) { hooks.set(name, callback); } });
  return { tools, hooks };
}
const execution = () => ({ agent: { session: { id: 'trusted-session-id' } }, signal: new AbortController().signal });

test('registers search and import business tools', () => {
  assert.deepEqual([...mount().tools.keys()], ['import_video', 'video_search']);
});

test('uses the authenticated runtime session bridge', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:45678/tools/video_search');
    assert.equal(options.headers.Authorization, 'Bearer ' + 'p'.repeat(32));
    assert.deepEqual(JSON.parse(options.body), { session_id: 'trusted-session-id', arguments: { query: 'video', platform: 'all', page: 2, max_results: 5 } });
    return Response.json({ success: true, results: [] });
  };
  assert.deepEqual(await mount().tools.get('video_search').execute({ query: 'video', platform: 'all', page: 2, max_results: 5 }, execution()), { success: true, results: [] });
});

test('rejects invalid search arguments and import indexes', async () => {
  const { tools } = mount();
  await assert.rejects(tools.get('video_search').execute({ query: '' }, execution()));
  await assert.rejects(tools.get('video_search').execute({ query: 'video', platform: 'vimeo' }, execution()));
  await assert.rejects(tools.get('import_video').execute({ video_index: -1 }, execution()));
});

test('step gate and unexpected business tools fail closed', async () => {
  const { tools, hooks } = mount();
  assert.equal(await hooks.get('agent/pre-step')({ step: 2, agent: {} }, async () => 42), 42);
  await assert.rejects(hooks.get('agent/pre-step')({ step: 3, agent: {} }, () => assert.fail('must not continue')), /AGENT_STEP_LIMIT/);
  tools.set('bash', { name: 'bash' });
  await assert.rejects(hooks.get('agent/pre-step')({ step: 1, agent: {} }, () => assert.fail('must not continue')), /Unexpected tools/);
});
