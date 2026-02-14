import { useState, useRef, useEffect } from 'react';
import { postFormData, fetchJSON, deleteAPI, extractBilibiliUrl, proxyImageUrl, streamPost } from '../api/client';
import { useSSE } from '../hooks/useSSE';
import ProgressBar from '../components/ProgressBar';
import ChatMessage from '../components/ChatMessage';
import { toast } from '../components/Toast';
import type { TaskStatus, VideoInfo } from '../types';
import { Loader2, Send, Trash2, Square } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export default function VideoQA() {
  const [mode, setMode] = useState<'url' | 'local'>('url');
  const [input, setInput] = useState('');
  const [transcript, setTranscript] = useState('');
  const [videoTitle, setVideoTitle] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [preprocessLoading, setPreprocessLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [answering, setAnswering] = useState(false);
  const [preview, setPreview] = useState<VideoInfo | null>(null);
  const msgEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { connect, disconnect } = useSSE();

  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handlePreprocess = async () => {
    const url = mode === 'url' ? extractBilibiliUrl(input.trim()) : input.trim();
    if (!url) return;
    if (mode === 'url' && !preview) {
      fetchJSON<{ success: boolean; data: VideoInfo }>(
        `/api/preview-video?url=${encodeURIComponent(url)}`,
      ).then((res) => setPreview(res.data)).catch(() => {});
    }
    setPreprocessLoading(true);
    setTask(null);
    setTranscript('');
    try {
      const formData: Record<string, string> = mode === 'url' ? { url } : { file_path: url };
      const res = await postFormData<{ task_id: string }>('/api/transcribe-only', formData);
      setTaskId(res.task_id);
      connect(`/api/task-stream/${res.task_id}`, {
        onMessage: (data) => {
          const t = data as TaskStatus;
          setTask(t);
          if (t.status === 'completed') {
            setTranscript(t.transcript || '');
            setVideoTitle(t.video_title || '');
            disconnect();
            setPreprocessLoading(false);
            toast('预处理完成，可以开始提问', 'success');
          } else if (t.status === 'error') {
            disconnect();
            setPreprocessLoading(false);
            toast(t.error || '预处理失败', 'error');
          }
        },
        onError: () => {
          setPreprocessLoading(false);
          toast('连接中断', 'error');
        },
      });
    } catch (e) {
      toast(e instanceof Error ? e.message : '预处理失败', 'error');
      setPreprocessLoading(false);
    }
  };

  const handleCancelPreprocess = async () => {
    if (!taskId) return;
    try {
      await deleteAPI(`/api/task/${taskId}`);
      disconnect();
      setPreprocessLoading(false);
      toast('已取消预处理', 'info');
    } catch {
      /* ignore */
    }
  };

  const handleAsk = () => {
    if (!question.trim() || !transcript || answering) return;
    const q = question.trim();
    setQuestion('');
    const userMsg: Message = { id: `u-${Date.now()}`, role: 'user', content: q, timestamp: new Date() };
    const aiMsg: Message = { id: `a-${Date.now()}`, role: 'assistant', content: '', timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg, aiMsg]);
    setAnswering(true);

    let fullAnswer = '';
    abortRef.current = streamPost(
      '/api/video-qa-stream',
      { question: q, transcript, video_url: input },
      (data) => {
        const d = data as { content?: string };
        if (d.content) {
          fullAnswer += d.content;
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { ...copy[copy.length - 1], content: fullAnswer };
            return copy;
          });
        }
      },
      () => setAnswering(false),
      (err) => {
        setMessages((prev) => [
          ...prev.slice(0, -1),
          { ...prev[prev.length - 1], content: `错误: ${err.message}` },
        ]);
        setAnswering(false);
      },
    );
  };

  const handleClear = () => {
    setMessages([]);
  };

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5">AI视频问答</h2>

        <div className="flex gap-1.5 mb-4">
          {(['url', 'local'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${
                mode === m
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border-light)]'
              }`}
            >
              {m === 'url' ? '在线URL' : '本地路径'}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={mode === 'url' ? '粘贴视频链接' : '输入本地文件路径'}
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
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-3 border-b border-[var(--color-border-light)] bg-[var(--color-surface)] shrink-0">
          <span className="text-sm font-medium text-[var(--color-text-secondary)]">
            {transcript ? '对话' : '等待预处理...'}
          </span>
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              className="flex items-center gap-1 px-2.5 py-1 text-xs text-[var(--color-text-secondary)] hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
            >
              <Trash2 size={12} />
              清空
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <p className="text-sm text-[var(--color-text-muted)]">
                {transcript ? '输入问题开始提问' : '请先完成视频预处理'}
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <ChatMessage
              key={m.id}
              role={m.role}
              content={m.content}
              timestamp={m.timestamp}
              isStreaming={answering && i === messages.length - 1 && m.role === 'assistant'}
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
              placeholder={transcript ? '输入你的问题...' : '请先完成预处理'}
              disabled={!transcript}
              className="flex-1 border border-[var(--color-border)] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20 disabled:bg-[var(--color-bg)] disabled:text-[var(--color-text-muted)]"
            />
            <button
              onClick={handleAsk}
              disabled={answering || !question.trim() || !transcript}
              className="w-9 h-9 flex items-center justify-center rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
            >
              {answering ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
