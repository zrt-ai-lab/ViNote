import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchJSON, postJSON } from '../api/client';
import { toast } from '../components/Toast';
import type { Category, CompletedTask, CompletedTasksResponse } from '../types';
import {
  FolderOpen, Plus, X, Pencil, Check, Trash2, Loader2,
  FileText, Sparkles, BrainCircuit, ChevronLeft, ChevronRight,
} from 'lucide-react';
import clsx from 'clsx';

type ActivePanel = { name: string } | null;

export default function TagManagement() {
  const navigate = useNavigate();

  // Categories
  const [categories, setCategories] = useState<Category[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [creatingCategory, setCreatingCategory] = useState(false);
  const [editingCatId, setEditingCatId] = useState<number | null>(null);
  const [editingCatName, setEditingCatName] = useState('');

  // Right panel — notes list
  const [activePanel, setActivePanel] = useState<ActivePanel>(null);
  const [notes, setNotes] = useState<CompletedTask[]>([]);
  const [notesTotal, setNotesTotal] = useState(0);
  const [notesPage, setNotesPage] = useState(1);
  const [loadingNotes, setLoadingNotes] = useState(false);
  const notesPageSize = 20;

  // ── Load data ──────────────────────────────────────

  const loadCategories = useCallback(() => {
    setLoadingCategories(true);
    fetchJSON<{ categories: Category[] }>('/api/categories')
      .then((res) => setCategories(res.categories))
      .catch(() => toast('加载分类失败', 'error'))
      .finally(() => setLoadingCategories(false));
  }, []);

  const loadNotes = useCallback(() => {
    if (!activePanel) return;
    setLoadingNotes(true);
    const params = new URLSearchParams();
    params.set('page', String(notesPage));
    params.set('page_size', String(notesPageSize));
    params.set('category', activePanel.name);

    fetchJSON<CompletedTasksResponse>(`/api/tasks/completed?${params}`)
      .then((res) => {
        setNotes(res.tasks);
        setNotesTotal(res.total);
      })
      .catch(() => toast('加载笔记列表失败', 'error'))
      .finally(() => setLoadingNotes(false));
  }, [activePanel, notesPage]);

  useEffect(() => { loadCategories(); }, [loadCategories]);
  useEffect(() => { loadNotes(); }, [loadNotes]);
  useEffect(() => { setNotesPage(1); }, [activePanel]);

  // ── Category CRUD ──────────────────────────────────

  const handleCreateCategory = async () => {
    const name = newCategoryName.trim();
    if (!name) return;
    setCreatingCategory(true);
    try {
      await postJSON('/api/categories', { name });
      setNewCategoryName('');
      loadCategories();
      toast('分类已创建', 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : '创建失败', 'error');
    } finally {
      setCreatingCategory(false);
    }
  };

  const handleRenameCategory = async (id: number) => {
    const name = editingCatName.trim();
    if (!name) { setEditingCatId(null); return; }
    try {
      await fetchJSON(`/api/categories/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ name }),
      });
      const oldName = categories.find((c) => c.id === id)?.name;
      setEditingCatId(null);
      loadCategories();
      if (activePanel?.name === oldName) {
        setActivePanel({ name });
      }
      toast('分类已重命名', 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : '重命名失败', 'error');
    }
  };

  const handleDeleteCategory = async (id: number, name: string) => {
    if (!confirm(`确认删除分类「${name}」？该分类下的笔记将变为未分类。`)) return;
    try {
      await fetchJSON(`/api/categories/${id}`, { method: 'DELETE' });
      loadCategories();
      if (activePanel?.name === name) {
        setActivePanel(null);
        setNotes([]);
      }
      toast('分类已删除', 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : '删除失败', 'error');
    }
  };

  // ── Helpers ────────────────────────────────────────

  const totalNotePages = Math.ceil(notesTotal / notesPageSize);

  const isActive = (name: string) => activePanel?.name === name;

  return (
    <div className="flex h-full">
      {/* ── Left panel: Categories ── */}
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5 flex items-center gap-2">
          <FolderOpen size={18} strokeWidth={1.8} />
          笔记分类
        </h2>

        {/* ── Categories section ── */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">
              <FolderOpen size={13} />
              分类
              {categories.length > 0 && (
                <span className="text-[var(--color-text-muted)] font-normal">({categories.length})</span>
              )}
            </h3>
          </div>

          {/* New category input */}
          <div className="flex gap-1.5 mb-3">
            <input
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreateCategory()}
              placeholder="新分类名..."
              className="flex-1 px-2.5 py-1.5 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
            />
            <button
              onClick={handleCreateCategory}
              disabled={creatingCategory || !newCategoryName.trim()}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-white disabled:opacity-50 transition-colors"
            >
              {creatingCategory ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
              添加
            </button>
          </div>

          {/* Categories list */}
          {loadingCategories ? (
            <div className="flex items-center justify-center py-8 text-xs text-[var(--color-text-muted)]">
              <Loader2 size={16} className="animate-spin mr-2" />
              加载中...
            </div>
          ) : categories.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)] text-center py-6">暂无分类</p>
          ) : (
            <div className="space-y-1">
              {categories.map((cat) => (
                <div
                  key={cat.id}
                  className={clsx(
                    'flex items-center gap-2 px-3 py-2 rounded-lg transition-colors group cursor-pointer',
                    isActive(cat.name)
                      ? 'bg-indigo-50 border border-indigo-200'
                      : 'hover:bg-[var(--color-bg)] border border-transparent',
                  )}
                  onClick={() => {
                    if (isActive(cat.name)) {
                      setActivePanel(null); setNotes([]);
                    } else {
                      setActivePanel({ name: cat.name });
                    }
                  }}
                >
                  {editingCatId === cat.id ? (
                    <>
                      <input
                        value={editingCatName}
                        onChange={(e) => setEditingCatName(e.target.value)}
                        onKeyDown={(e) => {
                          e.stopPropagation();
                          if (e.key === 'Enter') handleRenameCategory(cat.id);
                          if (e.key === 'Escape') setEditingCatId(null);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="flex-1 px-2 py-0.5 text-xs rounded border border-[var(--color-accent)] bg-white focus:outline-none"
                        autoFocus
                      />
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRenameCategory(cat.id); }}
                        className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded"
                      >
                        <Check size={12} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingCatId(null); }}
                        className="p-0.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface)] rounded"
                      >
                        <X size={12} />
                      </button>
                    </>
                  ) : (
                    <>
                      <span className="flex-1 text-xs text-[var(--color-text)]">
                        {cat.name}
                        {cat.is_system && (
                          <span className="ml-1 text-[10px] text-[var(--color-text-muted)]">(系统)</span>
                        )}
                      </span>
                      <span className="text-[10px] text-[var(--color-text-muted)] tabular-nums">
                        {cat.note_count}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingCatId(cat.id);
                          setEditingCatName(cat.name);
                        }}
                        className="opacity-0 group-hover:opacity-100 p-0.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent)] rounded transition-all"
                      >
                        <Pencil size={11} />
                      </button>
                      {!(cat.is_system && cat.name === '其他') && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDeleteCategory(cat.id, cat.name); }}
                          className="opacity-0 group-hover:opacity-100 p-0.5 text-[var(--color-text-muted)] hover:text-red-500 rounded transition-all"
                        >
                          <Trash2 size={11} />
                        </button>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Right panel: Associated notes ── */}
      <div className="flex-1 overflow-y-auto p-6">
        {!activePanel ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-4">
              <FolderOpen size={24} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">
              选择一个分类
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              点击左侧分类查看关联笔记
            </p>
          </div>
        ) : loadingNotes ? (
          <div className="flex flex-col items-center justify-center h-full">
            <Loader2 size={24} className="animate-spin text-[var(--color-accent)] mb-3" />
            <p className="text-sm text-[var(--color-text-secondary)]">加载中...</p>
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-2 mb-5">
              <h2 className="text-lg font-semibold text-[var(--color-text)]">
                <span className="flex items-center gap-1.5">
                  <FolderOpen size={18} className="text-indigo-500" />
                  {activePanel.name}
                </span>
              </h2>
              <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-[var(--color-bg)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
                {notesTotal} 条笔记
              </span>
            </div>

            {notes.length === 0 ? (
              <div className="text-center py-16">
                <p className="text-sm text-[var(--color-text-secondary)]">暂无关联笔记</p>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  {notes.map((note) => (
                    <div
                      key={note.task_id}
                      className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-light)] hover:shadow-sm transition-all"
                    >
                      <div className="px-4 py-3.5">
                        <div className="flex items-start gap-2 mb-2">
                          <span className="flex-1 text-sm font-medium text-[var(--color-text)] leading-snug line-clamp-2">
                            {note.video_title}
                          </span>
                          <span
                            className={clsx(
                              'px-2 py-0.5 text-[10px] font-semibold rounded-full shrink-0',
                              note.has_summary
                                ? 'bg-blue-50 text-blue-600 border border-blue-200'
                                : 'bg-violet-50 text-violet-600 border border-violet-200',
                            )}
                          >
                            {note.has_summary ? '笔记' : '问答'}
                          </span>
                        </div>

                        {/* Meta: tags as clickable chips */}
                        {note.tags.length > 0 && (
                          <div className="flex flex-wrap items-center gap-1 mb-2">
                            {note.tags.map((t) => (
                              <button
                                key={t}
                                onClick={() => navigate(`/history?tag=${encodeURIComponent(t)}`)}
                                className="px-1.5 py-0.5 text-[9px] rounded bg-emerald-50 text-emerald-600 border border-emerald-200 hover:bg-emerald-100 transition-colors cursor-pointer"
                              >
                                #{t}
                              </button>
                            ))}
                          </div>
                        )}

                        {/* Time */}
                        {note.created_at && (
                          <p className="text-[9px] text-[var(--color-text-muted)] mb-2">
                            {new Date(note.created_at + 'Z').toLocaleString()}
                          </p>
                        )}

                        {/* Action buttons */}
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            onClick={() => navigate(`/history`)}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg bg-[var(--color-bg)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                          >
                            <FileText size={11} />
                            查看详情
                          </button>
                          <button
                            onClick={() => navigate(`/cards?taskId=${note.task_id}&field=${note.has_summary ? 'summary' : 'transcript'}`)}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg bg-[var(--color-bg)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                          >
                            <Sparkles size={11} />
                            生成卡片
                          </button>
                          <button
                            onClick={() => navigate(`/mindmap?taskId=${note.task_id}&field=${note.has_summary ? 'summary' : 'transcript'}`)}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg bg-[var(--color-bg)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                          >
                            <BrainCircuit size={11} />
                            生成导图
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Pagination */}
                {totalNotePages > 1 && (
                  <div className="flex items-center justify-center gap-2 mt-4 pt-3 border-t border-[var(--color-border)]">
                    <button
                      onClick={() => setNotesPage(Math.max(1, notesPage - 1))}
                      disabled={notesPage <= 1}
                      className="p-1.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] disabled:opacity-30 transition-colors"
                    >
                      <ChevronLeft size={14} />
                    </button>
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      {notesPage} / {totalNotePages}
                    </span>
                    <button
                      onClick={() => setNotesPage(Math.min(totalNotePages, notesPage + 1))}
                      disabled={notesPage >= totalNotePages}
                      className="p-1.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] disabled:opacity-30 transition-colors"
                    >
                      <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
