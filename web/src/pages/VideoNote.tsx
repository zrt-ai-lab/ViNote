import { useState, useCallback, useRef, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { postFormData, fetchJSON, postJSON, deleteAPI, downloadFile, extractBilibiliUrl, proxyImageUrl, createSSE } from '../api/client';
import { useSSE } from '../hooks/useSSE';
import ProgressBar from '../components/ProgressBar';
import ProgressSteps from '../components/ProgressSteps';
import MarkdownRenderer from '../components/MarkdownRenderer';
import Modal from '../components/Modal';
import { toast } from '../components/Toast';
import type { TaskStatus, VideoInfo } from '../types';
import { Play, Download, Square, Sparkles, BrainCircuit } from 'lucide-react';

const MarkmapView = lazy(() => import('../components/MarkmapView'));

const LANGUAGES = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
  { value: 'ko', label: '한국어' },
  { value: 'fr', label: 'Français' },
  { value: 'de', label: 'Deutsch' },
  { value: 'es', label: 'Español' },
  { value: 'ru', label: 'Русский' },
  { value: 'pt', label: 'Português' },
  { value: 'ar', label: 'العربية' },
  { value: 'hi', label: 'हिंदी' },
];

const TABS = [
  { key: 'script', label: '完整笔记' },
  { key: 'summary', label: '精华摘要' },
  { key: 'mindmap', label: '思维导图' },
  { key: 'raw', label: '原文转录' },
  { key: 'translation', label: '翻译版本' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

function stepFromMessage(msg: string): string {
  if (/下载|download/i.test(msg)) return 'download';
  if (/转录|transcri|whisper/i.test(msg)) return 'transcribe';
  if (/优化|optimi/i.test(msg)) return 'optimize';
  if (/总结|summar/i.test(msg)) return 'summarize';
  if (/完成|complet/i.test(msg)) return 'complete';
  return '';
}

export default function VideoNote() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'url' | 'local'>('url');
  const [input, setInput] = useState('');
  const [language, setLanguage] = useState('zh');
  const [preview, setPreview] = useState<VideoInfo | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('script');
  const [currentStep, setCurrentStep] = useState('');
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [selectedQuality, setSelectedQuality] = useState<string | null>(null);
  const [downloadId, setDownloadId] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [downloadStatus, setDownloadStatus] = useState<'idle' | 'downloading' | 'completed' | 'error'>('idle');
  const [downloadSpeed, setDownloadSpeed] = useState('');
  const downloadSSERef = useRef<EventSource | null>(null);
  const { connect, disconnect } = useSSE();

  const handleGenerate = async () => {
    const url = mode === 'url' ? extractBilibiliUrl(input.trim()) : input.trim();
    if (!url) return;
    if (mode === 'url' && !preview) {
      fetchJSON<{ success: boolean; data: VideoInfo }>(
        `/api/preview-video?url=${encodeURIComponent(url)}`,
      ).then((res) => setPreview(res.data)).catch(() => {});
    }
    setLoading(true);
    setTask(null);
    setCurrentStep('');
    setCompletedSteps([]);
    try {
      const res = await postFormData<{ task_id: string }>('/api/process-video', {
        url,
        summary_language: language,
      });
      setTaskId(res.task_id);
      connect(`/api/task-stream/${res.task_id}`, {
        onMessage: (data) => {
          const t = data as TaskStatus;
          setTask(t);
          const step = stepFromMessage(t.message || '');
          if (step) {
            setCurrentStep(step);
            setCompletedSteps(() => {
              const steps = ['download', 'transcribe', 'optimize', 'summarize', 'complete'];
              const idx = steps.indexOf(step);
              return steps.slice(0, idx);
            });
          }
          if (t.status === 'completed') {
            setCompletedSteps(['download', 'transcribe', 'optimize', 'summarize', 'complete']);
            setCurrentStep('');
            disconnect();
            setLoading(false);
            toast('笔记生成完成！', 'success');
          } else if (t.status === 'error') {
            disconnect();
            setLoading(false);
            toast(t.error || '生成失败', 'error');
          }
        },
        onError: () => {
          setLoading(false);
          toast('连接中断', 'error');
        },
      });
    } catch (e) {
      toast(e instanceof Error ? e.message : '生成失败', 'error');
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    try {
      await deleteAPI(`/api/task/${taskId}`);
      disconnect();
      setLoading(false);
      setTask((prev) => (prev ? { ...prev, status: 'cancelled', message: '已取消' } : null));
      toast('已取消', 'info');
    } catch {
      /* ignore */
    }
  };

  const handleDownloadFile = useCallback((filename: string) => {
    downloadFile(filename);
    toast('开始下载', 'success');
  }, []);

  const handleStartDownload = async () => {
    if (!selectedQuality || !input.trim()) return;
    const url = extractBilibiliUrl(input.trim());
    setShowDownloadModal(false);
    setDownloadStatus('downloading');
    setDownloadProgress(0);
    try {
      const res = await postJSON<{ download_id: string }>('/api/start-download', {
        url,
        quality: selectedQuality,
      });
      setDownloadId(res.download_id);
      const es = createSSE(
        `/api/download-stream/${res.download_id}`,
        (data) => {
          const d = data as { progress?: number; speed?: string; status?: string; error?: string };
          if (d.progress != null) setDownloadProgress(d.progress);
          if (d.speed) setDownloadSpeed(d.speed);
          if (d.status === 'completed') {
            es.close();
            setDownloadStatus('completed');
            toast('下载完成', 'success');
            window.location.href = `/api/get-download/${res.download_id}`;
            setTimeout(() => setDownloadStatus('idle'), 3000);
          } else if (d.status === 'error') {
            es.close();
            setDownloadStatus('error');
            toast(d.error || '下载失败', 'error');
            setTimeout(() => setDownloadStatus('idle'), 3000);
          }
        },
        () => {
          setDownloadStatus('error');
          toast('下载连接中断', 'error');
        },
      );
      downloadSSERef.current = es;
    } catch (e) {
      toast(e instanceof Error ? e.message : '下载失败', 'error');
      setDownloadStatus('idle');
    }
  };

  const handleCancelDownload = async () => {
    if (!downloadId) return;
    try {
      downloadSSERef.current?.close();
      await deleteAPI(`/api/cancel-download/${downloadId}`);
      setDownloadStatus('idle');
      setDownloadId(null);
      toast('下载已取消', 'info');
    } catch { /* ignore */ }
  };

  const qualityOptions = preview?.formats?.length
    ? preview.formats.map((f: { height: number; quality: string; filesize_string: string }) => ({
        value: `best[height<=${f.height}]`,
        label: f.quality,
        size: f.filesize_string,
      }))
    : [{ value: 'best', label: '最佳质量', size: '自动选择' }];

  const getTabContent = (key: TabKey): string => {
    if (!task) return '';
    switch (key) {
      case 'script': return task.script || '';
      case 'summary': return task.summary || '';
      case 'mindmap': return task.mindmap || '';
      case 'raw': return task.raw_script || '';
      case 'translation': return task.translation || '';
    }
  };

  const getTabFilename = (key: TabKey): string => {
    if (!task?.short_id || !task?.safe_title) return '';
    const prefix = `${task.short_id}_${task.safe_title}`;
    switch (key) {
      case 'script': return `${prefix}_笔记.md`;
      case 'summary': return `${prefix}_摘要.md`;
      case 'mindmap': return task.mindmap_filename || '';
      case 'raw': return task.raw_script_filename || '';
      case 'translation': return task.translation_filename || '';
    }
  };

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5">AI视频笔记</h2>

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
            placeholder={mode === 'url' ? '粘贴视频链接 (YouTube, Bilibili...)' : '输入本地文件路径'}
            className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20"
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
              {preview.description && (
                <p className="text-xs text-[var(--color-text-muted)] mt-1 line-clamp-3">{preview.description}</p>
              )}
            </div>
          )}

          <div className="flex items-center gap-3">
            <label className="text-xs text-[var(--color-text-secondary)] shrink-0">摘要语言</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="flex-1 border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[var(--color-accent)]"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="flex gap-2">
              <button
                onClick={handleCancel}
                className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
              >
                <Square size={13} />
                取消生成
              </button>
            </div>
          ) : (
            <button
              onClick={handleGenerate}
              disabled={!input.trim()}
              className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
            >
              <Play size={13} />
              生成笔记
            </button>
          )}

          {mode === 'url' && preview && (
            downloadStatus === 'downloading' ? (
              <button
                onClick={handleCancelDownload}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-xs text-red-600 border border-red-200 bg-red-50 rounded-lg hover:bg-red-100 transition-colors"
              >
                <Square size={13} />
                取消下载 {Math.round(downloadProgress)}%{downloadSpeed && ` · ${downloadSpeed}`}
              </button>
            ) : (
              <button
                onClick={() => { setSelectedQuality(null); setShowDownloadModal(true); }}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-xs text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-bg)] transition-colors"
              >
                <Download size={13} />
                下载视频
              </button>
            )
          )}
        </div>

        {(loading || task) && (
          <div className="mt-5 space-y-3">
            <ProgressBar progress={task?.progress ?? 0} />
            <ProgressSteps currentStep={currentStep} completedSteps={completedSteps} />
            {task?.message && (
              <p className="text-xs text-[var(--color-text-secondary)]">{task.message}</p>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {task?.status === 'completed' ? (
          <div>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-[var(--color-text)] truncate pr-4">
                {task.video_title || '笔记结果'}
              </h2>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => navigate(`/cards?taskId=${task.short_id}&field=summary`)}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-bg)] hover:text-[var(--color-accent)] transition-colors"
                >
                  <Sparkles size={12} />
                  生成卡片
                </button>
                <button
                  onClick={() => navigate(`/mindmap?taskId=${task.short_id}&field=summary`)}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-bg)] hover:text-[var(--color-accent)] transition-colors"
                >
                  <BrainCircuit size={12} />
                  生成导图
                </button>
              </div>
            </div>

            <div className="flex border-b border-[var(--color-border)] mb-4 gap-0">
              {TABS.map((tab) => {
                const content = getTabContent(tab.key);
                const filename = getTabFilename(tab.key);
                if (!content && tab.key !== 'script') return null;
                return (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                      activeTab === tab.key
                        ? 'border-[var(--color-accent)] text-[var(--color-accent)]'
                        : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text)]'
                    }`}
                  >
                    {tab.label}
                    {filename && content && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDownloadFile(filename);
                        }}
                        className="text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
                        title="下载"
                      >
                        <Download size={12} />
                      </button>
                    )}
                  </button>
                );
              })}
            </div>

            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-5 min-h-[300px]">
              {activeTab === 'mindmap' && getTabContent('mindmap') ? (
                <Suspense fallback={<p className="text-sm text-[var(--color-text-muted)] text-center py-12">加载思维导图...</p>}>
                  <MarkmapView content={getTabContent('mindmap')} />
                </Suspense>
              ) : getTabContent(activeTab) ? (
                <MarkdownRenderer content={getTabContent(activeTab)} />
              ) : (
                <p className="text-sm text-[var(--color-text-muted)] text-center py-12">暂无内容</p>
              )}
            </div>
          </div>
        ) : task?.status === 'error' ? (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {task.error || '处理失败'}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-4">
              <Play size={24} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">输入视频链接，生成AI笔记</p>
            <p className="text-xs text-[var(--color-text-muted)]">支持 YouTube、Bilibili 等平台</p>
          </div>
        )}
      </div>

      <Modal open={showDownloadModal} onClose={() => setShowDownloadModal(false)} title="选择下载质量">
        <div className="space-y-2 mb-4">
          {qualityOptions.map((opt: { value: string; label: string; size: string }) => (
            <button
              key={opt.value}
              onClick={() => setSelectedQuality(opt.value)}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border text-sm transition-colors ${
                selectedQuality === opt.value
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)] text-[var(--color-accent)]'
                  : 'border-[var(--color-border)] hover:bg-[var(--color-bg)] text-[var(--color-text-secondary)]'
              }`}
            >
              <span className="font-medium">{opt.label}</span>
              <span className="text-xs text-[var(--color-text-muted)]">{opt.size}</span>
            </button>
          ))}
        </div>
        <button
          onClick={handleStartDownload}
          disabled={!selectedQuality}
          className="w-full py-2.5 text-sm font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
        >
          开始下载
        </button>
      </Modal>
    </div>
  );
}
