import { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import { postFormData, postJSON, fetchJSON, extractBilibiliUrl, deleteAPI } from '../api/client';
import { useSSE } from '../hooks/useSSE';
import ProgressBar from '../components/ProgressBar';
import { toast } from '../components/Toast';
import type { TaskStatus } from '../types';
import { BrainCircuit, Play, Loader2, Square } from 'lucide-react';

const MarkmapView = lazy(() => import('../components/MarkmapView'));

type InputMode = 'text' | 'video';

export default function MindMap() {
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<InputMode>('text');

  const [textContent, setTextContent] = useState('');
  const [textLoading, setTextLoading] = useState(false);

  const [url, setUrl] = useState('');
  const [videoLoading, setVideoLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const { connect, disconnect } = useSSE();

  const [mindmapContent, setMindmapContent] = useState('');
  const autoLoadedRef = useRef(false);

  useEffect(() => {
    if (autoLoadedRef.current) return;
    const tid = searchParams.get('taskId');
    const field = searchParams.get('field') || 'summary';
    if (!tid) return;
    autoLoadedRef.current = true;
    setMode('text');
    setTextLoading(true);
    fetchJSON<{ content: string }>(`/api/tasks/${tid}/content?field=${field}`)
      .then(async (res) => {
        setTextContent(res.content);
        const result = await postJSON<{ mindmap: string }>('/api/generate-mindmap', {
          content: res.content,
          language: 'zh',
        });
        setMindmapContent(result.mindmap);
        toast('思维导图已生成', 'success');
      })
      .catch(() => toast('自动生成失败', 'error'))
      .finally(() => setTextLoading(false));
  }, [searchParams]);

  // 场景1: 粘贴文本 → 大模型生成思维导图
  const handleTextGenerate = async () => {
    const content = textContent.trim();
    if (!content) return;
    setTextLoading(true);
    setMindmapContent('');
    try {
      const res = await postJSON<{ mindmap: string }>('/api/generate-mindmap', {
        content,
        language: 'zh',
      });
      setMindmapContent(res.mindmap);
      toast('思维导图已生成', 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : '生成失败', 'error');
    } finally {
      setTextLoading(false);
    }
  };

  // 场景2: 视频URL → 下载+转录+摘要+思维导图
  const handleVideoGenerate = async () => {
    const extracted = extractBilibiliUrl(url.trim());
    if (!extracted) return;
    setVideoLoading(true);
    setProgress(0);
    setStatusMessage('正在提交任务...');
    setMindmapContent('');
    try {
      const res = await postFormData<{ task_id: string }>('/api/video-to-mindmap', {
        url: extracted,
        language: 'zh',
      });
      setTaskId(res.task_id);
      connect(`/api/task-stream/${res.task_id}`, {
        onMessage: (data) => {
          const t = data as TaskStatus;
          setProgress(t.progress);
          setStatusMessage(t.message || '');
          if (t.status === 'completed') {
            if (t.mindmap) {
              setMindmapContent(t.mindmap);
              toast('思维导图生成完成！', 'success');
            } else {
              toast('视频处理完成，但未生成思维导图', 'info');
            }
            disconnect();
            setVideoLoading(false);
          } else if (t.status === 'error') {
            disconnect();
            setVideoLoading(false);
            toast(t.error || '生成失败', 'error');
          }
        },
        onError: () => {
          setVideoLoading(false);
          toast('连接中断', 'error');
        },
      });
    } catch (e) {
      toast(e instanceof Error ? e.message : '生成失败', 'error');
      setVideoLoading(false);
    }
  };

  const handleCancelVideo = async () => {
    if (taskId) {
      try { await deleteAPI(`/api/task/${taskId}`); } catch { /* ignore */ }
    }
    disconnect();
    setVideoLoading(false);
    setStatusMessage('');
    setTaskId(null);
    toast('已取消', 'info');
  };

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5">思维导图</h2>

        <div className="flex gap-1.5 mb-4">
          {([
            { key: 'text' as InputMode, label: '输入内容' },
            { key: 'video' as InputMode, label: '从视频生成' },
          ]).map((m) => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${
                mode === m.key
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border-light)]'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          {mode === 'text' ? (
            <>
              <textarea
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
                placeholder={'粘贴任意文本内容，AI 将自动提炼生成思维导图\n\n例如：课程笔记、文章摘要、会议纪要等'}
                rows={14}
                className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20 resize-none"
              />
              <button
                onClick={handleTextGenerate}
                disabled={!textContent.trim() || textLoading}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
              >
                {textLoading ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                {textLoading ? '生成中...' : '生成思维导图'}
              </button>
              <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
                AI 会分析文本结构，自动提炼关键信息并生成可视化思维导图
              </p>
            </>
          ) : (
            <>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="粘贴视频链接 (YouTube, Bilibili...)"
                className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20"
                disabled={videoLoading}
              />

              {videoLoading ? (
                <button
                  onClick={handleCancelVideo}
                  className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
                >
                  <Square size={13} />
                  取消生成
                </button>
              ) : (
                <button
                  onClick={handleVideoGenerate}
                  disabled={!url.trim()}
                  className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
                >
                  <Play size={13} />
                  生成
                </button>
              )}
              <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
                下载视频 → 转录 → 直接生成思维导图，跳过摘要等步骤，更快
              </p>
            </>
          )}
        </div>

        {videoLoading && (
          <div className="mt-5 space-y-3">
            <ProgressBar progress={progress} />
            {statusMessage && (
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                <Loader2 size={12} className="animate-spin" />
                {statusMessage}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-hidden relative">
        {mindmapContent ? (
          <Suspense fallback={<p className="text-sm text-[var(--color-text-muted)] text-center py-12">加载思维导图...</p>}>
            <MarkmapView content={mindmapContent} className="absolute inset-0" />
          </Suspense>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-4">
              <BrainCircuit size={24} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">
              {mode === 'text' ? '粘贴文本内容，AI 生成思维导图' : '输入视频链接，自动生成思维导图'}
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              {mode === 'text' ? '支持任意文本：笔记、文章、会议记录等' : '支持 YouTube、Bilibili 等平台'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
