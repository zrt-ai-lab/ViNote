import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchJSON, postJSON } from '../api/client';
import { toast } from '../components/Toast';
import MarkdownRenderer from '../components/MarkdownRenderer';
import type { CompletedTask, CompletedTasksResponse, Category } from '../types';
import {
  Clock, FileText, MessageCircle, Sparkles, BrainCircuit, Loader2, Eye,
  Trash2, HardDrive, Music, Download, RefreshCw, Archive, AlertTriangle,
  Filter, ChevronLeft, ChevronRight, ArrowUpDown, X, Check,
  Tag,
} from 'lucide-react';
import clsx from 'clsx';

interface FileInfo {
  name: string;
  size: string;
  age_days: number;
}

interface StorageStats {
  notes: { count: number; size: number; size_display: string };
  audio: { count: number; size: number; size_display: string; files: FileInfo[] };
  downloads: { count: number; size: number; size_display: string; files: FileInfo[] };
  backups: { count: number; size: number; size_display: string; files: FileInfo[] };
  other: { count: number; size: number; size_display: string };
  total_size: number;
  total_size_display: string;
}

type ContentField = 'summary' | 'transcript';
type CleanupType = 'audio' | 'downloads' | 'backups' | 'all_notes';
type SortBy = 'created_at' | 'title';

