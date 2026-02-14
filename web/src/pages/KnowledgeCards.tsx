import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { streamPost, fetchJSON } from '../api/client';
import { toast } from '../components/Toast';
import { Sparkles, ClipboardPaste, BookOpen, MessageSquare, Loader2, Check, FlipHorizontal2, ListChecks, Lightbulb, LayoutPanelLeft, Copy } from 'lucide-react';
import clsx from 'clsx';

type KnowledgeCard = Record<string, string | string[]>;

type CardStyle = 'anki' | 'keypoint' | 'concept' | 'cornell';

type SourceType = 'notes' | 'text' | 'qa';

interface CompletedTask {
  task_id: string;
  video_title: string;
  type: 'notes' | 'qa';
  has_summary: boolean;
  has_transcript: boolean;
}

const SOURCE_TABS: { key: SourceType; label: string; icon: typeof BookOpen }[] = [
  { key: 'notes', label: '从笔记选择', icon: BookOpen },
  { key: 'text', label: '粘贴文本', icon: ClipboardPaste },
  { key: 'qa', label: '从问答选择', icon: MessageSquare },
];

function cardToMarkdown(card: KnowledgeCard, cardStyle: CardStyle): string {
  switch (cardStyle) {
    case 'anki': {
      const tags = Array.isArray(card.tags) ? card.tags.map(String).join(', ') : '';
      let md = `## Q: ${String(card.front || '')}\n\n**A:** ${String(card.back || '')}`;
      if (tags) md += `\n\nTags: ${tags}`;
      return md;
    }
    case 'keypoint': {
      const points = Array.isArray(card.points) ? card.points.map((p) => `- ${String(p)}`).join('\n') : '';
      let md = `## ${String(card.title || '')}\n\n**核心概念:** ${String(card.concept || '')}`;
      if (points) md += `\n\n${points}`;
      md += `\n\n**总结:** ${String(card.summary || '')}`;
      md += `\n\n> Q: ${String(card.question || '')}\n> A: ${String(card.answer || '')}`;
      return md;
    }
    case 'concept': {
      const related = Array.isArray(card.related) ? card.related.map(String).join(', ') : '';
      let md = `## ${String(card.term || '')}\n\n${String(card.definition || '')}`;
      if (card.example) md += `\n\n**示例:** ${String(card.example)}`;
      if (related) md += `\n\n相关: ${related}`;
      return md;
    }
    case 'cornell': {
      const cue = Array.isArray(card.cue) ? card.cue.map(String).join(', ') : String(card.cue || '');
      const notes = Array.isArray(card.notes) ? card.notes.map((n) => `- ${String(n)}`).join('\n') : String(card.notes || '');
      let md = `## ${String(card.topic || '')}\n\n**关键词:** ${cue}`;
      if (notes) md += `\n\n${notes}`;
      md += `\n\n---\n\n**总结:** ${String(card.summary || '')}`;
      return md;
    }
  }
}

function copyToClipboard(text: string) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(
      () => toast('已复制到剪贴板', 'success'),
      () => fallbackCopy(text),
    );
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text: string) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand('copy');
    toast('已复制到剪贴板', 'success');
  } catch {
    toast('复制失败，请手动复制', 'error');
  }
  document.body.removeChild(textarea);
}

