import type { AgentVideo } from '../types';

const storageKey = 'vinote-search-session-id';
type SessionStorage = Pick<Storage, 'getItem' | 'setItem'>;

export interface SearchSessionSnapshot {
  session_id: string;
  messages: { role: 'user' | 'assistant'; content: string }[];
  videos: AgentVideo[];
  updated_at?: string;
}

interface RestoredMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  videosByPlatform?: Record<string, AgentVideo[]>;
  allVideos?: AgentVideo[];
}

export function getSearchSessionId(storage?: SessionStorage): string {
  let target: SessionStorage | undefined;
  try {
    target = storage ?? window.localStorage;
    const existing = target.getItem(storageKey);
    if (existing && /^[A-Za-z0-9_-]{1,128}$/.test(existing)) return existing;
  } catch {
    // Storage can be blocked; an in-memory session must still work.
  }
  const id = globalThis.crypto?.randomUUID?.()
    ?? `session_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
  try {
    target?.setItem(storageKey, id);
  } catch {
    // Persist only the opaque ID, never messages, videos or model settings.
  }
  return id;
}

export function groupSearchVideos(videos: AgentVideo[]): Record<string, AgentVideo[]> {
  const grouped: Record<string, AgentVideo[]> = Object.create(null);
  for (const video of videos) {
    const platform = video.platform || 'unknown';
    (grouped[platform] ??= []).push(video);
  }
  return grouped;
}

export function updateSearchMessage<T extends { id: string; role: string }>(
  messages: T[], messageId: string, updater: (message: T) => T, isCurrent: () => boolean,
): T[] {
  if (!isCurrent()) return messages;
  const index = messages.findIndex((message) => message.id === messageId && message.role === 'assistant');
  if (index < 0) return messages;
  const copy = [...messages];
  copy[index] = updater(copy[index]);
  return copy;
}

export function getNoteWarnings(result: { persisted?: boolean; warnings?: string[] }): string {
  const warnings = Array.isArray(result.warnings)
    ? result.warnings.filter((warning) => typeof warning === 'string' && warning.trim())
    : [];
  if (result.persisted === false) warnings.unshift('文件已生成，但未保存到笔记库。');
  return warnings.length ? `\n\n${[...new Set(warnings)].map((warning) => `⚠️ ${warning}`).join('\n\n')}` : '';
}

export function restoreSearchMessages(session: SearchSessionSnapshot): RestoredMessage[] {
  const timestamp = new Date(session.updated_at || Date.now());
  const validTimestamp = Number.isNaN(timestamp.getTime()) ? new Date() : timestamp;
  const messages: RestoredMessage[] = session.messages.map((message, index) => ({
    id: `restored-${index}`,
    role: message.role,
    content: message.content,
    timestamp: validTimestamp,
  }));
  if (session.videos.length > 0) {
    let target = messages.length - 1;
    while (target >= 0 && messages[target].role !== 'assistant') target--;
    if (target < 0) {
      target = messages.length;
      messages.push({ id: `restored-${target}`, role: 'assistant', content: '', timestamp: validTimestamp });
    }
    messages[target].allVideos = session.videos;
    messages[target].videosByPlatform = groupSearchVideos(session.videos);
  }
  return messages;
}

/** A successful clear or unmount invalidates every older async callback. */
export function createSessionGuard() {
  let generation = 0;
  return {
    capture() {
      const captured = generation;
      return () => captured === generation;
    },
    invalidate() { generation++; },
  };
}