export default function History() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [tasks, setTasks] = useState<CompletedTask[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [contentField, setContentField] = useState<ContentField | null>(null);
  const [content, setContent] = useState('');
  const [loadingContent, setLoadingContent] = useState(false);
  const [storageStats, setStorageStats] = useState<StorageStats | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null);

  // Filters
  const [filterCategory, setFilterCategory] = useState('');
  const [filterTag, setFilterTag] = useState(() => searchParams.get('tag') || '');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortBy>('created_at');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const searchTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Categories
  const [categories, setCategories] = useState<Category[]>([]);

  // Inline tag/category editing
  const [editingTaskTags, setEditingTaskTags] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState('');

  const loadTasks = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', String(pageSize));
    params.set('sort_by', sortBy);
    params.set('sort_order', sortOrder);
    if (filterCategory) params.set('category', filterCategory);
    if (filterTag) params.set('tag', filterTag);
    if (searchQuery) params.set('search', searchQuery);

    fetchJSON<CompletedTasksResponse>(`/api/tasks/completed?${params}`)
      .then((res) => {
        setTasks(res.tasks);
        setTotal(res.total);
      })
      .catch(() => toast('获取历史记录失败', 'error'))
      .finally(() => setLoading(false));
  }, [page, pageSize, sortBy, sortOrder, filterCategory, filterTag, searchQuery]);

  const loadStorageStats = useCallback(() => {
    fetchJSON<StorageStats>('/api/storage/stats')
      .then(setStorageStats)
      .catch(() => {});
  }, []);

  const loadCategories = useCallback(() => {
    fetchJSON<{ categories: Category[] }>('/api/categories')
      .then((res) => setCategories(res.categories))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    loadStorageStats();
    loadCategories();
  }, [loadStorageStats, loadCategories]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [filterCategory, filterTag, searchQuery, sortBy, sortOrder]);

  const handleSearchChange = (value: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setSearchQuery(value), 400);
  };

  // Derived: all unique tags from current result page (for quick filter chips)
  const allTags = Array.from(new Set(tasks.flatMap((t) => t.tags))).sort();

  const handleViewContent = async (task: CompletedTask, field: ContentField) => {
    if (selectedTaskId === task.task_id && contentField === field) {
      setSelectedTaskId(null);
      setContentField(null);
      setContent('');
      return;
    }
    setSelectedTaskId(task.task_id);
    setContentField(field);
    setLoadingContent(true);
    try {
      const res = await fetchJSON<{ content: string }>(`/api/tasks/${task.task_id}/content?field=${field}`);
      setContent(res.content);
    } catch {
      toast('加载内容失败', 'error');
      setContent('');
    } finally {
      setLoadingContent(false);
    }
  };

  const handleCleanup = async (type: CleanupType) => {
    const labels: Record<CleanupType, string> = {
      audio: '音频缓存',
      downloads: '下载文件',
      backups: '备份文件',
      all_notes: '所有笔记和历史记录',
    };
    const label = labels[type];
    const confirmMsg = type === 'all_notes'
      ? `确认清理${label}？这将删除所有笔记文件和任务记录，此操作不可撤销！`
      : `确认清理所有${label}？此操作不可撤销。`;
    if (!confirm(confirmMsg)) return;

    setCleaning(true);
    try {
      const body: Record<string, boolean> = {
        clean_audio: type === 'audio',
        clean_downloads: type === 'downloads',
        clean_backups: type === 'backups',
        clean_all_notes: type === 'all_notes',
      };
      const res = await postJSON<{ deleted_count: number; freed_size_display: string }>(
        '/api/storage/cleanup',
        body,
      );
      toast(`已清理 ${res.deleted_count} 个文件，释放 ${res.freed_size_display}`, 'success');
      loadStorageStats();
      if (type === 'all_notes') {
        setSelectedTaskId(null);
        setContent('');
        setContentField(null);
        loadTasks();
      }
    } catch {
      toast('清理失败', 'error');
    } finally {
      setCleaning(false);
    }
  };

  const handleDeleteTask = async (task: CompletedTask) => {
    if (!confirm(`确认删除「${task.video_title}」的所有笔记文件？此操作不可撤销。`)) return;
    setDeletingTaskId(task.task_id);
    try {
      await fetchJSON(`/api/storage/task/${task.task_id}`, { method: 'DELETE' });
      toast('已删除', 'success');
      if (selectedTaskId === task.task_id) {
        setSelectedTaskId(null);
        setContent('');
        setContentField(null);
      }
      loadTasks();
      loadStorageStats();
    } catch {
      toast('删除失败', 'error');
    } finally {
      setDeletingTaskId(null);
    }
  };

  // Inline note category change
  const handleChangeNoteCategory = async (shortId: string, categoryId: number | null) => {
    try {
      await fetchJSON(`/api/notes/${shortId}/category`, {
        method: 'PUT',
        body: JSON.stringify({ category_id: categoryId }),
      });
      loadTasks();
    } catch {
      toast('修改分类失败', 'error');
    }
  };

  // Inline tag editing
  const handleSaveTags = async (shortId: string) => {
    const tags = tagInput.split(/[,，\s]+/).filter(Boolean);
    try {
      const task = tasks.find((t) => t.task_id === shortId);
      await fetchJSON(`/api/tags/task/${shortId}`, {
        method: 'PUT',
        body: JSON.stringify({ tags, category: task?.category || '' }),
      });
      setEditingTaskTags(null);
      loadTasks();
    } catch {
      toast('保存标签失败', 'error');
    }
  };

  const totalPages = Math.ceil(total / pageSize);
  const hasCleanableFiles = storageStats && (
    storageStats.audio.count > 0 ||
    storageStats.downloads.count > 0 ||
    storageStats.backups.count > 0 ||
    storageStats.notes.count > 0
  );
  const categoriesWithNotes = categories.filter((c) => c.note_count > 0);

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
          <Clock size={18} strokeWidth={1.8} />
          历史记录
          {total > 0 && (
            <span className="text-xs font-normal text-[var(--color-text-muted)]">({total})</span>
          )}
        </h2>

        {/* 存储统计 */}
        {storageStats && (
          <div className="mb-5 p-3.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
            <div className="flex items-center justify-between mb-2.5">
              <span className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary)]">
                <HardDrive size={13} />
                存储占用
              </span>
              <button
                onClick={loadStorageStats}
                className="p-1 rounded hover:bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
                title="刷新"
              >
                <RefreshCw size={12} />
              </button>
            </div>
            <div className="text-lg font-semibold text-[var(--color-text)] mb-2.5">
              {storageStats.total_size_display}
            </div>
            <div className="space-y-1.5 text-[11px]">
              <div className="flex justify-between text-[var(--color-text-secondary)]">
                <span className="flex items-center gap-1"><FileText size={11} /> 笔记 ({storageStats.notes.count})</span>
                <span>{storageStats.notes.size_display}</span>
              </div>
              <div className="flex justify-between text-[var(--color-text-secondary)]">
                <span className="flex items-center gap-1"><Music size={11} /> 音频缓存 ({storageStats.audio.count})</span>
                <span>{storageStats.audio.size_display}</span>
              </div>
              <div className="flex justify-between text-[var(--color-text-secondary)]">
                <span className="flex items-center gap-1"><Download size={11} /> 下载 ({storageStats.downloads.count})</span>
                <span>{storageStats.downloads.size_display}</span>
              </div>
              <div className="flex justify-between text-[var(--color-text-secondary)]">
                <span className="flex items-center gap-1"><Archive size={11} /> 备份 ({storageStats.backups.count})</span>
                <span>{storageStats.backups.size_display}</span>
              </div>
              {storageStats.other.count > 0 && (
                <div className="flex justify-between text-[var(--color-text-muted)]">
                  <span className="flex items-center gap-1">其他 ({storageStats.other.count})</span>
                  <span>{storageStats.other.size_display}</span>
                </div>
              )}
            </div>
            {hasCleanableFiles && (
              <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-[var(--color-border)]">
                {storageStats.audio.count > 0 && (
                  <button onClick={() => handleCleanup('audio')} disabled={cleaning}
                    className="flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-medium rounded-lg bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-50 transition-colors">
                    {cleaning ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                    清理音频
                  </button>
                )}
                {storageStats.downloads.count > 0 && (
                  <button onClick={() => handleCleanup('downloads')} disabled={cleaning}
                    className="flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-medium rounded-lg bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-50 transition-colors">
                    {cleaning ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                    清理下载
                  </button>
                )}
                {storageStats.backups.count > 0 && (
                  <button onClick={() => handleCleanup('backups')} disabled={cleaning}
                    className="flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-medium rounded-lg bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-50 transition-colors">
                    {cleaning ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                    清理备份
                  </button>
                )}
                {storageStats.notes.count > 0 && (
                  <button onClick={() => handleCleanup('all_notes')} disabled={cleaning}
                    className="flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-medium rounded-lg bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 disabled:opacity-50 transition-colors">
                    {cleaning ? <Loader2 size={11} className="animate-spin" /> : <AlertTriangle size={11} />}
                    清空所有笔记
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* 搜索 + 排序 */}
        <div className="mb-4 flex gap-2">
          <input
            type="text"
            placeholder="搜索标题..."
            onChange={(e) => handleSearchChange(e.target.value)}
            className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
          />
          <button
            onClick={() => {
              if (sortBy === 'created_at') {
                setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc');
              } else {
                setSortBy('created_at');
                setSortOrder('desc');
              }
            }}
            className={clsx(
              'p-1.5 rounded-lg border transition-colors text-[var(--color-text-secondary)]',
              sortBy === 'created_at'
                ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)]'
                : 'border-[var(--color-border)] hover:border-[var(--color-accent)]',
            )}
            title={`按时间${sortOrder === 'desc' ? '从新到旧' : '从旧到新'}`}
          >
            <ArrowUpDown size={13} />
          </button>
          <button
            onClick={() => {
              if (sortBy === 'title') {
                setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
              } else {
                setSortBy('title');
                setSortOrder('asc');
              }
            }}
            className={clsx(
              'px-2 py-1.5 rounded-lg border text-[10px] font-medium transition-colors',
              sortBy === 'title'
                ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)] text-[var(--color-accent)]'
                : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]',
            )}
            title="按标题排序"
          >
            A-Z
          </button>
        </div>

        {/* 分类筛选 */}
        {(categoriesWithNotes.length > 0 || allTags.length > 0) && (
          <div className="mb-4 p-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
            <p className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] mb-2.5">
              <Filter size={12} />
              分类筛选
            </p>
            {categoriesWithNotes.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                <button
                  onClick={() => setFilterCategory('')}
                  className={clsx(
                    'px-2 py-0.5 text-[10px] rounded-full border transition-colors',
                    !filterCategory
                      ? 'bg-[var(--color-accent)] text-white border-[var(--color-accent)]'
                      : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border-[var(--color-border)] hover:border-[var(--color-accent)]',
                  )}
                >
                  全部
                </button>
                {categoriesWithNotes.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setFilterCategory(filterCategory === cat.name ? '' : cat.name)}
                    className={clsx(
                      'px-2 py-0.5 text-[10px] rounded-full border transition-colors',
                      filterCategory === cat.name
                        ? 'bg-[var(--color-accent)] text-white border-[var(--color-accent)]'
                        : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border-[var(--color-border)] hover:border-[var(--color-accent)]',
                    )}
                  >
                    {cat.name} ({cat.note_count})
                  </button>
                ))}
              </div>
            )}
            {allTags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => setFilterTag(filterTag === tag ? '' : tag)}
                    className={clsx(
                      'px-1.5 py-0.5 text-[10px] rounded-md border transition-colors',
                      filterTag === tag
                        ? 'bg-emerald-100 text-emerald-700 border-emerald-300'
                        : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] border-[var(--color-border)] hover:text-emerald-600',
                    )}
                  >
                    #{tag}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 任务列表 */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 text-xs text-[var(--color-text-muted)]">
            <Loader2 size={20} className="animate-spin mb-2" />
            加载中...
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-3">
              <Clock size={20} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">
              {(filterCategory || filterTag || searchQuery) ? '无匹配记录' : '暂无历史记录'}
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              {(filterCategory || filterTag || searchQuery) ? '尝试调整筛选条件' : '完成视频笔记或问答后，记录会出现在这里'}
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              {tasks.map((task) => (
                <div
                  key={task.task_id}
                  className={clsx(
                    'rounded-xl border transition-all group',
                    selectedTaskId === task.task_id
                      ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)] shadow-sm'
                      : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-border-light)] hover:shadow-sm',
                  )}
                >
                  <div className="px-4 py-3.5">
                    <div className="flex items-start gap-2 mb-2">
                      <span className="flex-1 text-sm font-medium text-[var(--color-text)] leading-snug line-clamp-2">
                        {task.video_title}
                      </span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span
                          className={clsx(
                            'px-2 py-0.5 text-[10px] font-semibold rounded-full',
                            task.has_summary
                              ? 'bg-blue-50 text-blue-600 border border-blue-200'
                              : 'bg-violet-50 text-violet-600 border border-violet-200',
                          )}
                        >
                          {task.has_summary ? '笔记' : '问答'}
                        </span>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDeleteTask(task); }}
                          disabled={deletingTaskId === task.task_id}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded-md text-[var(--color-text-muted)] hover:text-red-500 hover:bg-red-50 transition-all"
                          title="删除此记录"
                        >
                          {deletingTaskId === task.task_id
                            ? <Loader2 size={13} className="animate-spin" />
                            : <Trash2 size={13} />}
                        </button>
                      </div>
                    </div>

                    {/* 分类/标签显示 + 行内编辑 */}
                    <div className="flex flex-wrap items-center gap-1 mb-2">
                      {/* 分类下拉 */}
                      <select
                        value={task.category_id ?? ''}
                        onChange={(e) => handleChangeNoteCategory(
                          task.task_id,
                          e.target.value ? Number(e.target.value) : null,
                        )}
                        className="px-1.5 py-0.5 text-[9px] font-medium rounded bg-indigo-50 text-indigo-600 border border-indigo-200 appearance-none cursor-pointer hover:bg-indigo-100 focus:outline-none"
                      >
                        <option value="">未分类</option>
                        {categories.map((c) => (
                          <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                      </select>

                      {/* 标签 */}
                      {editingTaskTags === task.task_id ? (
                        <div className="flex items-center gap-1 flex-1">
                          <input
                            value={tagInput}
                            onChange={(e) => setTagInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSaveTags(task.task_id)}
                            placeholder="标签用逗号分隔"
                            className="flex-1 px-1.5 py-0.5 text-[9px] rounded border border-emerald-300 bg-white focus:outline-none min-w-0"
                            autoFocus
                          />
                          <button onClick={() => handleSaveTags(task.task_id)}
                            className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded"><Check size={10} /></button>
                          <button onClick={() => setEditingTaskTags(null)}
                            className="p-0.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface)] rounded"><X size={10} /></button>
                        </div>
                      ) : (
                        <>
                          {task.tags.map((t) => (
                            <span key={t} className="px-1.5 py-0.5 text-[9px] rounded bg-emerald-50 text-emerald-600 border border-emerald-200">
                              #{t}
                            </span>
                          ))}
                          <button
                            onClick={() => { setEditingTaskTags(task.task_id); setTagInput(task.tags.join(', ')); }}
                            className="opacity-0 group-hover:opacity-100 p-0.5 text-[var(--color-text-muted)] hover:text-emerald-600 hover:bg-emerald-50 rounded transition-all"
                            title="编辑标签"
                          >
                            <Tag size={10} />
                          </button>
                        </>
                      )}
                    </div>

                    {/* 时间 */}
                    {task.created_at && (
                      <p className="text-[9px] text-[var(--color-text-muted)] mb-2">
                        {new Date(task.created_at + 'Z').toLocaleString()}
                      </p>
                    )}

                    <div className="flex flex-wrap gap-1.5">
                      {task.has_summary && (
                        <button
                          onClick={() => handleViewContent(task, 'summary')}
                          className={clsx(
                            'flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg transition-colors',
                            selectedTaskId === task.task_id && contentField === 'summary'
                              ? 'bg-[var(--color-accent)] text-white'
                              : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]',
                          )}
                        >
                          <Eye size={11} />
                          查看摘要
                        </button>
                      )}
                      {task.has_transcript && (
                        <button
                          onClick={() => handleViewContent(task, 'transcript')}
                          className={clsx(
                            'flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg transition-colors',
                            selectedTaskId === task.task_id && contentField === 'transcript'
                              ? 'bg-[var(--color-accent)] text-white'
                              : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]',
                          )}
                        >
                          <FileText size={11} />
                          查看原文
                        </button>
                      )}
                      <button
                        onClick={() => navigate(`/cards?taskId=${task.task_id}&field=${task.has_summary ? 'summary' : 'transcript'}`)}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                      >
                        <Sparkles size={11} />
                        生成卡片
                      </button>
                      <button
                        onClick={() => navigate(`/mindmap?taskId=${task.task_id}&field=${task.has_summary ? 'summary' : 'transcript'}`)}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                      >
                        <BrainCircuit size={11} />
                        生成导图
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* 分页 */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-4 pt-3 border-t border-[var(--color-border)]">
                <button
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page <= 1}
                  className="p-1.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="text-xs text-[var(--color-text-secondary)]">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages}
                  className="p-1.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] disabled:opacity-30 transition-colors"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {loadingContent ? (
          <div className="flex flex-col items-center justify-center h-full">
            <Loader2 size={24} className="animate-spin text-[var(--color-accent)] mb-3" />
            <p className="text-sm text-[var(--color-text-secondary)]">加载内容中...</p>
          </div>
        ) : selectedTaskId && content ? (
          <div>
            <div className="flex items-center gap-2 mb-5">
              <h2 className="text-lg font-semibold text-[var(--color-text)]">
                {contentField === 'summary' ? '摘要内容' : '原文内容'}
              </h2>
              <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent)] border border-[var(--color-accent)]/20">
                {tasks.find((t) => t.task_id === selectedTaskId)?.video_title}
              </span>
            </div>
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-6">
              <MarkdownRenderer content={content} />
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-4">
              <MessageCircle size={24} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">
              选择一条记录查看内容
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              点击「查看摘要」或「查看原文」预览详细内容
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
