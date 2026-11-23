import { useEffect, useState } from 'react';
import { getHealth } from '../api/v2';

export default function Settings() {
  const [health, setHealth] = useState<{ status: string; openai_configured: boolean } | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { getHealth().then(setHealth).catch((err) => setError(err instanceof Error ? err.message : '健康检查失败')); }, []);
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-8 sm:py-12">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">设置</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">当前运行配置来自本地环境变量，核心状态在这里可核对。</p>
      </header>

      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"><h2 className="font-semibold">运行诊断</h2>{error ? <p role="alert" className="mt-2 text-sm text-red-600">{error}</p> : <dl className="mt-3 space-y-2 text-sm"><div className="flex justify-between"><dt>API 状态</dt><dd>{health?.status || '检查中…'}</dd></div><div className="flex justify-between"><dt>大模型配置</dt><dd>{health ? (health.openai_configured ? '已配置' : '未配置') : '检查中…'}</dd></div><div className="flex justify-between"><dt>版本</dt><dd>2.0.0</dd></div></dl>}</section>
      <section className="grid gap-3 sm:grid-cols-2"><div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"><h2 className="font-semibold">转录</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">默认使用本地 Faster-Whisper，模型和设备由环境变量控制。</p></div><div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"><h2 className="font-semibold">存储</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">资产、任务和产物元数据保存在 SQLite，上传文件位于受控 temp 目录。</p></div></section>
    </div>
  );
}
