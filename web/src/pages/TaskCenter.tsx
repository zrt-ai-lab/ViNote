import { Activity } from 'lucide-react';
import { useEffect, useState } from 'react';
import { listTasks } from '../api/v2';
import type { Job } from '../api/v2';

export default function TaskCenter() {
  const [tasks, setTasks] = useState<Job[]>([]); const [loading, setLoading] = useState(true);
  const refresh = () => listTasks().then(setTasks).finally(() => setLoading(false));
  useEffect(() => { void refresh(); const timer = window.setInterval(refresh, 3000); return () => window.clearInterval(timer); }, []);
  return <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-8 sm:py-12"><header><h1 className="text-3xl font-bold tracking-tight">转录进程</h1><p className="mt-2 text-sm text-[var(--color-text-secondary)]">查看搜索导入、字幕解析和媒体转录的真实任务状态。</p></header>{loading ? <p className="text-sm text-[var(--color-text-secondary)]">加载中…</p> : tasks.length === 0 ? <div className="rounded-2xl border border-dashed border-[var(--color-border)] p-12 text-center"><Activity className="mx-auto text-[var(--color-text-secondary)]" /><p className="mt-3 text-sm text-[var(--color-text-secondary)]">暂无处理任务</p></div> : <div className="space-y-3">{tasks.map((task) => <article key={task.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"><div className="flex items-center justify-between"><div><h2 className="text-sm font-semibold">{task.kind}</h2><p className="mt-1 text-xs text-[var(--color-text-secondary)]">{task.id}</p></div><span className="rounded-full bg-[var(--color-accent-light)] px-3 py-1 text-xs">{task.status}</span></div><p className="mt-3 text-sm text-[var(--color-text-secondary)]">阶段：{task.stage || '排队'}{task.error ? ' · ' + task.error : ''}</p></article>)}</div>}</div>;
}
