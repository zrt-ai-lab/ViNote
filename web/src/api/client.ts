const BASE = '';

export async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
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
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
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

export function deleteAPI(path: string): Promise<void> {
  return fetch(`${BASE}${path}`, { method: 'DELETE' }).then((res) => {
    if (!res.ok) throw new Error(`Delete failed (${res.status})`);
  });
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
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error((err as { detail?: string }).detail || `Stream failed (${res.status})`);
      }
      const reader = res.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = '';
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            onLine(JSON.parse(line.slice(6)));
          } catch {
            /* skip */
          }
        }
      }
      onDone?.();
    })
    .catch((err: unknown) => {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      onError?.(err instanceof Error ? err : new Error(String(err)));
    });
  return controller;
}

export function createSSE(
  path: string,
  onMessage: (data: unknown) => void,
  onError?: () => void,
): EventSource {
  const es = new EventSource(`${BASE}${path}`);
  es.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      /* skip */
    }
  };
  es.onerror = () => {
    onError?.();
    es.close();
  };
  return es;
}

export function downloadFile(filename: string) {
  const a = document.createElement('a');
  a.href = `/api/download/${encodeURIComponent(filename)}`;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
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
