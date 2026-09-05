import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { postFormData, fetchJSON, deleteAPI, extractBilibiliUrl, proxyImageUrl, streamPost } from '../api/client';
import { useTaskProgress } from '../hooks/useTaskProgress';
import { readStoredId, writeStoredId } from '../utils/taskRecovery';
import ProgressBar from '../components/ProgressBar';
import ChatMessage from '../components/ChatMessage';
import { toast } from '../components/toastStore';
import type { QASession, QASessionSummary, TaskStatus, VideoInfo } from '../types';
import { Loader2, Send, Trash2, Square, Plus, RefreshCw, MessageCircle } from 'lucide-react';

const qaTaskKey = 'vinote.qa.task-id';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export default function VideoQA() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('sessionId');
  const [input, setInput] = useState('');
  const [transcript, setTranscript] = useState('');
  const [videoTitle, setVideoTitle] = useState('');
  const [taskId, setTaskId] = useState<string | null>(() => readStoredId(qaTaskKey));
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [preprocessLoading, setPreprocessLoading] = useState(() => Boolean(readStoredId(qaTaskKey)));
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [answering, setAnswering] = useState(false);
  const [preview, setPreview] = useState<VideoInfo | null>(null);
  const [session, setSession] = useState<QASession | null>(null);
  const [sessionError, setSessionError] = useState<{ id: string; message: string } | null>(null);
  const [sessionReload, setSessionReload] = useState(0);
  const [messageSessionId, setMessageSessionId] = useState<string | null>(sessionId);
  const [recentSessions, setRecentSessions] = useState<QASessionSummary[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState('');
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const msgEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const activeSession = session?.id === sessionId ? session : null;
  const sessionLoading = Boolean(sessionId && !activeSession && sessionError?.id !== sessionId);
  const readyToAsk = sessionId ? Boolean(activeSession?.sources.length) : Boolean(transcript);
  const visibleMessages = messageSessionId === sessionId ? messages : [];
  const isAnswering = answering && messageSessionId === sessionId;

  const loadRecentSessions = useCallback(async () => {
    setRecentLoading(true);
    try {
      const data = await fetchJSON<{ sessions: QASessionSummary[] }>('/api/qa/sessions');
      setRecentSessions(data.sessions);
      setRecentError('');
    } catch (error) {
      setRecentError(error instanceof Error ? error.message : '加载最近会话失败');
    } finally {
      setRecentLoading(false);
    }
  }, []);

  useEffect(() => { void loadRecentSessions(); }, [loadRecentSessions]);

  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!sessionId) return;
    const controller = new AbortController();
    fetchJSON<QASession>(`/api/qa/sessions/${encodeURIComponent(sessionId)}`, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        setSession(data);
        setAnswering(false);
        setSessionError(null);
        setMessageSessionId(sessionId);
        setMessages(data.messages.map((message) => ({
          id: String(message.id),
          role: message.role,
          content: message.content,
          timestamp: new Date(`${message.created_at}Z`),
        })));
      })
      .catch((error) => {
        if (!controller.signal.aborted) setSessionError({ id: sessionId, message: error instanceof Error ? error.message : '加载问答会话失败' });
      });
    return () => controller.abort();
  }, [sessionId, sessionReload]);

  useEffect(() => () => abortRef.current?.abort(), [sessionId]);

  const handleTaskUpdate = useCallback((t: TaskStatus) => {
    setTask(t);
    setPreprocessLoading(t.status === 'queued' || t.status === 'processing');
    if (t.status === 'completed') {
      setTranscript(t.transcript || t.raw_script || t.script || '');
      setVideoTitle(t.video_title || '');
    } else if (t.status === 'error') {
      toast(t.error || '预处理失败', 'error');
    }
  }, []);
  const handleTaskUnavailable = useCallback((error: Error) => {
    setTaskId(null);
    writeStoredId(qaTaskKey, null);
    setPreprocessLoading(false);
    toast(error.message, 'error');
  }, []);
  const taskConnection = useTaskProgress(sessionId ? null : taskId, handleTaskUpdate, handleTaskUnavailable);

  const handlePreprocess = async () => {
    const url = extractBilibiliUrl(input.trim());
    if (!url) return;
    // 尝试预览（仅在线URL有效，本地路径会静默失败）
    if (!preview) {
      fetchJSON<{ success: boolean; data: VideoInfo }>(
        `/api/preview-video?url=${encodeURIComponent(url)}`,
      ).then((res) => setPreview(res.data)).catch(() => {});
    }
    setPreprocessLoading(true);
    setTask(null);
    setTranscript('');
    try {
      const res = await postFormData<{ task_id: string }>('/api/transcribe-only', { url });
      writeStoredId(qaTaskKey, res.task_id);
      setTaskId(res.task_id);
    } catch (e) {
      toast(e instanceof Error ? e.message : '预处理失败', 'error');
      setPreprocessLoading(false);
    }
  };

  const handleCancelPreprocess = async () => {
    if (!taskId) return;
    try {
      await deleteAPI(`/api/task/${taskId}`);
      setTaskId(null);
      writeStoredId(qaTaskKey, null);
      setPreprocessLoading(false);
      toast('已取消预处理', 'info');
    } catch (error) {
      toast(error instanceof Error ? error.message : '取消预处理失败', 'error');
    }
  };

  const handleAsk = () => {
    if (!question.trim() || !readyToAsk || isAnswering) return;
    const q = question.trim();
    setQuestion('');
    const userMsg: Message = { id: `u-${Date.now()}`, role: 'user', content: q, timestamp: new Date() };
    const aiMsg: Message = { id: `a-${Date.now()}`, role: 'assistant', content: '', timestamp: new Date() };
    setMessages((prev) => [...(messageSessionId === sessionId ? prev : []), userMsg, aiMsg]);
    setMessageSessionId(sessionId);
    setAnswering(true);

    let fullAnswer = '';
    abortRef.current = streamPost(
      sessionId ? `/api/qa/sessions/${sessionId}/messages/stream` : '/api/video-qa-stream',
      sessionId ? { question: q } : { question: q, transcript, video_url: input },
      (data) => {
        const d = data as { content?: string; error?: string };
        if (d.error) {
          fullAnswer = `错误: ${d.error}`;
          setMessages((prev) => prev.map((message) => message.id === aiMsg.id ? { ...message, content: fullAnswer } : message));
          return;
        }
        if (d.content) {
          fullAnswer += d.content;
          setMessages((prev) => prev.map((message) => message.id === aiMsg.id ? { ...message, content: fullAnswer } : message));
        }
      },
      () => { setAnswering(false); if (sessionId) void loadRecentSessions(); },
      (err) => {
        setMessages((prev) => prev.map((message) => message.id === aiMsg.id ? { ...message, content: `错误: ${err.message}` } : message));
        setAnswering(false);
      },
    );
  };

  const handleNewConversation = () => {
    abortRef.current?.abort();
    setAnswering(false);
    setSession(null);
    setSessionError(null);
    setTaskId(null);
    writeStoredId(qaTaskKey, null);
    setTask(null);
    setPreprocessLoading(false);
    setTranscript('');
    setInput('');
    setPreview(null);
    setVideoTitle('');
    setQuestion('');
    setMessageSessionId(null);
    setMessages([]);
    navigate('/qa');
  };

  const handleOpenSession = (id: string) => {
    abortRef.current?.abort();
    setAnswering(false);
    setSessionError(null);
    setQuestion('');
    navigate(`/qa?sessionId=${encodeURIComponent(id)}`);
  };

  const handleDeleteSession = async (id: string) => {
    if (!confirm('确认删除此问答会话及全部消息？此操作不可撤销。')) return;
    setDeletingSessionId(id);
    try {
      await deleteAPI(`/api/qa/sessions/${encodeURIComponent(id)}`);
      setRecentSessions((previous) => previous.filter((item) => item.id !== id));
      if (id === sessionId) handleNewConversation();
      toast('问答会话已删除', 'success');
    } catch (error) {
      toast(error instanceof Error ? error.message : '删除会话失败', 'error');
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleClear = () => {
    if (sessionId) {
      void handleDeleteSession(sessionId);
      return;
    }
    abortRef.current?.abort();
    setAnswering(false);
    setMessages([]);
  };

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-[var(--color-text)]">AI视频问答</h2>
          <button onClick={handleNewConversation} className="flex items-center gap-1 text-xs text-[var(--color-accent)]"><Plus size={13} /> 新问答</button>
        </div>

        <div className="space-y-3">
          {sessionId && sessionLoading && (
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
              <Loader2 size={13} className="animate-spin" /> 正在恢复问答会话...
            </div>
          )}

          {sessionId && sessionError?.id === sessionId && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
              <p>{sessionError.message}</p>
              <button onClick={() => { setSessionError(null); setSessionReload((value) => value + 1); }} className="mt-2 underline">重新加载会话</button>
            </div>
          )}

          {activeSession && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-[var(--color-text)]">{activeSession.title}</p>
              <p className="text-[11px] text-[var(--color-text-muted)]">知识来源（{activeSession.sources.length}）</p>
              {activeSession.sources.map((source) => (
                <div key={source.short_id} className="p-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
                  <p className="text-xs text-[var(--color-text)] line-clamp-2">{source.title}</p>
                  <p className="text-[10px] text-[var(--color-text-muted)] mt-1">
                    {source.content_field === 'summary' ? '摘要' : '原文/完整笔记'}
                  </p>
                </div>
              ))}
            </div>
          )}

          {!sessionId && (
            <>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="粘贴视频链接或本地文件路径"
            className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20 disabled:bg-[var(--color-bg)] disabled:text-[var(--color-text-muted)]"
            disabled={!!transcript}
          />

          {preview && (
            <div className="p-3 bg-[var(--color-bg)] rounded-lg">
              {preview.thumbnail && (
                <img
                  src={proxyImageUrl(preview.thumbnail)}
                  alt=""
                  className="w-full h-32 object-cover rounded-md mb-2"
                />
              )}
              <p className="text-sm font-medium text-[var(--color-text)] line-clamp-2">{preview.title}</p>
              <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                {preview.uploader && `${preview.uploader} · `}
                {preview.duration > 0 &&
                  `${Math.floor(preview.duration / 60)}:${String(preview.duration % 60).padStart(2, '0')}`}
              </p>
            </div>
          )}

          {!transcript && (
            preprocessLoading ? (
              <div className="space-y-2">
                <ProgressBar progress={task?.progress ?? 0} />
                <p className="text-xs text-[var(--color-text-secondary)]">{task?.message || '预处理中...'}</p>
                {taskConnection === 'retrying' && <p role="status" className="text-xs text-amber-700">状态连接中断，正在自动恢复，请勿重复提交。</p>}
                {taskConnection === 'polling' && <p role="status" className="text-xs text-[var(--color-text-secondary)]">已恢复状态查询，正在同步进度。</p>}
                <button
                  onClick={handleCancelPreprocess}
                  className="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-medium bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
                >
                  <Square size={13} />
                  取消预处理
                </button>
              </div>
            ) : (
              <button
                onClick={handlePreprocess}
                disabled={!input.trim()}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
              >
                开始预处理
              </button>
            )
          )}

          {transcript && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
              <p className="text-xs font-medium text-emerald-700">
                {videoTitle && <span className="block mb-0.5">{videoTitle}</span>}
                预处理完成，可以开始提问
              </p>
            </div>
          )}
            </>
          )}
        </div>
        <section className="mt-6 border-t border-[var(--color-border)] pt-4" aria-label="最近问答会话">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-[var(--color-text)]">最近会话</h3>
            <button onClick={() => void loadRecentSessions()} disabled={recentLoading} aria-label="刷新最近会话" className="text-[var(--color-text-muted)] disabled:opacity-40"><RefreshCw size={13} className={recentLoading ? 'animate-spin' : ''} /></button>
          </div>
          {recentError && <p role="alert" className="mb-2 text-xs text-red-600">{recentError}，可点击刷新重试。</p>}
          {!recentLoading && !recentError && recentSessions.length === 0 && <p className="text-xs text-[var(--color-text-muted)]">还没有保存的会话。可在历史记录中选择笔记发起知识问答。</p>}
          <div className="space-y-2">
            {recentSessions.map((item) => (
              <div key={item.id} className={`flex items-center gap-2 rounded-lg border p-2 ${item.id === sessionId ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/5' : 'border-[var(--color-border)]'}`}>
                <button onClick={() => handleOpenSession(item.id)} className="min-w-0 flex-1 text-left" aria-label={`继续会话：${item.title}`}>
                  <span className="flex items-center gap-1.5 text-xs text-[var(--color-text)]"><MessageCircle size={12} className="shrink-0" /><span className="truncate">{item.title}</span></span>
                  <span className="mt-1 block text-[10px] text-[var(--color-text-muted)]">{item.source_count} 条笔记 · {item.message_count} 条消息</span>
                </button>
                <button onClick={() => void handleDeleteSession(item.id)} disabled={deletingSessionId === item.id || (isAnswering && item.id === sessionId)} aria-label={`删除会话：${item.title}`} className="p-1 text-[var(--color-text-muted)] hover:text-red-600 disabled:opacity-40">
                  {deletingSessionId === item.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                </button>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-3 border-b border-[var(--color-border-light)] bg-[var(--color-surface)] shrink-0">
          <span className="text-sm font-medium text-[var(--color-text-secondary)]">
            {readyToAsk ? '对话' : sessionId ? '请选择或恢复问答会话' : '等待预处理...'}
          </span>
          {visibleMessages.length > 0 && (
            <button
              onClick={handleClear}
              disabled={Boolean(sessionId && isAnswering)}
              className="flex items-center gap-1 px-2.5 py-1 text-xs text-[var(--color-text-secondary)] hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
            >
              <Trash2 size={12} />
                {sessionId ? '删除会话' : '清空'}
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {visibleMessages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <p className="text-sm text-[var(--color-text-muted)]">
                {readyToAsk ? '输入问题开始提问' : sessionId ? '正在等待会话内容' : '请先完成视频预处理'}
              </p>
            </div>
          )}
          {visibleMessages.map((m, i) => (
            <ChatMessage
              key={m.id}
              role={m.role}
              content={m.content}
              timestamp={m.timestamp}
              isStreaming={isAnswering && i === visibleMessages.length - 1 && m.role === 'assistant'}
            />
          ))}
          <div ref={msgEndRef} />
        </div>

        <div className="p-4 border-t border-[var(--color-border-light)] bg-[var(--color-surface)] shrink-0">
          <div className="flex gap-2">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
              placeholder={readyToAsk ? '输入你的问题...' : '请先选择会话或完成预处理'}
              disabled={!readyToAsk}
              className="flex-1 border border-[var(--color-border)] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20 disabled:bg-[var(--color-bg)] disabled:text-[var(--color-text-muted)]"
            />
            <button
              onClick={handleAsk}
              disabled={isAnswering || !question.trim() || !readyToAsk}
              className="w-9 h-9 flex items-center justify-center rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
            >
              {isAnswering ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