export default function KnowledgeCards() {
  const [searchParams] = useSearchParams();
  const [source, setSource] = useState<SourceType>('text');
  const [content, setContent] = useState('');
  const [cardCount, setCardCount] = useState(5);
  const [style, setStyle] = useState<CardStyle>('keypoint');
  const [loading, setLoading] = useState(false);
  const [cards, setCards] = useState<KnowledgeCard[]>([]);
  const [progress, setProgress] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const [completedTasks, setCompletedTasks] = useState<CompletedTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const autoLoadedRef = useRef(false);

  useEffect(() => {
    if (autoLoadedRef.current) return;
    const taskId = searchParams.get('taskId');
    const field = searchParams.get('field') || 'summary';
    if (!taskId) return;
    autoLoadedRef.current = true;
    setSource('text');
    fetchJSON<{ content: string }>(`/api/tasks/${taskId}/content?field=${field}`)
      .then((res) => {
        setContent(res.content);
        toast('已加载历史内容，可直接生成卡片', 'success');
      })
      .catch(() => toast('自动加载内容失败', 'error'));
  }, [searchParams]);

  useEffect(() => {
    if (source === 'notes' || source === 'qa') {
      setLoadingTasks(true);
      fetchJSON<{ tasks: CompletedTask[] }>('/api/tasks/completed')
        .then((res) => {
          const filtered = source === 'notes'
            ? res.tasks.filter((t) => t.has_summary)
            : res.tasks.filter((t) => t.has_transcript);
          setCompletedTasks(filtered);
        })
        .catch(() => {
          setCompletedTasks([]);
          toast('获取任务列表失败', 'error');
        })
        .finally(() => setLoadingTasks(false));
    }
  }, [source]);

  const handleSelectTask = async (task: CompletedTask) => {
    setSelectedTaskId(task.task_id);
    setLoadingContent(true);
    const field = source === 'notes' ? 'summary' : 'transcript';
    try {
      const res = await fetchJSON<{ content: string }>(`/api/tasks/${task.task_id}/content?field=${field}`);
      setContent(res.content);
      toast(`已加载：${task.video_title}`, 'success');
    } catch {
      toast('加载内容失败', 'error');
    } finally {
      setLoadingContent(false);
    }
  };

  const handleGenerate = () => {
    const trimmed = content.trim();
    if (!trimmed) {
      toast('请输入内容', 'error');
      return;
    }
    if (trimmed.length < 50) {
      toast('内容太短，请提供至少 50 字的文本', 'error');
      return;
    }
    setLoading(true);
    setCards([]);
    setProgress(0);

    let received = 0;

    abortRef.current = streamPost(
      '/api/generate-cards',
      { source, content: content.trim(), count: cardCount, style },
      (data) => {
        const d = data as { type: string; data?: KnowledgeCard; message?: string };
        if (d.type === 'card' && d.data) {
          received++;
          setCards((prev) => [...prev, d.data as KnowledgeCard]);
          setProgress(Math.round((received / cardCount) * 100));
        } else if (d.type === 'done') {
          setLoading(false);
          setProgress(100);
          toast('卡片生成完成！', 'success');
        } else if (d.type === 'error') {
          setLoading(false);
          toast(d.message || '生成失败', 'error');
        }
      },
      () => {
        setLoading(false);
      },
      (err) => {
        setLoading(false);
        toast(err.message || '生成失败', 'error');
      },
    );
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    setLoading(false);
    toast('已取消生成', 'info');
  };

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5">知识卡片</h2>

        <div className="flex gap-1.5 mb-4">
          {SOURCE_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setSource(tab.key)}
              className={clsx(
                'flex items-center gap-1 px-3 py-1.5 text-xs rounded-md font-medium transition-colors',
                source === tab.key
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border-light)]',
              )}
            >
              <tab.icon size={12} />
              {tab.label}
            </button>
          ))}
        </div>

        {(source === 'notes' || source === 'qa') && (
          <div className="mb-3 max-h-48 overflow-y-auto border border-[var(--color-border)] rounded-lg">
            {loadingTasks ? (
              <div className="flex items-center justify-center py-6 text-xs text-[var(--color-text-muted)]">
                <Loader2 size={14} className="animate-spin mr-1.5" />
                加载中...
              </div>
            ) : completedTasks.length === 0 ? (
              <div className="py-6 text-center text-xs text-[var(--color-text-muted)]">
                暂无已完成的{source === 'notes' ? '笔记' : '问答'}记录
              </div>
            ) : (
              completedTasks.map((task) => (
                <button
                  key={task.task_id}
                  onClick={() => handleSelectTask(task)}
                  disabled={loadingContent}
                  className={clsx(
                    'w-full flex items-center gap-2 px-3 py-2.5 text-left text-xs border-b border-[var(--color-border-light)] last:border-b-0 transition-colors',
                    selectedTaskId === task.task_id
                      ? 'bg-[var(--color-accent-light)] text-[var(--color-accent)]'
                      : 'hover:bg-[var(--color-bg)] text-[var(--color-text-secondary)]',
                  )}
                >
                  {selectedTaskId === task.task_id ? (
                    <Check size={13} className="shrink-0 text-[var(--color-accent)]" />
                  ) : (
                    <BookOpen size={13} className="shrink-0" />
                  )}
                  <span className="flex-1 truncate">{task.video_title}</span>
                  {loadingContent && selectedTaskId === task.task_id && (
                    <Loader2 size={12} className="animate-spin shrink-0" />
                  )}
                </button>
              ))
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 mb-4">
          {([
            { key: 'anki' as const, name: 'Anki 闪卡', desc: '正面问题/背面答案', Icon: FlipHorizontal2 },
            { key: 'keypoint' as const, name: '知识要点', desc: '标题+概念+要点+总结', Icon: ListChecks },
            { key: 'concept' as const, name: '概念图卡', desc: '概念+定义+示例', Icon: Lightbulb },
            { key: 'cornell' as const, name: '康奈尔笔记', desc: '线索+笔记+总结', Icon: LayoutPanelLeft },
          ]).map((opt) => (
            <button
              key={opt.key}
              onClick={() => {
                setStyle(opt.key);
                setCards([]);
                setProgress(0);
              }}
              disabled={loading}
              className={clsx(
                'flex flex-col items-start gap-1 p-2.5 rounded-lg border text-left transition-all',
                loading && 'opacity-50 cursor-not-allowed',
                style === opt.key
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)]'
                  : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-border-light)]',
              )}
            >
              <div className="flex items-center gap-1.5">
                <opt.Icon
                  size={13}
                  className={clsx(
                    style === opt.key ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]',
                  )}
                />
                <span
                  className={clsx(
                    'text-xs font-medium',
                    style === opt.key ? 'text-[var(--color-accent)]' : 'text-[var(--color-text)]',
                  )}
                >
                  {opt.name}
                </span>
              </div>
              <span className="text-[10px] text-[var(--color-text-muted)] leading-tight">{opt.desc}</span>
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={
              source === 'notes'
                ? '从笔记中选择内容，或粘贴笔记文本...'
                : source === 'qa'
                  ? '从问答记录中选择内容，或粘贴问答文本...'
                  : '粘贴任意文本内容，AI 将自动提炼生成知识卡片\n\n例如：课程笔记、文章摘要、视频转录文本等'
            }
            rows={12}
            className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20 resize-none"
            disabled={loading}
          />

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs text-[var(--color-text-secondary)]">生成卡片数量</label>
              <span className="text-xs font-medium text-[var(--color-accent)]">{cardCount} 张</span>
            </div>
            <input
              type="range"
              min={5}
              max={10}
              value={cardCount}
              onChange={(e) => setCardCount(Number(e.target.value))}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--color-accent)]"
              style={{
                background: `linear-gradient(to right, var(--color-accent) ${((cardCount - 5) / 5) * 100}%, var(--color-border) ${((cardCount - 5) / 5) * 100}%)`,
              }}
              disabled={loading}
            />
            <div className="flex justify-between text-[10px] text-[var(--color-text-muted)]">
              <span>5</span>
              <span>10</span>
            </div>
          </div>

          {loading ? (
            <button
              onClick={handleCancel}
              className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
            >
              <Loader2 size={13} className="animate-spin" />
              取消生成 ({progress}%)
            </button>
          ) : (
            <button
              onClick={handleGenerate}
              disabled={!content.trim()}
              className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
            >
              <Sparkles size={13} />
              生成卡片
            </button>
          )}

          <p className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
            AI 会分析文本内容，提炼核心知识点并生成结构化学习卡片
          </p>
        </div>

        {loading && (
          <div className="mt-5 space-y-2">
            <div className="h-1.5 bg-[var(--color-border)] rounded-full overflow-hidden">
              <div
                className="h-full bg-[var(--color-accent)] rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
              <Loader2 size={12} className="animate-spin" />
              已生成 {cards.length} / {cardCount} 张卡片
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {cards.length > 0 ? (
          <div>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-[var(--color-text)]">
                知识卡片
                <span className="ml-2 text-sm font-normal text-[var(--color-text-secondary)]">
                  ({cards.length} 张)
                </span>
              </h2>
              <button
                onClick={() => {
                  const allMd = cards.map((c) => cardToMarkdown(c, style)).join('\n\n---\n\n');
                  copyToClipboard(allMd);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]/40 hover:text-[var(--color-accent)] transition-colors"
              >
                <Copy size={12} />
                复制全部
              </button>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {cards.map((card, idx) => (
                <div
                  key={idx}
                  className="group relative bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-sm hover:shadow-md transition-shadow overflow-hidden"
                  style={{
                    animation: 'card-in 0.4s ease both',
                    animationDelay: `${idx * 80}ms`,
                  }}
                >
                  <button
                    onClick={() => copyToClipboard(cardToMarkdown(card, style))}
                    className="absolute top-2.5 right-2.5 z-10 p-1.5 rounded-md bg-[var(--color-surface)]/80 backdrop-blur border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)]/40 opacity-0 group-hover:opacity-100 transition-all"
                    title="复制为 Markdown"
                  >
                    <Copy size={12} />
                  </button>
                  {style === 'anki' && (
                    <div className="flex flex-col">
                      <div className="bg-[var(--color-accent)]/5 border-b border-[var(--color-accent)]/15 px-5 py-5">
                        <div className="flex items-center gap-1.5 mb-2">
                          <FlipHorizontal2 size={11} className="text-[var(--color-accent)]" />
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-accent)]">Question</span>
                        </div>
                        <p className="text-sm font-bold text-[var(--color-text)] leading-relaxed">
                          {String(card.front || '')}
                        </p>
                      </div>
                      <div className="px-5 py-5">
                        <div className="flex items-center gap-1.5 mb-2">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Answer</span>
                        </div>
                        <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                          {String(card.back || '')}
                        </p>
                      </div>
                      {Array.isArray(card.tags) && card.tags.length > 0 && (
                        <div className="px-5 pb-4 flex flex-wrap gap-1.5">
                          {card.tags.map((tag, ti) => (
                            <span
                              key={ti}
                              className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent)] border border-[var(--color-accent)]/20"
                            >
                              {String(tag)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {style === 'keypoint' && (
                    <div className="p-5">
                      <h3 className="text-sm font-bold text-[var(--color-text)] mb-2 leading-snug">
                        {String(card.title || '')}
                      </h3>
                      <span className="inline-block px-2 py-0.5 text-[11px] font-medium rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent)] border border-[var(--color-accent)]/20 mb-3">
                        {String(card.concept || '')}
                      </span>
                      {Array.isArray(card.points) && (
                        <ul className="space-y-1 mb-3">
                          {card.points.map((point, pi) => (
                            <li
                              key={pi}
                              className="flex items-start gap-1.5 text-xs text-[var(--color-text-secondary)] leading-relaxed"
                            >
                              <span className="shrink-0 mt-1 w-1 h-1 rounded-full bg-[var(--color-accent)]" />
                              {String(point)}
                            </li>
                          ))}
                        </ul>
                      )}
                      <p className="text-xs italic text-[var(--color-text-muted)] mb-3 leading-relaxed border-l-2 border-[var(--color-border)] pl-2.5">
                        {String(card.summary || '')}
                      </p>
                      <div className="bg-[var(--color-bg)] rounded-lg p-3 space-y-1.5">
                        <p className="text-xs font-semibold text-[var(--color-text)]">
                          <MessageSquare size={11} className="inline mr-1 -mt-0.5 text-[var(--color-accent)]" />
                          {String(card.question || '')}
                        </p>
                        <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                          {String(card.answer || '')}
                        </p>
                      </div>
                    </div>
                  )}

                  {style === 'concept' && (
                    <div className="p-5">
                      <h3 className="text-base font-extrabold text-[var(--color-text)] mb-1 leading-snug tracking-tight">
                        {String(card.term || '')}
                      </h3>
                      <div className="w-8 h-0.5 bg-[var(--color-accent)] rounded-full mb-3" />
                      <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed mb-3">
                        {String(card.definition || '')}
                      </p>
                      {card.example && (
                        <div className="bg-[var(--color-accent-light)] rounded-lg px-3.5 py-3 mb-3 border-l-2 border-[var(--color-accent)]">
                          <p className="text-xs text-[var(--color-text)] leading-relaxed">
                            <Lightbulb size={11} className="inline mr-1 -mt-0.5 text-[var(--color-accent)]" />
                            {String(card.example)}
                          </p>
                        </div>
                      )}
                      {Array.isArray(card.related) && card.related.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {card.related.map((rel, ri) => (
                            <span
                              key={ri}
                              className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-[var(--color-bg)] text-[var(--color-text-muted)] border border-[var(--color-border)]"
                            >
                              {String(rel)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {style === 'cornell' && (
                    <div className="flex flex-col">
                      <div className="px-5 pt-4 pb-2 border-b border-[var(--color-border)]">
                        <h3 className="text-sm font-bold text-[var(--color-text)] leading-snug">
                          {String(card.topic || '')}
                        </h3>
                      </div>
                      <div className="flex flex-1 min-h-0">
                        <div className="w-[30%] border-r border-[var(--color-border)] px-3 py-3 bg-[var(--color-bg)]">
                          {Array.isArray(card.cue) ? (
                            card.cue.map((c, ci) => (
                              <p key={ci} className="text-xs font-semibold text-[var(--color-text)] mb-1.5 leading-snug">
                                {String(c)}
                              </p>
                            ))
                          ) : (
                            <p className="text-xs font-semibold text-[var(--color-text)] leading-snug">
                              {String(card.cue || '')}
                            </p>
                          )}
                        </div>
                        <div className="w-[70%] px-3 py-3">
                          {Array.isArray(card.notes) ? (
                            <ul className="space-y-1">
                              {card.notes.map((n, ni) => (
                                <li
                                  key={ni}
                                  className="flex items-start gap-1.5 text-xs text-[var(--color-text-secondary)] leading-relaxed"
                                >
                                  <span className="shrink-0 mt-1 w-1 h-1 rounded-full bg-[var(--color-text-muted)]" />
                                  {String(n)}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                              {String(card.notes || '')}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="px-5 py-3 bg-[var(--color-accent-light)] border-t border-[var(--color-accent)]/15">
                        <p className="text-xs text-[var(--color-text)] leading-relaxed">
                          <span className="font-semibold text-[var(--color-accent)] mr-1">总结</span>
                          {String(card.summary || '')}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-4">
              <Sparkles size={24} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">
              输入文本内容，AI 生成知识卡片
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              支持笔记、文章、问答记录等任意文本
            </p>
          </div>
        )}
      </div>

      <style>{`
        @keyframes card-in {
          from {
            opacity: 0;
            transform: translateY(12px) scale(0.97);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
      `}</style>
    </div>
  );
}
