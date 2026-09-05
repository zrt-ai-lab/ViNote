/** Business-only tools for the DeepSeek Harness subprocess. */
export const name = 'vinote-business-tools';
export const inject = ['tools'];

const TOOL_NAMES = ['generate_notes', 'video_search'];
const MAX_RESPONSE_BYTES = 512 * 1024;

function positiveInteger(value, fallback, ceiling) {
  const number = Number(value ?? fallback);
  if (!Number.isSafeInteger(number) || number <= 0 || number > ceiling) {
    throw new Error('Invalid ViNote agent limit configuration');
  }
  return number;
}

function bridgeConfiguration(env) {
  const url = new URL(env.VINOTE_AGENT_BRIDGE_URL ?? '');
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port
      || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('ViNote agent bridge must use a loopback HTTP origin');
  }
  const token = env.VINOTE_AGENT_BRIDGE_TOKEN;
  if (typeof token !== 'string' || token.length < 32 || /[\r\n]/.test(token)) {
    throw new Error('ViNote agent bridge authentication is not configured');
  }
  return {origin: url.origin, token};
}

async function readResult(response) {
  if (!response.body) throw new Error('ViNote business tool returned an empty response');
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) throw new Error('ViNote business tool result is too large');
      chunks.push(value);
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const result = JSON.parse(new TextDecoder().decode(bytes));
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    throw new Error('ViNote business tool returned an invalid result');
  }
  return result;
}

function validateArguments(tool, args) {
  if (!args || typeof args !== 'object' || Array.isArray(args)) {
    throw new Error('Business tool arguments must be an object');
  }
  const keys = tool === 'video_search' ? ['query', 'platform', 'page', 'max_results'] : ['video_index'];
  if (Object.keys(args).some(key => !keys.includes(key))) {
    throw new Error('Unsupported business tool argument');
  }
  if (tool === 'video_search') {
    if (typeof args.query !== 'string' || !args.query.trim() || args.query.length > 200) {
      throw new Error('Search query must contain between 1 and 200 characters');
    }
    if (args.platform !== undefined && !['youtube', 'bilibili', 'all'].includes(args.platform)) {
      throw new Error('Invalid search platform');
    }
    if (args.page !== undefined && (!Number.isSafeInteger(args.page) || args.page < 1 || args.page > 10)) {
      throw new Error('Search page must be between 1 and 10');
    }
    if (args.max_results !== undefined && (!Number.isSafeInteger(args.max_results) || args.max_results < 1 || args.max_results > 20)) {
      throw new Error('Search result count must be between 1 and 20');
    }
  } else if (!Number.isSafeInteger(args.video_index) || args.video_index < 0) {
    throw new Error('Video index must be a non-negative integer');
  }
}

export function apply(ctx) {
  const bridge = bridgeConfiguration(process.env);
  const maxSteps = positiveInteger(process.env.VINOTE_AGENT_MAX_STEPS, 8, 32);
  const toolTimeout = positiveInteger(process.env.VINOTE_AGENT_TOOL_TIMEOUT_MS, 600000, 3600000);

  async function invoke(tool, args, exec) {
    validateArguments(tool, args);
    const sessionId = exec.agent?.session?.id;
    if (sessionId === undefined) throw new Error('Business tools require an owning session');
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), toolTimeout);
    try {
      const response = await fetch(`${bridge.origin}/tools/${tool}`, {
        method: 'POST',
        redirect: 'error',
        headers: {'Content-Type': 'application/json', Authorization: `Bearer ${bridge.token}`},
        body: JSON.stringify({session_id: String(sessionId), arguments: args}),
        signal: AbortSignal.any([exec.signal, timeout.signal]),
      });
      if (!response.ok) {
        await response.body?.cancel();
        throw new Error(`ViNote business tool failed (HTTP ${response.status})`);
      }
      return await readResult(response);
    } catch (error) {
      if (exec.signal.aborted) throw new Error('ViNote business tool cancelled');
      if (timeout.signal.aborted) throw new Error('ViNote business tool timed out');
      // Keep local addresses and transport diagnostics out of model history.
      if (error instanceof Error && error.message.startsWith('ViNote business tool')) throw error;
      throw new Error('ViNote business tool is unavailable');
    } finally {
      clearTimeout(timer);
    }
  }

  const output = {
    schema: {type: 'object', additionalProperties: true},
    render: (_args, value) => [{type: 'text', text: JSON.stringify(value)}],
  };
  ctx.tools.register({
    name: 'video_search',
    description: 'Search videos on YouTube, Bilibili, or both (all). Use page+1 for more results; return at most max_results videos per platform.',
    parameters: {
      type: 'object',
      properties: {
        query: {type: 'string', description: 'Search keywords, between 1 and 200 characters.'},
        platform: {type: 'string', enum: ['youtube', 'bilibili', 'all'], description: 'Video platform; all searches both supported platforms.'},
        page: {type: 'integer', description: '1-based result page, between 1 and 10; defaults to 1.'},
        max_results: {type: 'integer', description: 'Result count per platform, between 1 and 20; defaults to 5.'},
      },
      required: ['query'],
      additionalProperties: false,
    },
    output,
    execute: (args, exec) => invoke('video_search', args, exec),
  });
  ctx.tools.register({
    name: 'generate_notes',
    description: 'Generate real notes for one previously returned video. Requires a prior successful search; never invent a result.',
    parameters: {
      type: 'object',
      properties: {video_index: {type: 'integer', description: '0-based index in the current session video list.'}},
      required: ['video_index'],
      additionalProperties: false,
    },
    output,
    execute: (args, exec) => invoke('generate_notes', args, exec),
  });

  ctx.on('agent/pre-step', async (payload, next) => {
    const names = ctx.tools.schemas(payload.agent).map(tool => tool.name).sort();
    if (names.length !== TOOL_NAMES.length || names.some((tool, index) => tool !== TOOL_NAMES[index])) {
      throw new Error('ViNote agent has an unexpected tool configuration');
    }
    if (payload.step > maxSteps) throw new Error('AGENT_STEP_LIMIT');
    return next();
  });
}
