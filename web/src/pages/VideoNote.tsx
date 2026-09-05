import { useState, useCallback, useRef, useEffect, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { postFormData, fetchJSON, postJSON, deleteAPI, downloadFile, extractBilibiliUrl, proxyImageUrl, createSSE } from '../api/client';
import { useTaskProgress } from '../hooks/useTaskProgress';
import { monitorProgress } from '../api/progress';
import type { ProgressConnection } from '../api/progress';
import { getArtifactFilename, readStoredId, writeStoredId } from '../utils/taskRecovery';
import ProgressBar from '../components/ProgressBar';
import ProgressSteps from '../components/ProgressSteps';
import { SUBTITLE_STEPS } from '../components/progressStepData';
import MarkdownRenderer from '../components/MarkdownRenderer';
import Modal from '../components/Modal';
import { toast } from '../components/toastStore';
import type { TaskStatus, VideoInfo, BatchStatus, BatchTaskInfo, ScanResult, ScannedFile, PlaylistInfo } from '../types';
import { Play, Download, Square, Sparkles, BrainCircuit, List, CheckCircle2, XCircle, Loader2, Clock, FolderSearch, Layers } from 'lucide-react';

const MarkmapView = lazy(() => import('../components/MarkmapView'));
const noteTaskKey = 'vinote.note.task-id';
const batchTaskKey = 'vinote.note.batch-id';
const focusedTaskKey = 'vinote.note.focused-id';

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
  if (/字幕.*检查|检查.*字幕|subtitle.*check/i.test(msg)) return 'subtitle';
  if (/字幕.*提取|字幕.*成功|跳过.*下载|subtitle.*extract/i.test(msg)) return 'subtitle_done';
  if (/下载|download/i.test(msg)) return 'download';
  if (/转录|transcri|whisper|ASR|从视频字幕中提取/i.test(msg)) return 'transcribe';
  if (/优化|optimi|整理/i.test(msg)) return 'optimize';
  if (/总结|summar|摘要|提炼/i.test(msg)) return 'summarize';
  if (/完成|complet|所有处理/i.test(msg)) return 'complete';
  return '';
}

function BatchTaskStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 size={14} className="text-green-500 shrink-0" />;
    case 'error':
      return <XCircle size={14} className="text-red-500 shrink-0" />;
    case 'processing':
      return <Loader2 size={14} className="text-[var(--color-accent)] animate-spin shrink-0" />;
    case 'cancelled':
      return <Square size={14} className="text-amber-500 shrink-0" />;
    default:
      return <Clock size={14} className="text-[var(--color-text-muted)] shrink-0" />;
  }
}

function batchTaskStatusText(task: BatchTaskInfo): string {
  if (task.status === 'completed') return '已完成';
  if (task.status === 'error') return '失败';
  if (task.status === 'cancelled') return '已取消';
  if (task.status === 'queued') return task.message || '排队中';
  return task.message || '处理中';
}

