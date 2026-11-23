import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Check, Clock3, ExternalLink, Loader2, Search, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';
import { proxyImageUrl } from '../api/client';
import type { AgentVideo, ChatMessage } from '../types';
import { getSearchSessionId, restoreSearchMessages } from './searchAgentSession';

type SearchEvent = { type?: string; content?: string; data?: { videos?: AgentVideo[]; asset_id?: string; job_id?: string; title?: string } };
type SessionResponse = { messages?: { role: 'user' | 'assistant'; content: string }[]; videos?: AgentVideo[]; updated_at?: string };
type ImportResult = { asset_id: string; job_id: string; title: string };
type Platform = 'youtube' | 'bilibili' | 'unknown';
const PLATFORM_LABELS: Record<Platform, string> = { youtube: 'YouTube', bilibili: 'Bilibili', unknown: '其他平台' };

function messageId(prefix: string) { return globalThis.crypto?.randomUUID?.() ?? prefix + '-' + Date.now() + '-' + Math.random().toString(36).slice(2); }
function platformOf(video: AgentVideo): Platform { return video.platform === 'youtube' || video.platform === 'bilibili' ? video.platform : 'unknown'; }
function responseError(payload: unknown, fallback: string) { return payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string' ? payload.detail : fallback; }
function platformNotice(content: string) { const match = content.match(/^(youtube|bilibili)\s*[：:]\s*(.+)$/i); return match ? { platform: match[1].toLowerCase() as Platform, message: match[2] } : null; }

export default function SearchAgent() {
  const sessionRef = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const importAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const sessionId = sessionRef.current ?? (sessionRef.current = getSearchSessionId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [videos, setVideos] = useState<AgentVideo[]>([]);
  const [failures, setFailures] = useState<Partial<Record<Platform, string>>>({});
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState('');
  const [importingIndex, setImportingIndex] = useState<number | null>(null);
  const [imported, setImported] = useState<ImportResult | null>(null);

  const updateMessage = useCallback((id: string, update: (message: ChatMessage) => ChatMessage) => {
    setMessages((current) => current.map((message) => message.id === id ? update(message) : message));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/v2/search/sessions/' + encodeURIComponent(sessionId), { signal: controller.signal })
      .then(async (response) => { const payload = await response.json().catch(() => null) as SessionResponse | null; if (!response.ok) throw new Error(responseError(payload, '无法恢复搜索会话')); return payload ?? {}; })
      .then((snapshot) => {
        if (!mountedRef.current) return;
        const restored = restoreSearchMessages({ session_id: sessionId, messages: Array.isArray(snapshot.messages) ? snapshot.messages : [], videos: Array.isArray(snapshot.videos) ? snapshot.videos : [], updated_at: snapshot.updated_at });
        setMessages(restored.map((message) => ({ id: message.id, role: message.role, content: message.content, timestamp: message.timestamp, videos: message.allVideos, videosByPlatform: message.videosByPlatform })));
        setVideos(Array.isArray(snapshot.videos) ? snapshot.videos : []);
      })
      .catch((cause: unknown) => { if (!controller.signal.aborted && mountedRef.current) setError(cause instanceof Error ? cause.message : '无法恢复搜索会话'); })
      .finally(() => { if (mountedRef.current) setRestoring(false); });
    return () => controller.abort();
  }, [sessionId]);

  useEffect(() => () => { mountedRef.current = false; abortRef.current?.abort(); importAbortRef.current?.abort(); }, []);

  const consumeSSE = async (response: Response, assistantId: string, signal: AbortSignal) => {
    if (!response.body) throw new Error('搜索流不可用');
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    const consume = (flush = false) => {
      const lines = buffer.split(/\r?\n/); buffer = flush ? '' : (lines.pop() ?? '');
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim(); if (!raw || raw === '[DONE]') continue;
        let event: SearchEvent; try { event = JSON.parse(raw) as SearchEvent; } catch { continue; }
        if (signal.aborted) return;
        if (event.type === 'text_chunk' && event.content) updateMessage(assistantId, (message) => ({ ...message, content: message.content + event.content, isStreaming: true }));
        else if (event.type === 'video_list') { const next = event.data?.videos ?? []; setVideos(next); setFailures({}); updateMessage(assistantId, (message) => ({ ...message, videos: next, isStreaming: true })); }
        else if (event.type === 'thinking' && event.content) { const notice = platformNotice(event.content); if (notice) setFailures((current) => ({ ...current, [notice.platform]: notice.message })); updateMessage(assistantId, (message) => ({ ...message, thinking: [...(message.thinking ?? []), event.content!] })); }
        else if (event.type === 'asset_imported' && event.data?.asset_id) setImported({ asset_id: event.data.asset_id, job_id: event.data.job_id ?? '', title: event.data.title ?? '搜索结果' });
        else if (event.type === 'error') { setError(event.content || '搜索失败'); updateMessage(assistantId, (message) => ({ ...message, isStreaming: false })); }
        else if (event.type === 'done' || event.type === 'cancelled') updateMessage(assistantId, (message) => ({ ...message, isStreaming: false }));
      }
    };
    while (true) { const { done, value } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); consume(); }
    buffer += decoder.decode(); if (buffer.trim()) consume(true);
  };

  const send = async () => {
    const query = input.trim(); if (!query || busy || restoring) return;
    setInput(''); setError(''); setImported(null); setFailures({}); setBusy(true);
    const assistantId = messageId('assistant'); setMessages((current) => [...current, { id: messageId('user'), role: 'user', content: query, timestamp: new Date() }, { id: assistantId, role: 'assistant', content: '', timestamp: new Date(), isStreaming: true }]);
    const controller = new AbortController(); abortRef.current = controller;
    try {
      const response = await fetch('/api/v2/search/sessions/' + encodeURIComponent(sessionId) + '/messages', { method: 'POST', headers: { 'content-type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify({ message: query }), signal: controller.signal });
      const payload = response.ok ? null : await response.json().catch(() => null); if (!response.ok) throw new Error(responseError(payload, '搜索请求失败'));
      await consumeSSE(response, assistantId, controller.signal);
    } catch (cause: unknown) { if (!controller.signal.aborted && mountedRef.current) { setError(cause instanceof Error ? cause.message : '搜索失败'); updateMessage(assistantId, (message) => ({ ...message, isStreaming: false })); } }
    finally { if (mountedRef.current) setBusy(false); if (abortRef.current === controller) abortRef.current = null; }
  };

  const importVideo = async (videoIndex: number) => {
    if (importingIndex !== null) return;
    setError(''); setImported(null); setImportingIndex(videoIndex); const controller = new AbortController(); importAbortRef.current = controller;
    try {
      const response = await fetch('/api/v2/search/sessions/' + encodeURIComponent(sessionId) + '/import', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ video_index: videoIndex }), signal: controller.signal });
      const payload = await response.json().catch(() => null) as ImportResult | { detail?: string } | null;
      if (!response.ok || !payload || !('asset_id' in payload) || !('job_id' in payload) || !('title' in payload)) throw new Error(responseError(payload, '导入失败，请稍后重试'));
      setImported(payload);
    } catch (cause: unknown) { if (!controller.signal.aborted && mountedRef.current) setError(cause instanceof Error ? cause.message : '导入失败'); }
    finally { if (mountedRef.current) setImportingIndex(null); if (importAbortRef.current === controller) importAbortRef.current = null; }
  };

  const groups = useMemo(() => { const result: Record<Platform, AgentVideo[]> = { youtube: [], bilibili: [], unknown: [] }; videos.forEach((video) => result[platformOf(video)].push(video)); return result; }, [videos]);
  return <div className="mx-auto max-w-6xl space-y-7 px-4 py-8 sm:px-8 sm:py-12">
    <header><p className="text-sm font-medium text-[var(--color-accent)]">ViNote · 搜索工作台</p><h1 className="mt-2 text-3xl font-bold tracking-tight">视频智搜</h1><p className="mt-2 max-w-2xl text-sm text-[var(--color-text-secondary)]">搜索 YouTube 和 Bilibili 视频，查看来源卡片，并把选中的视频导入知识库。</p></header>
    <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm"><div className="min-h-40 space-y-3" aria-live="polite">
      {restoring && <p className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]"><Loader2 size={15} className="animate-spin" />正在恢复会话…</p>}
      {!restoring && messages.length === 0 && <div className="flex min-h-32 flex-col items-center justify-center text-center"><Search size={22} className="text-[var(--color-accent)]" /><p className="mt-2 text-sm text-[var(--color-text-secondary)]">例如：搜索适合初学者的 RAG 教程</p></div>}
      {messages.map((message) => <div key={message.id} className={message.role === 'user' ? 'ml-auto max-w-2xl rounded-xl bg-[var(--color-accent-light)] p-3 text-sm' : 'max-w-3xl rounded-xl bg-[var(--color-bg)] p-3 text-sm'}>{message.content || (message.isStreaming ? <span className="text-[var(--color-text-secondary)]">正在搜索…</span> : '')}{message.isStreaming && message.content && <Loader2 size={13} className="ml-1 inline animate-spin text-[var(--color-text-muted)]" />}</div>)}
    </div><div className="mt-5 flex gap-2"><input value={input} disabled={busy || restoring} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send(); } }} placeholder="告诉我你想搜索什么视频" className="min-w-0 flex-1 rounded-lg border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]" /><button disabled={!input.trim() || busy || restoring} onClick={() => void send()} className="flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm text-white transition hover:bg-[var(--color-accent-hover)] disabled:opacity-50"><Search size={15} />{busy ? '搜索中…' : '发送'}</button></div>{error && <p role="alert" className="mt-3 flex items-center gap-2 text-sm text-[var(--color-error)]"><AlertCircle size={15} />{error}</p>}{imported && <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-[var(--color-success)]"><Check size={15} />已导入「{imported.title}」<Link className="underline" to={'/assets/' + encodeURIComponent(imported.asset_id)}>查看资产</Link></p>}</section>
    <section aria-labelledby="search-results"><div className="mb-3"><h2 id="search-results" className="text-lg font-semibold">搜索结果</h2><p className="text-xs text-[var(--color-text-secondary)]">{videos.length ? '共 ' + videos.length + ' 个结果，点击卡片按钮导入' : '完成一次搜索后，结果会显示在这里'}</p></div>
      {Object.entries(groups).map(([platform, items]) => items.length > 0 && <div key={platform} className="mb-5"><h3 className="mb-2 text-sm font-semibold">{PLATFORM_LABELS[platform as Platform]} <span className="font-normal text-[var(--color-text-secondary)]">· {items.length}</span></h3><div className="grid gap-3 md:grid-cols-2">{items.map((video) => { const index = videos.indexOf(video); return <article key={video.url + '-' + index} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition hover:border-[var(--color-accent)]/50"><div className="flex gap-3"><img src={proxyImageUrl(video.cover || video.thumbnail || '')} alt="" className="h-20 w-32 shrink-0 rounded-lg bg-[var(--color-bg)] object-cover" onError={(event) => { event.currentTarget.src = '/product-logo.png'; }} /><div className="min-w-0 flex-1"><h4 className="line-clamp-2 text-sm font-semibold">{index + 1}. {video.title || '未命名视频'}</h4><p className="mt-1 flex items-center gap-1 text-xs text-[var(--color-text-secondary)]">{video.author || '未知作者'}{video.duration && <><span>·</span><Clock3 size={12} />{video.duration}</>}</p><a className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--color-accent)] hover:underline" href={video.url} target="_blank" rel="noreferrer">打开原视频 <ExternalLink size={12} /></a></div></div><button disabled={importingIndex !== null} onClick={() => void importVideo(index)} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--color-accent)]/30 bg-[var(--color-accent-light)] px-3 py-2 text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white disabled:cursor-wait disabled:opacity-60">{importingIndex === index ? <><Loader2 size={14} className="animate-spin" />导入中…</> : <><Upload size={14} />导入知识库</>}</button></article>; })}</div></div>)}
      {videos.length === 0 && !busy && <div className="rounded-2xl border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-text-secondary)]">暂无搜索结果</div>}
      {Object.entries(failures).map(([platform, message]) => <div key={platform} className="mb-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"><AlertCircle size={16} className="mt-0.5 shrink-0" /><span><strong>{PLATFORM_LABELS[platform as Platform]}搜索失败：</strong>{message}</span></div>)}
    </section>
  </div>;
}
