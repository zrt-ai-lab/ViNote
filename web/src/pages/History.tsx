import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchJSON } from '../api/client';
import { toast } from '../components/Toast';
import MarkdownRenderer from '../components/MarkdownRenderer';
import { Clock, FileText, MessageCircle, Sparkles, BrainCircuit, Loader2, Eye } from 'lucide-react';
import clsx from 'clsx';

interface CompletedTask {
  task_id: string;
  video_title: string;
  type: 'notes' | 'qa';
  has_summary: boolean;
  has_transcript: boolean;
}

type ContentField = 'summary' | 'transcript';

export default function History() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<CompletedTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [contentField, setContentField] = useState<ContentField | null>(null);
  const [content, setContent] = useState('');
  const [loadingContent, setLoadingContent] = useState(false);

  useEffect(() => {
    fetchJSON<{ tasks: CompletedTask[] }>('/api/tasks/completed')
      .then((res) => setTasks(res.tasks))
      .catch(() => toast('获取历史记录失败', 'error'))
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5 flex items-center gap-2">
          <Clock size={18} strokeWidth={1.8} />
          历史记录
        </h2>

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
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">暂无历史记录</p>
            <p className="text-xs text-[var(--color-text-muted)]">完成视频笔记或问答后，记录会出现在这里</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div
                key={task.task_id}
                className={clsx(
                  'rounded-xl border transition-all',
                  selectedTaskId === task.task_id
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)] shadow-sm'
                    : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-border-light)] hover:shadow-sm',
                )}
              >
                <div className="px-4 py-3.5">
                  <div className="flex items-start gap-2 mb-2.5">
                    <span className="flex-1 text-sm font-medium text-[var(--color-text)] leading-snug line-clamp-2">
                      {task.video_title}
                    </span>
                    <span
                      className={clsx(
                        'shrink-0 px-2 py-0.5 text-[10px] font-semibold rounded-full',
                        task.has_summary
                          ? 'bg-blue-50 text-blue-600 border border-blue-200'
                          : 'bg-violet-50 text-violet-600 border border-violet-200',
                      )}
                    >
                      {task.has_summary ? '笔记' : '问答'}
                    </span>
                  </div>

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
