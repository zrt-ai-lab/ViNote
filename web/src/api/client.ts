const BASE = '';

export class HttpError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

async function responseError(res: Response, fallback: string): Promise<Error> {
  const payload = await res.json().catch(() => null) as { detail?: string; message?: string } | null;
  return new HttpError(payload?.detail || payload?.message || `${fallback} (${res.status})`, res.status);
}

export async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    throw await responseError(res, '请求失败');
  }
  return res.json() as Promise<T>;
}

export function postFormData<T>(path: string, data: Record<string, string>): Promise<T> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(data)) {
    fd.append(k, v);
  }
  return fetch(`${BASE}${path}`, { method: 'POST', body: fd }).then(async (res) => {
    if (!res.ok) {
      throw await responseError(res, '请求失败');
    }
    return res.json() as Promise<T>;
  });
}

export function postJSON<T>(path: string, body: unknown): Promise<T> {
  return fetchJSON<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deleteAPI(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw await responseError(res, '删除失败');
}

export function streamPost(
  path: string,
  body: unknown,
  onLine: (data: unknown) => void,
  onDone?: () => void,
  onError?: (err: Error) => void,
): AbortController {
  const controller = new AbortController();
  fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        throw await responseError(res, '流式请求失败');
      }
      const reader = res.body?.getReader();
      if (!reader) throw new Error('流式响应不可用');
      const decoder = new TextDecoder();
      let buffer = '';
      const consumeLines = (flush = false) => {
        const lines = buffer.split(/\r?\n/);
        buffer = flush ? '' : (lines.pop() ?? '');
        for (const line of lines) {
          if (controller.signal.aborted) return;
          if (!line.startsWith('data:')) continue;
          const payload = line.slice(5).trimStart();
          if (!payload) continue;
          try {
            onLine(JSON.parse(payload));
          } catch {
            /* ignore malformed server events */
          }
        }
      };
      while (true) {
        const { done, value } = await reader.read();
        if (controller.signal.aborted) return;
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        consumeLines();
      }
      buffer += decoder.decode();
      consumeLines(true);
      if (!controller.signal.aborted) onDone?.();
    })
    .catch((err: unknown) => {
      if (controller.signal.aborted || (err instanceof DOMException && err.name === 'AbortError')) return;
      onError?.(err instanceof Error ? err : new Error(String(err)));
    });
  return controller;
}

export function createSSE(
  path: string,
  onMessage: (data: unknown) => void,
  onError?: () => void,
  onOpen?: () => void,
): EventSource {
  const es = new EventSource(`${BASE}${path}`);
  es.onopen = () => onOpen?.();
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data?.type !== 'heartbeat') onMessage(data);
    } catch {
      /* ignore malformed server events */
    }
  };
  es.onerror = () => {
    onError?.();
    es.close();
  };
  return es;
}

export async function downloadFile(filename: string): Promise<void> {
  const response = await fetch(`/api/download/${encodeURIComponent(filename)}`);
  if (!response.ok) throw await responseError(response, '下载失败');
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export function proxyImageUrl(url: string): string {
  if (!url) return '/product-logo.png';
  if (url.includes('bilibili.com') || url.includes('hdslb.com')) {
    return `/api/proxy-image?url=${encodeURIComponent(url)}`;
  }
  return url;
}

export function extractBilibiliUrl(text: string): string {
  const match = text.match(/https?:\/\/[^\s]+/);
  return match ? match[0] : text;
}
