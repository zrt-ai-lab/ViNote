import { useState, useRef, useEffect, useCallback, lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import { streamPost, postJSON, deleteAPI, downloadFile } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import VideoCard from '../components/VideoCard';
import ProgressBar from '../components/ProgressBar';
import MarkdownRenderer from '../components/MarkdownRenderer';
import { toast } from '../components/Toast';
import type { AgentSSEData, AgentVideo, AgentVideoListData, AgentNotesData, AgentGenerateCommand } from '../types';
import { Send, Trash2, Loader2, Search, FileText, MessageCircle, Globe, ChevronDown, ChevronUp, Download, Brain, Maximize2, X } from 'lucide-react';

const MarkmapView = lazy(() => import('../components/MarkmapView'));

interface ChatMsg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  thinking?: string[];
  videosByPlatform?: Record<string, AgentVideo[]>;
  allVideos?: AgentVideo[];
  progress?: { percent: number; message: string };
  notesResult?: AgentNotesData;
  isStreaming?: boolean;
}

const PLATFORM_NAMES: Record<string, string> = {
  bilibili: '哔哩哔哩',
  youtube: 'YouTube',
  unknown: '其他平台',
};

function generateSessionId() {
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
}

export default function SearchAgent() {
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(generateSessionId);
  const [generatingUrls, setGeneratingUrls] = useState<Set<string>>(new Set());
  const [generatedUrls, setGeneratedUrls] = useState<Set<string>>(new Set());
  const [currentGenerationId, setCurrentGenerationId] = useState<string | null>(null);
  const [expandedThinking, setExpandedThinking] = useState<Set<string>>(new Set());
  const [fullscreenMindmap, setFullscreenMindmap] = useState<string | null>(null);
  const msgEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const initialQuerySent = useRef(false);

  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const q = searchParams.get('q');
    if (q && !initialQuerySent.current && messages.length === 0) {
      initialQuerySent.current = true;
      setInput('');
      setTimeout(() => sendMessage(q), 100);
    }
  }, [searchParams]);

  const updateLastMessage = useCallback((updater: (msg: ChatMsg) => ChatMsg) => {
    setMessages((prev) => {
      const copy = [...prev];
      if (copy.length > 0 && copy[copy.length - 1].role === 'assistant') {
        copy[copy.length - 1] = updater(copy[copy.length - 1]);
      }
      return copy;
    });
  }, []);

  const sendMessage = useCallback(
    (text?: string) => {
      const msg = (text || input).trim();
      if (!msg || loading) return;
      if (!text) setInput('');

      const userMsg: ChatMsg = { id: `u-${Date.now()}`, role: 'user', content: msg, timestamp: new Date() };
      const aiMsg: ChatMsg = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        thinking: [],
        isStreaming: true,
      };
      setMessages((prev) => [...prev, userMsg, aiMsg]);
      setLoading(true);

      abortRef.current = streamPost(
        '/api/search-agent-chat',
        { session_id: sessionId, message: msg },
        (raw) => {
          const data = raw as AgentSSEData;
          switch (data.type) {
            case 'text_chunk':
              updateLastMessage((m) => ({ ...m, content: m.content + (data.content || '') }));
              break;

            case 'thinking':
              updateLastMessage((m) => ({
                ...m,
                thinking: [...(m.thinking || []), data.content || ''],
              }));
              break;

            case 'video_list': {
              const vData = data.data as AgentVideoListData;
              if (vData?.videos?.length) {
                const byPlatform: Record<string, AgentVideo[]> = {};
                vData.videos.forEach((v) => {
                  const p = v.platform || 'unknown';
                  if (!byPlatform[p]) byPlatform[p] = [];
                  byPlatform[p].push(v);
                });
                updateLastMessage((m) => ({
                  ...m,
                  videosByPlatform: byPlatform,
                  allVideos: vData.videos,
                }));
              }
              break;
            }

            case 'progress':
              updateLastMessage((m) => ({
                ...m,
                progress: { percent: data.progress || 0, message: data.message || '' },
              }));
              break;

            case 'notes_complete':
              updateLastMessage((m) => ({
                ...m,
                notesResult: data.data as AgentNotesData,
                progress: undefined,
              }));
              setCurrentGenerationId(null);
              break;

            case 'generation_id':
              setCurrentGenerationId(data.generation_id || null);
              break;

            case 'generate_notes_command': {
              const cmd = data.data as AgentGenerateCommand;
              if (cmd?.video_url) {
                handleGenerateNotes(cmd.video_url, cmd.video_title);
              }
              break;
            }

            case 'error':
            case 'cancelled':
              updateLastMessage((m) => ({
                ...m,
                content: m.content + `\n\n${data.type === 'error' ? '❌' : '⚠️'} ${data.content || ''}`,
              }));
              break;

            case 'done':
              break;
          }
        },
        () => {
          updateLastMessage((m) => ({ ...m, isStreaming: false }));
          setLoading(false);
        },
        (err) => {
          updateLastMessage((m) => ({
            ...m,
            content: m.content + `\n\n❌ 错误: ${err.message}`,
            isStreaming: false,
          }));
          setLoading(false);
        },
      );
    },
    [input, loading, sessionId, updateLastMessage],
  );

  const handleGenerateNotes = useCallback(
    async (videoUrl: string, _videoTitle: string) => {
      setGeneratingUrls((prev) => new Set(prev).add(videoUrl));

      const aiMsg: ChatMsg = {
        id: `notes-${Date.now()}`,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
      };
      setMessages((prev) => [...prev, aiMsg]);

      streamPost(
        '/api/search-agent-generate-notes',
        { video_url: videoUrl, summary_language: 'zh' },
        (raw) => {
          const data = raw as AgentSSEData;
          switch (data.type) {
            case 'text_chunk':
              updateLastMessage((m) => ({ ...m, content: m.content + (data.content || '') }));
              break;
            case 'progress':
              updateLastMessage((m) => ({
                ...m,
                progress: { percent: data.progress || 0, message: data.message || '' },
              }));
              break;
            case 'notes_complete':
              updateLastMessage((m) => ({
                ...m,
                notesResult: data.data as AgentNotesData,
                progress: undefined,
              }));
              setGeneratingUrls((prev) => {
                const next = new Set(prev);
                next.delete(videoUrl);
                return next;
              });
              setGeneratedUrls((prev) => new Set(prev).add(videoUrl));
              setCurrentGenerationId(null);
              break;
            case 'generation_id':
              setCurrentGenerationId(data.generation_id || null);
              break;
            case 'error':
            case 'cancelled':
              updateLastMessage((m) => ({
                ...m,
                content: m.content + `\n\n${data.type === 'error' ? '❌' : '⚠️'} ${data.content || ''}`,
              }));
              setGeneratingUrls((prev) => {
                const next = new Set(prev);
                next.delete(videoUrl);
                return next;
              });
              break;
            case 'done':
              break;
          }
        },
        () => {
          updateLastMessage((m) => ({ ...m, isStreaming: false }));
        },
        (err) => {
          updateLastMessage((m) => ({
            ...m,
            content: m.content + `\n\n❌ ${err.message}`,
            isStreaming: false,
          }));
          setGeneratingUrls((prev) => {
            const next = new Set(prev);
            next.delete(videoUrl);
            return next;
          });
        },
      );
    },
    [updateLastMessage],
  );

  const handleCancelGeneration = async () => {
    if (!currentGenerationId) return;
    try {
      await deleteAPI(`/api/search-agent-cancel-generation/${currentGenerationId}`);
      toast('已取消生成', 'info');
    } catch {
      toast('取消失败', 'error');
    }
  };

  const handleClear = async () => {
    try {
      await postJSON('/api/search-agent-clear-session', { session_id: sessionId });
    } catch {
      /* ignore */
    }
    abortRef.current?.abort();
    setMessages([]);
    setSessionId(generateSessionId());
    setGeneratingUrls(new Set());
    setGeneratedUrls(new Set());
    setCurrentGenerationId(null);
    setLoading(false);
  };

  const toggleThinking = (msgId: string) => {
    setExpandedThinking((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
  };

  useEffect(() => {
    messages.forEach((m) => {
      if (m.role === 'assistant' && m.thinking && m.thinking.length > 0) {
        if (m.isStreaming) {
          setExpandedThinking((prev) => {
            if (prev.has(m.id)) return prev;
            return new Set(prev).add(m.id);
          });
        } else {
          setExpandedThinking((prev) => {
            if (!prev.has(m.id)) return prev;
            const next = new Set(prev);
            next.delete(m.id);
            return next;
          });
        }
      }
    });
  }, [messages]);

  return (
    <div className="flex h-full">
      <div className="w-80 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5">ViNoter 超级智搜</h2>
        <div className="space-y-4">
          <div className="p-4 bg-[var(--color-bg)] rounded-lg">
            <h3 className="text-xs font-semibold text-[var(--color-text-secondary)] mb-3 uppercase tracking-wider">功能</h3>
            <div className="space-y-2.5">
              {[
                { icon: <Search size={14} />, label: '搜索视频', desc: '跨平台搜索优质视频' },
                { icon: <FileText size={14} />, label: '生成笔记', desc: '自动生成视频笔记摘要' },
                { icon: <MessageCircle size={14} />, label: '智能对话', desc: '自然语言交互操作' },
                { icon: <Globe size={14} />, label: '多平台支持', desc: 'B站、YouTube等' },
              ].map((item) => (
                <div key={item.label} className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-md bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-accent)] shrink-0 mt-0.5">
                    {item.icon}
                  </div>
                  <div>
                    <p className="text-xs font-medium text-[var(--color-text)]">{item.label}</p>
                    <p className="text-[11px] text-[var(--color-text-secondary)]">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-3 border-b border-[var(--color-border-light)] bg-[var(--color-surface)] shrink-0">
          <span className="text-sm font-medium text-[var(--color-text-secondary)]">对话</span>
          <button
            onClick={handleClear}
            className="flex items-center gap-1 px-2.5 py-1 text-xs text-[var(--color-text-secondary)] hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
          >
            <Trash2 size={12} />
            清空对话
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full">
              <div className="w-12 h-12 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-3">
                <img src="/product-logo.png" alt="" className="w-7 h-7 rounded-full" />
              </div>
              <p className="text-sm text-[var(--color-text-secondary)] font-medium mb-1">你好！我是 ViNote 搜索助手</p>
              <p className="text-xs text-[var(--color-text-muted)] text-center max-w-sm">
                我可以帮你搜索各平台视频、生成笔记和摘要。试试说"帮我在B站搜索Python教程"
              </p>
            </div>
          )}

          {messages.map((m) => (
            <div key={m.id}>
              <ChatMessage
                role={m.role}
                content={m.content}
                timestamp={m.timestamp}
                isStreaming={m.isStreaming && !m.content}
              >
                {m.thinking && m.thinking.length > 0 && (
                  <div className="mt-3">
                    <button
                      onClick={() => toggleThinking(m.id)}
                      className="w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-indigo-50/80 hover:bg-indigo-100/80 border border-indigo-100 transition-all duration-200 group"
                    >
                      <div className={`w-6 h-6 rounded-lg bg-indigo-100 flex items-center justify-center ${m.isStreaming ? 'animate-pulse' : ''}`}>
                        <Brain size={13} className="text-indigo-600" />
                      </div>
                      <span className="text-xs font-medium text-indigo-700 flex-1 text-left">
                        {m.isStreaming ? 'AI 思考中...' : '思考过程'}
                      </span>
                      <span className="text-[10px] font-semibold text-indigo-500 bg-indigo-100 px-2 py-0.5 rounded-full">
                        {m.thinking.length} 步
                      </span>
                      {expandedThinking.has(m.id) ? (
                        <ChevronUp size={14} className="text-indigo-400 group-hover:text-indigo-600 transition-colors" />
                      ) : (
                        <ChevronDown size={14} className="text-indigo-400 group-hover:text-indigo-600 transition-colors" />
                      )}
                    </button>
                    {expandedThinking.has(m.id) && (
                      <div className="mt-2 ml-3 pl-4 border-l-2 border-indigo-200 space-y-3 py-2">
                        {m.thinking.map((t, i) => (
                          <div key={i} className="flex gap-3 items-start">
                            <div className="w-5 h-5 rounded-full bg-indigo-100 border-2 border-indigo-300 flex items-center justify-center shrink-0 -ml-[1.375rem]">
                              <span className="text-[9px] font-bold text-indigo-600">{i + 1}</span>
                            </div>
                            <div className="text-xs text-[var(--color-text-secondary)] leading-relaxed min-w-0 flex-1">
                              <MarkdownRenderer content={t} className="text-xs" />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {m.videosByPlatform && Object.keys(m.videosByPlatform).length > 0 && (
                  <div className="mt-3 space-y-4">
                    {Object.entries(m.videosByPlatform).map(([platform, videos]) => (
                      <div key={platform}>
                        <div className="flex items-center gap-2 mb-2.5">
                          <Globe size={13} className="text-[var(--color-accent)]" />
                          <span className="text-xs font-semibold text-[var(--color-text)]">
                            {PLATFORM_NAMES[platform] || platform}
                          </span>
                          <span className="text-[10px] text-[var(--color-text-muted)] bg-[var(--color-bg)] px-1.5 py-0.5 rounded-full">
                            {videos.length} 个视频
                          </span>
                        </div>
                        <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
                          {videos.map((v, vi) => (
                            <VideoCard
                              key={vi}
                              video={v}
                              onGenerateNotes={(url, title) => handleGenerateNotes(url, title)}
                              generating={generatingUrls.has(v.url)}
                              generated={generatedUrls.has(v.url)}
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {m.progress && (
                  <div className="mt-3">
                    <div className="px-4 py-3 bg-[var(--color-surface)] border border-[var(--color-border-light)] rounded-xl">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Loader2 size={14} className="text-[var(--color-accent)] animate-spin" />
                          <span className="text-xs text-[var(--color-text-secondary)]">{m.progress.message}</span>
                        </div>
                        <span className="text-xs font-semibold text-[var(--color-accent)] tabular-nums">
                          {m.progress.percent}%
                        </span>
                      </div>
                      <ProgressBar progress={m.progress.percent} />
                      {currentGenerationId && (
                        <button
                          onClick={handleCancelGeneration}
                          className="mt-2 text-[11px] text-[var(--color-text-muted)] hover:text-red-500 transition-colors"
                        >
                          取消生成
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {m.notesResult && (
                  <div className="mt-3">
                    <div className="rounded-xl shadow-sm bg-white border border-emerald-100 border-l-4 border-l-emerald-500 overflow-hidden">
                      <div className="px-4 py-3 bg-gradient-to-r from-emerald-50 to-transparent flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center">
                          <FileText size={14} className="text-emerald-600" />
                        </div>
                        <span className="text-sm font-semibold text-emerald-900 flex-1 min-w-0 truncate">
                          {m.notesResult.video_title || m.notesResult.title || '笔记已生成'}
                        </span>
                      </div>
                      {m.notesResult.summary && (
                        <div className="px-4 py-3 border-t border-emerald-50">
                          <div className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                            <MarkdownRenderer content={m.notesResult.summary} className="text-xs" />
                          </div>
                        </div>
                      )}
                      {m.notesResult.mindmap && (
                        <div className="mx-4 mb-3 border border-emerald-100 rounded-lg overflow-hidden">
                          <div className="flex items-center justify-between px-3 py-2 bg-emerald-50/60 border-b border-emerald-100">
                            <div className="flex items-center gap-2">
                              <Brain size={13} className="text-emerald-600" />
                              <span className="text-xs font-medium text-emerald-700">思维导图</span>
                            </div>
                            <button
                              onClick={() => setFullscreenMindmap(m.notesResult!.mindmap!)}
                              className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-emerald-600 hover:bg-emerald-100 rounded transition-colors"
                            >
                              <Maximize2 size={11} />
                              全屏
                            </button>
                          </div>
                          <Suspense fallback={<div className="h-[500px] flex items-center justify-center text-xs text-emerald-400">加载中...</div>}>
                            <MarkmapView content={m.notesResult.mindmap} className="h-[500px]" />
                          </Suspense>
                        </div>
                      )}
                      <div className="px-4 py-3 border-t border-emerald-50 flex gap-2 flex-wrap">
                        {m.notesResult.files?.transcript_filename && (
                          <button
                            onClick={() => downloadFile(m.notesResult!.files!.transcript_filename!)}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-emerald-50 text-emerald-700 rounded-full hover:bg-emerald-100 border border-emerald-200 transition-colors"
                          >
                            <Download size={12} /> 完整笔记
                          </button>
                        )}
                        {m.notesResult.files?.summary_filename && (
                          <button
                            onClick={() => downloadFile(m.notesResult!.files!.summary_filename!)}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-emerald-50 text-emerald-700 rounded-full hover:bg-emerald-100 border border-emerald-200 transition-colors"
                          >
                            <Download size={12} /> 摘要
                          </button>
                        )}
                        {m.notesResult.files?.raw_transcript_filename && (
                          <button
                            onClick={() => downloadFile(m.notesResult!.files!.raw_transcript_filename!)}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-emerald-50 text-emerald-700 rounded-full hover:bg-emerald-100 border border-emerald-200 transition-colors"
                          >
                            <Download size={12} /> 原文
                          </button>
                        )}
                        {m.notesResult.files?.mindmap_filename && (
                          <button
                            onClick={() => downloadFile(m.notesResult!.files!.mindmap_filename!)}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-emerald-50 text-emerald-700 rounded-full hover:bg-emerald-100 border border-emerald-200 transition-colors"
                          >
                            <Download size={12} /> 思维导图
                          </button>
                        )}
                        {m.notesResult.files?.translation_filename && (
                          <button
                            onClick={() => downloadFile(m.notesResult!.files!.translation_filename!)}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-emerald-50 text-emerald-700 rounded-full hover:bg-emerald-100 border border-emerald-200 transition-colors"
                          >
                            <Download size={12} /> 翻译
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </ChatMessage>
            </div>
          ))}
          <div ref={msgEndRef} />
        </div>

        <div className="p-4 border-t border-[var(--color-border-light)] bg-[var(--color-surface)] shrink-0">
          <div className="flex gap-2 max-w-4xl mx-auto">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
              placeholder="搜索视频或输入指令..."
              className="flex-1 border border-[var(--color-border)] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20"
            />
            <button
              onClick={() => sendMessage()}
              disabled={loading || !input.trim()}
              className="w-10 h-10 flex items-center justify-center rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>

      {fullscreenMindmap && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <div className="relative w-full h-full bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] shadow-2xl overflow-hidden">
            <div className="absolute top-3 right-3 z-10">
              <button
                onClick={() => setFullscreenMindmap(null)}
                className="p-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <Suspense fallback={<div className="h-full flex items-center justify-center text-sm text-[var(--color-text-muted)]">加载中...</div>}>
              <MarkmapView content={fullscreenMindmap} className="h-full" />
            </Suspense>
          </div>
        </div>
      )}
    </div>
  );
}