export default function VideoNote() {
  const navigate = useNavigate();
  const [isBatch, setIsBatch] = useState(() => {
    const batch = readStoredId(batchTaskKey);
    return Boolean(batch && (!readStoredId(noteTaskKey) || readStoredId(focusedTaskKey) === batch));
  });
  const [input, setInput] = useState('');
  const [batchInput, setBatchInput] = useState('');
  const [language, setLanguage] = useState('zh');
  const [preview, setPreview] = useState<VideoInfo | null>(null);
  const [taskId, setTaskId] = useState<string | null>(() => readStoredId(noteTaskKey));
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [loading, setLoading] = useState(() => Boolean(readStoredId(noteTaskKey)));
  const [activeTab, setActiveTab] = useState<TabKey>('script');
  const [currentStep, setCurrentStep] = useState('');
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [useSubtitleFlow, setUseSubtitleFlow] = useState(false);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [selectedQuality, setSelectedQuality] = useState<string | null>(null);
  const [downloadId, setDownloadId] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [downloadStatus, setDownloadStatus] = useState<'idle' | 'downloading' | 'completed' | 'error'>('idle');
  const [downloadSpeed, setDownloadSpeed] = useState('');
  const downloadSSERef = useRef<EventSource | null>(null);
  const previousTaskStatus = useRef<string | null>(null);

  // Batch state
  const [batchId, setBatchId] = useState<string | null>(() => readStoredId(batchTaskKey));
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
  const [batchLoading, setBatchLoading] = useState(() => Boolean(readStoredId(batchTaskKey)));
  const [selectedBatchTask, setSelectedBatchTask] = useState<string | null>(null);
  const [batchTaskContent, setBatchTaskContent] = useState<TaskStatus | null>(null);
  const [batchConnection, setBatchConnection] = useState<ProgressConnection>('checking');

  // Directory scan state
  const [showDirScan, setShowDirScan] = useState(false);
  const [dirPath, setDirPath] = useState('');
  const [recursive, setRecursive] = useState(false);
  const [scannedFiles, setScannedFiles] = useState<ScannedFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [scanning, setScanning] = useState(false);
  const [playlist, setPlaylist] = useState<PlaylistInfo | null>(null);
  const [playlistLoading, setPlaylistLoading] = useState(false);
  const [selectedPlaylistUrls, setSelectedPlaylistUrls] = useState<Set<string>>(new Set());

  const handleTaskUpdate = useCallback((t: TaskStatus) => {
    setTask(t);
    const step = stepFromMessage(t.message || '');
    if (step === 'subtitle_done') setUseSubtitleFlow(true);
    if (step) {
      const mapped = step === 'subtitle' ? 'download' : step === 'subtitle_done' ? 'transcribe' : step;
      setCurrentStep(mapped);
      const steps = ['download', 'transcribe', 'optimize', 'summarize', 'complete'];
      setCompletedSteps(steps.slice(0, steps.indexOf(mapped)));
    }
    setLoading(t.status === 'queued' || t.status === 'processing');
    if (t.status === 'completed') {
      setCompletedSteps(['download', 'transcribe', 'optimize', 'summarize', 'complete']);
      setCurrentStep('');
      if (previousTaskStatus.current === 'processing' || previousTaskStatus.current === 'queued') {
        toast(t.warnings?.length ? '笔记已生成，部分 AI 能力已降级' : '笔记生成完成！', t.warnings?.length ? 'info' : 'success');
      }
    } else if (t.status === 'error' && previousTaskStatus.current !== 'error') {
      toast(t.error || '生成失败', 'error');
    }
    previousTaskStatus.current = t.status;
  }, []);
  const handleTaskUnavailable = useCallback((error: Error) => {
    writeStoredId(noteTaskKey, null);
    setTaskId(null);
    setTask(null);
    setLoading(false);
    toast(error.message, 'error');
  }, []);
  const taskConnection = useTaskProgress(taskId, handleTaskUpdate, handleTaskUnavailable);

  // A serial poll also restores batches after navigation or reload.
  useEffect(() => {
    if (!batchId) return;
    let wasProcessing = false;
    return monitorProgress<BatchStatus>({
      load: (signal) => fetchJSON(`/api/batch-status/${encodeURIComponent(batchId)}`, { signal }),
      isTerminal: (data) => data.processing === 0,
      onUpdate: (data) => {
        setBatchStatus(data);
        setBatchLoading(data.processing > 0);
        if (wasProcessing && data.processing === 0) {
          toast(`批量处理结束: ${data.completed} 完成, ${data.failed} 失败, ${data.cancelled} 取消`, data.failed > 0 ? 'error' : data.cancelled > 0 ? 'info' : 'success');
        }
        wasProcessing = data.processing > 0;
      },
      onConnectionChange: setBatchConnection,
      onUnavailable: (error) => {
        writeStoredId(batchTaskKey, null);
        setBatchId(null);
        setBatchStatus(null);
        setBatchLoading(false);
        toast(error.message, 'error');
      },
    });
  }, [batchId]);

  useEffect(() => () => downloadSSERef.current?.close(), []);

  // ── Batch handlers ────────────────────────────────
  const handleBatchSubmit = async () => {
    const urls = playlist
      ? Array.from(selectedPlaylistUrls)
      : batchInput.split('\n').map((l) => l.trim()).filter(Boolean);
    if (urls.length === 0) return;
    if (urls.length > 20) { toast('单次最多支持20个', 'error'); return; }
    setBatchLoading(true); setBatchStatus(null); setSelectedBatchTask(null); setBatchTaskContent(null);
    try {
      const res = await postJSON<{ batch_id: string; task_ids: string[]; total: number }>(
        '/api/batch-process', { urls, summary_language: language },
      );
      writeStoredId(batchTaskKey, res.batch_id);
      writeStoredId(focusedTaskKey, res.batch_id);
      setBatchId(res.batch_id);
      toast(`已创建批量任务: ${res.total} 个`, 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : '批量提交失败', 'error');
      setBatchLoading(false);
    }
  };

  const handleCancelBatch = async () => {
    if (!batchId) return;
    try {
      await deleteAPI(`/api/batch/${batchId}`);
      setBatchLoading(false);
      toast('批量任务已取消', 'info');
      fetchJSON<BatchStatus>(`/api/batch-status/${batchId}`)
        .then(setBatchStatus)
        .catch((error) => toast(error instanceof Error ? error.message : '刷新批次状态失败', 'error'));
    } catch (error) {
      toast(error instanceof Error ? error.message : '取消批量任务失败', 'error');
    }
  };

  const handleExpandPlaylist = async () => {
    const url = extractBilibiliUrl(batchInput.trim());
    if (!url) return;
    setPlaylistLoading(true);
    try {
      const data = await postJSON<PlaylistInfo>('/api/playlists/expand', { url });
      setPlaylist(data);
      setSelectedPlaylistUrls(new Set(data.entries.slice(0, 20).map((entry) => entry.url)));
      toast(`已解析 ${data.total} 个视频，请选择本次处理内容`, 'success');
    } catch (error) {
      setPlaylist(null);
      setSelectedPlaylistUrls(new Set());
      toast(error instanceof Error ? error.message : '合集解析失败', 'error');
    } finally {
      setPlaylistLoading(false);
    }
  };

  const togglePlaylistEntry = (url: string) => {
    setSelectedPlaylistUrls((previous) => {
      const next = new Set(previous);
      if (next.has(url)) next.delete(url);
      else if (next.size < 20) next.add(url);
      else toast('单次最多选择20个视频', 'error');
      return next;
    });
  };

  const handleScanDir = async () => {
    if (!dirPath.trim()) return;
    setScanning(true); setScannedFiles([]); setSelectedFiles(new Set());
    try {
      const res = await postJSON<ScanResult>('/api/scan-directory', { directory: dirPath.trim(), recursive });
      setScannedFiles(res.files);
      setSelectedFiles(new Set(res.files.map((f) => f.path)));
      toast(res.files.length === 0 ? '未找到支持的媒体文件' : `找到 ${res.files.length} 个媒体文件`, res.files.length === 0 ? 'info' : 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : '扫描目录失败', 'error');
    } finally { setScanning(false); }
  };

  const handleBatchFromScan = async () => {
    const paths = Array.from(selectedFiles);
    if (paths.length === 0) return;
    if (paths.length > 20) { toast('单次最多支持20个文件', 'error'); return; }
    setBatchLoading(true); setBatchStatus(null); setSelectedBatchTask(null); setBatchTaskContent(null);
    try {
      const res = await postJSON<{ batch_id: string; task_ids: string[]; total: number }>(
        '/api/batch-process', { urls: paths, summary_language: language },
      );
      writeStoredId(batchTaskKey, res.batch_id);
      writeStoredId(focusedTaskKey, res.batch_id);
      setBatchId(res.batch_id);
      toast(`已创建批量任务: ${res.total} 个文件`, 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : '批量提交失败', 'error');
      setBatchLoading(false);
    }
  };

  const toggleFileSelection = (path: string) => {
    setSelectedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const toggleAllFiles = () => {
    setSelectedFiles(selectedFiles.size === scannedFiles.length ? new Set() : new Set(scannedFiles.map((f) => f.path)));
  };

  const handleSelectBatchTask = async (bt: BatchTaskInfo) => {
    if (bt.status !== 'completed') return;
    setSelectedBatchTask(bt.task_id);
    try {
      const data = await fetchJSON<TaskStatus>(`/api/task-status/${bt.task_id}`);
      setBatchTaskContent(data);
      setActiveTab('script');
    } catch (error) {
      toast(error instanceof Error ? error.message : '加载笔记失败', 'error');
    }
  };

  // ── Single handlers ───────────────────────────────
  const handleGenerate = async () => {
    const url = extractBilibiliUrl(input.trim());
    if (!url) return;
    // 尝试预览（仅在线URL有效，本地路径会静默失败）
    if (!preview) {
      fetchJSON<{ success: boolean; data: VideoInfo }>(
        `/api/preview-video?url=${encodeURIComponent(url)}`,
      ).then((res) => setPreview(res.data)).catch(() => {});
    }
    setLoading(true); setTask(null); setCurrentStep(''); setCompletedSteps([]); setUseSubtitleFlow(false);
    previousTaskStatus.current = 'processing';
    try {
      const res = await postFormData<{ task_id: string }>('/api/process-video', { url, summary_language: language });
      writeStoredId(noteTaskKey, res.task_id);
      writeStoredId(focusedTaskKey, res.task_id);
      setTaskId(res.task_id);
    } catch (e) {
      toast(e instanceof Error ? e.message : '生成失败', 'error'); setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    try {
      await deleteAPI(`/api/task/${taskId}`);
      setTaskId(null); writeStoredId(noteTaskKey, null); setLoading(false);
      setTask((prev) => (prev ? { ...prev, status: 'cancelled', message: '已取消' } : null));
      toast('已取消', 'info');
    } catch (error) {
      toast(error instanceof Error ? error.message : '取消任务失败', 'error');
    }
  };

  const handleDownloadFile = useCallback(async (filename: string) => {
    try {
      await downloadFile(filename);
      toast('文件已下载', 'success');
    } catch (error) {
      toast(error instanceof Error ? error.message : '下载失败', 'error');
    }
  }, []);

  const handleStartDownload = async () => {
    if (!selectedQuality || !input.trim()) return;
    const url = extractBilibiliUrl(input.trim());
    setShowDownloadModal(false); setDownloadStatus('downloading'); setDownloadProgress(0);
    try {
      const res = await postJSON<{ download_id: string }>('/api/start-download', { url, quality: selectedQuality });
      setDownloadId(res.download_id);
      const es = createSSE(`/api/download-stream/${res.download_id}`, (data) => {
        const d = data as { progress?: number; speed?: string; status?: string; error?: string };
        if (d.progress != null) setDownloadProgress(d.progress);
        if (d.speed) setDownloadSpeed(d.speed);
        if (d.status === 'completed') {
          es.close(); setDownloadStatus('completed'); toast('下载完成', 'success');
          window.location.href = `/api/get-download/${res.download_id}`;
          setTimeout(() => setDownloadStatus('idle'), 3000);
        } else if (d.status === 'error') {
          es.close(); setDownloadStatus('error'); toast(d.error || '下载失败', 'error');
          setTimeout(() => setDownloadStatus('idle'), 3000);
        }
      }, () => { setDownloadStatus('error'); toast('下载连接中断', 'error'); });
      downloadSSERef.current = es;
    } catch (e) {
      toast(e instanceof Error ? e.message : '下载失败', 'error'); setDownloadStatus('idle');
    }
  };

  const handleCancelDownload = async () => {
    if (!downloadId) return;
    try {
      await deleteAPI(`/api/cancel-download/${downloadId}`);
      downloadSSERef.current?.close();
      setDownloadStatus('idle'); setDownloadId(null); toast('下载已取消', 'info');
    } catch (error) {
      toast(error instanceof Error ? error.message : '取消下载失败', 'error');
    }
  };

  const qualityOptions = preview?.formats?.length
    ? preview.formats.map((f: { height: number; quality: string; filesize_string: string }) => ({
        value: `best[height<=${f.height}]`, label: f.quality, size: f.filesize_string,
      }))
    : [{ value: 'best', label: '最佳质量', size: '自动选择' }];

  // Active content for right panel
  const activeTask = (isBatch && batchTaskContent) ? batchTaskContent : task;

  const getTabContent = (key: TabKey): string => {
    if (!activeTask) return '';
    switch (key) {
      case 'script': return activeTask.script || '';
      case 'summary': return activeTask.summary || '';
      case 'mindmap': return activeTask.mindmap || '';
      case 'raw': return activeTask.raw_script || '';
      case 'translation': return activeTask.translation || '';
    }
  };

  const getTabFilename = (key: TabKey): string => {
    return getArtifactFilename(activeTask, key);
  };

  const showCompleted = (isBatch && batchTaskContent?.status === 'completed') || (!isBatch && task?.status === 'completed');

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5">AI视频笔记</h2>

        {/* 单条 / 批量 toggle */}
        <div className="flex items-center gap-2 mb-4">
          <button
            onClick={() => { setIsBatch(false); writeStoredId(focusedTaskKey, taskId); }}
            className={`flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-md font-medium transition-colors ${
              !isBatch
                ? 'bg-[var(--color-text)] text-white'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
            }`}
          >
            <Play size={11} />
            单条
          </button>
          <button
            onClick={() => { setIsBatch(true); writeStoredId(focusedTaskKey, batchId); }}
            className={`flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-md font-medium transition-colors ${
              isBatch
                ? 'bg-[var(--color-text)] text-white'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
            }`}
          >
            <Layers size={11} />
            批量
          </button>
        </div>

        {/* ── 输入区域 ──────────────────────────────── */}
        <div className="space-y-3">
          {isBatch ? (
            /* ── 批量输入 ─────────────────────────── */
            <>
              {/* 目录扫描 */}
              <button
                onClick={() => setShowDirScan(!showDirScan)}
                className="flex items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline"
              >
                <FolderSearch size={12} />
                {showDirScan ? '收起目录扫描' : '扫描本地目录'}
              </button>

              {showDirScan && (
                <div className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] space-y-2">
                  <div className="flex gap-1.5">
                    <input
                      value={dirPath}
                      onChange={(e) => setDirPath(e.target.value)}
                      placeholder="输入目录路径，如 /path/to/课程"
                      className="flex-1 border border-[var(--color-border)] rounded-md px-2.5 py-1.5 text-xs focus:outline-none focus:border-[var(--color-accent)]"
                    />
                    <button
                      onClick={handleScanDir}
                      disabled={scanning || !dirPath.trim()}
                      className="px-3 py-1.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-md hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors shrink-0"
                    >
                      {scanning ? <Loader2 size={12} className="animate-spin" /> : '扫描'}
                    </button>
                  </div>
                  <label className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)] cursor-pointer">
                    <input type="checkbox" checked={recursive} onChange={(e) => setRecursive(e.target.checked)}
                      className="rounded border-[var(--color-border)]" />
                    包含子目录
                  </label>

                  {scannedFiles.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <p className="text-[11px] text-[var(--color-text-secondary)]">
                          已选 {selectedFiles.size}/{scannedFiles.length} 个文件
                        </p>
                        <button onClick={toggleAllFiles} className="text-[11px] text-[var(--color-accent)] hover:underline">
                          {selectedFiles.size === scannedFiles.length ? '取消全选' : '全选'}
                        </button>
                      </div>
                      <div className="max-h-[160px] overflow-y-auto space-y-0.5">
                        {scannedFiles.map((f) => (
                          <label key={f.path}
                            className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-[var(--color-surface)] cursor-pointer text-xs">
                            <input type="checkbox" checked={selectedFiles.has(f.path)}
                              onChange={() => toggleFileSelection(f.path)} className="rounded border-[var(--color-border)]" />
                            <span className="flex-1 truncate text-[var(--color-text)]">{f.name}</span>
                            <span className="text-[10px] text-[var(--color-text-muted)] shrink-0">{f.size_display}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 批量文本输入 */}
              {!(showDirScan && scannedFiles.length > 0) && (
                <>
                  <textarea
                    value={batchInput}
                    onChange={(e) => { setBatchInput(e.target.value); setPlaylist(null); }}
                    placeholder={'粘贴合集链接，或每行一个视频链接/本地路径'}
                    rows={4}
                    className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20 resize-none font-mono"
                  />
                  <button
                    onClick={handleExpandPlaylist}
                    disabled={!batchInput.trim() || batchInput.includes('\n') || playlistLoading}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs text-[var(--color-accent)] border border-[var(--color-accent)]/30 rounded-lg hover:bg-[var(--color-accent-light)] disabled:opacity-40 transition-colors"
                  >
                    {playlistLoading ? <Loader2 size={12} className="animate-spin" /> : <Layers size={12} />}
                    {playlistLoading ? '正在解析合集...' : '解析合集/播放列表'}
                  </button>
                </>
              )}

              {playlist && (
                <div className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-[var(--color-text)] truncate">{playlist.title}</p>
                    <span className="text-[10px] text-[var(--color-text-muted)] shrink-0">
                      已选 {selectedPlaylistUrls.size}/{playlist.total}
                    </span>
                  </div>
                  <div className="max-h-52 overflow-y-auto space-y-0.5">
                    {playlist.entries.map((entry) => (
                      <label key={`${entry.id}-${entry.index}`} className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-[var(--color-surface)] cursor-pointer">
                        <input type="checkbox" checked={selectedPlaylistUrls.has(entry.url)} onChange={() => togglePlaylistEntry(entry.url)} />
                        <span className="text-[10px] text-[var(--color-text-muted)] w-6 shrink-0">{entry.index}</span>
                        <span className="text-xs text-[var(--color-text)] truncate">{entry.title}</span>
                      </label>
                    ))}
                  </div>
                  {playlist.truncated && <p className="text-[10px] text-amber-600">合集较大，当前显示前100条</p>}
                </div>
              )}

              <p className="text-[11px] text-[var(--color-text-muted)]">
                {showDirScan && scannedFiles.length > 0
                  ? `已选 ${selectedFiles.size} 个文件（最多20个）`
                  : playlist
                    ? `已从合集中选择 ${selectedPlaylistUrls.size} 条（最多20条）`
                    : `${batchInput.split('\n').filter((l) => l.trim()).length} 条（最多20条）· 自动识别在线链接和本地路径`}
              </p>
            </>
          ) : (
            /* ── 单条输入 ─────────────────────────── */
            <>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="粘贴视频链接或本地文件路径"
                className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20"
              />
              <p className="text-[11px] text-[var(--color-text-muted)]">
                支持 YouTube/Bilibili 链接、本地 mp4/mkv/mp3 等文件路径
              </p>

              {preview && (
                <div className="p-3 bg-[var(--color-bg)] rounded-lg">
                  {preview.thumbnail && (
                    <img src={proxyImageUrl(preview.thumbnail)} alt=""
                      className="w-full h-32 object-cover rounded-md mb-2" />
                  )}
                  <p className="text-sm font-medium text-[var(--color-text)] line-clamp-2">{preview.title}</p>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                    {preview.uploader && `${preview.uploader} · `}
                    {preview.duration > 0 && `${Math.floor(preview.duration / 60)}:${String(preview.duration % 60).padStart(2, '0')}`}
                  </p>
                  {preview.description && (
                    <p className="text-xs text-[var(--color-text-muted)] mt-1 line-clamp-3">{preview.description}</p>
                  )}
                </div>
              )}
            </>
          )}

          {/* 语言选择（共享） */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-[var(--color-text-secondary)] shrink-0">摘要语言</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}
              className="flex-1 border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[var(--color-accent)]">
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
          </div>

          {/* 操作按钮 */}
          {isBatch ? (
            batchLoading ? (
              <button onClick={handleCancelBatch}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
                <Square size={13} /> 取消批量任务
              </button>
            ) : (
              <button
                onClick={showDirScan && scannedFiles.length > 0 ? handleBatchFromScan : handleBatchSubmit}
                disabled={showDirScan && scannedFiles.length > 0
                  ? selectedFiles.size === 0
                  : playlist ? selectedPlaylistUrls.size === 0 : !batchInput.trim()}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
              >
                <><List size={13} />
                  {showDirScan && scannedFiles.length > 0
                    ? `批量处理 ${selectedFiles.size} 个文件`
                    : '批量生成笔记'}
                </>
              </button>
            )
          ) : loading ? (
            <button onClick={handleCancel}
              className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
              <Square size={13} /> 取消生成
            </button>
          ) : (
            <button onClick={handleGenerate} disabled={!input.trim()}
              className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors">
              <Play size={13} /> 生成笔记
            </button>
          )}

          {/* 下载视频按钮（仅单条模式+有预览时） */}
          {!isBatch && preview && (
            downloadStatus === 'downloading' ? (
              <button onClick={handleCancelDownload}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-xs text-red-600 border border-red-200 bg-red-50 rounded-lg hover:bg-red-100 transition-colors">
                <Square size={13} />
                取消下载 {Math.round(downloadProgress)}%{downloadSpeed && ` · ${downloadSpeed}`}
              </button>
            ) : (
              <button onClick={() => { setSelectedQuality(null); setShowDownloadModal(true); }}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2 text-xs text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-bg)] transition-colors">
                <Download size={13} /> 下载视频
              </button>
            )
          )}
        </div>

        {/* ── 进度区域（共享） ──────────────────────── */}
        {((isBatch && batchLoading && batchConnection === 'retrying') || (!isBatch && loading && taskConnection === 'retrying')) && (
          <p role="status" className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            状态连接暂时中断，正在自动恢复。任务仍可能在后台运行，请勿重复提交。
          </p>
        )}
        {!isBatch && loading && taskConnection === 'polling' && (
          <p role="status" className="mt-4 text-xs text-[var(--color-text-secondary)]">已恢复状态查询，正在同步任务进度。</p>
        )}
        {!isBatch && (loading || task) && (
          <div className="mt-5 space-y-3">
            <ProgressBar progress={task?.progress ?? 0} />
            <ProgressSteps currentStep={currentStep} completedSteps={completedSteps} steps={useSubtitleFlow ? SUBTITLE_STEPS : undefined} />
            {task?.message && <p className="text-xs text-[var(--color-text-secondary)]">{task.message}</p>}
          </div>
        )}

        {/* 批量进度 */}
        {isBatch && batchStatus && (
          <div className="mt-5 space-y-3">
            <div className="grid grid-cols-5 gap-2 text-center">
              <div className="bg-[var(--color-bg)] rounded-lg p-2">
                <p className="text-lg font-semibold text-[var(--color-text)]">{batchStatus.total}</p>
                <p className="text-[10px] text-[var(--color-text-muted)]">总计</p>
              </div>
              <div className="bg-[var(--color-bg)] rounded-lg p-2">
                <p className="text-lg font-semibold text-green-600">{batchStatus.completed}</p>
                <p className="text-[10px] text-[var(--color-text-muted)]">完成</p>
              </div>
              <div className="bg-[var(--color-bg)] rounded-lg p-2">
                <p className="text-lg font-semibold text-[var(--color-accent)]">{batchStatus.processing}</p>
                <p className="text-[10px] text-[var(--color-text-muted)]">处理中</p>
              </div>
              <div className="bg-[var(--color-bg)] rounded-lg p-2">
                <p className="text-lg font-semibold text-red-500">{batchStatus.failed}</p>
                <p className="text-[10px] text-[var(--color-text-muted)]">失败</p>
              </div>
              <div className="bg-[var(--color-bg)] rounded-lg p-2">
                <p className="text-lg font-semibold text-amber-500">{batchStatus.cancelled}</p>
                <p className="text-[10px] text-[var(--color-text-muted)]">取消</p>
              </div>
            </div>

            <ProgressBar progress={batchStatus.total > 0 ? Math.round(((batchStatus.completed + batchStatus.failed + batchStatus.cancelled) / batchStatus.total) * 100) : 0} />

            <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
              {batchStatus.tasks.map((bt) => (
                <button key={bt.task_id} onClick={() => handleSelectBatchTask(bt)} disabled={bt.status !== 'completed'}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-colors ${
                    selectedBatchTask === bt.task_id
                      ? 'bg-[var(--color-accent-light)] border border-[var(--color-accent)]'
                      : bt.status === 'completed'
                        ? 'bg-[var(--color-bg)] hover:bg-[var(--color-border-light)] border border-transparent'
                        : 'bg-[var(--color-bg)] border border-transparent opacity-70'
                  }`}>
                  <BatchTaskStatusIcon status={bt.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-[var(--color-text)] truncate">{bt.video_title}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      {bt.status === 'processing' && (
                        <div className="flex-1 h-1 bg-[var(--color-border)] rounded-full overflow-hidden">
                          <div className="h-full bg-[var(--color-accent)] rounded-full transition-all duration-300"
                            style={{ width: `${bt.progress}%` }} />
                        </div>
                      )}
                      <p className="text-[10px] text-[var(--color-text-muted)] shrink-0">
                        {batchTaskStatusText(bt)}
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── 右侧面板（共享） ───────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6">
        {showCompleted && activeTask ? (
          <div>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-[var(--color-text)] truncate pr-4">
                {activeTask.video_title || '笔记结果'}
              </h2>
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => navigate(`/cards?taskId=${activeTask.short_id}&field=summary`)}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-bg)] hover:text-[var(--color-accent)] transition-colors">
                  <Sparkles size={12} /> 生成卡片
                </button>
                <button onClick={() => navigate(`/mindmap?taskId=${activeTask.short_id}&field=summary`)}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-bg)] hover:text-[var(--color-accent)] transition-colors">
                  <BrainCircuit size={12} /> 生成导图
                </button>
              </div>
            </div>

            {activeTask.warnings && activeTask.warnings.length > 0 && (
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                <p className="font-medium mb-1">部分 AI 能力已降级，以下内容使用备用流程生成：</p>
                <ul className="list-disc pl-4 space-y-0.5">
                  {activeTask.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              </div>
            )}

            <div className="flex border-b border-[var(--color-border)] mb-4 gap-0">
              {TABS.map((tab) => {
                const content = getTabContent(tab.key);
                const filename = getTabFilename(tab.key);
                if (!content && tab.key !== 'script') return null;
                return (
                  <div key={tab.key}
                    className={`flex items-center border-b-2 transition-colors ${
                      activeTab === tab.key
                        ? 'border-[var(--color-accent)] text-[var(--color-accent)]'
                        : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text)]'
                    }`}>
                    <button onClick={() => setActiveTab(tab.key)} className="px-4 py-2.5 pr-2 text-xs font-medium">
                      {tab.label}
                    </button>
                    {filename && content && (
                      <button onClick={(e) => { e.stopPropagation(); handleDownloadFile(filename); }}
                        className="py-2.5 pr-4 text-[var(--color-text-muted)] hover:text-[var(--color-accent)]" title="下载">
                        <Download size={12} />
                      </button>
                    )}
                  </div>
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
        ) : (!isBatch && task?.status === 'error') ? (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {task.error || '处理失败'}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-4">
              <Play size={24} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">
              {isBatch ? '批量输入视频链接或本地路径，一键生成多篇笔记' : '输入视频链接或本地路径，生成AI笔记'}
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              支持 YouTube、Bilibili 等平台链接，以及 mp4/mkv/mp3 等本地文件
            </p>
          </div>
        )}
      </div>

      <Modal open={showDownloadModal} onClose={() => setShowDownloadModal(false)} title="选择下载质量">
        <div className="space-y-2 mb-4">
          {qualityOptions.map((opt: { value: string; label: string; size: string }) => (
            <button key={opt.value} onClick={() => setSelectedQuality(opt.value)}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border text-sm transition-colors ${
                selectedQuality === opt.value
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)] text-[var(--color-accent)]'
                  : 'border-[var(--color-border)] hover:bg-[var(--color-bg)] text-[var(--color-text-secondary)]'
              }`}>
              <span className="font-medium">{opt.label}</span>
              <span className="text-xs text-[var(--color-text-muted)]">{opt.size}</span>
            </button>
          ))}
        </div>
        <button onClick={handleStartDownload} disabled={!selectedQuality}
          className="w-full py-2.5 text-sm font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors">
          开始下载
        </button>
      </Modal>
    </div>
  );
}
