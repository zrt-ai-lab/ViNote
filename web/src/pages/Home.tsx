import { ArrowRight, AudioLines, Captions, Link2, Upload, Video } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useRef, useState } from 'react';
import { createAsset, uploadAsset } from '../api/v2';

const SOURCES = [
  { label: '视频链接', icon: Link2 },
  { label: '本地视频', icon: Video },
  { label: '音频文件', icon: AudioLines },
  { label: '字幕文件', icon: Captions },
];

export default function Home() {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const submitUrl = async () => {
    if (!url.trim()) return;
    setBusy(true); setError('');
    try { const asset = await createAsset({ title: url.trim(), source_type: 'url', source_uri: url.trim() }); window.location.href = '/assets/' + asset.id; }
    catch (err) { setError(err instanceof Error ? err.message : '导入失败'); }
    finally { setBusy(false); }
  };
  const submitFile = async (file: File) => {
    setBusy(true); setError('');
    try { const result = await uploadAsset(file); window.location.href = '/assets/' + result.asset.id; }
    catch (err) { setError(err instanceof Error ? err.message : '上传失败'); }
    finally { setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-8 sm:py-12">
      <header>
        <p className="mb-2 text-sm font-medium text-[var(--color-text-secondary)]">ViNote · 工作台</p>
        <h1 className="text-3xl font-bold tracking-tight sm:text-5xl">Video to Everything</h1>
        <p className="mt-4 max-w-xl text-sm leading-6 text-[var(--color-text-secondary)] sm:text-base">
          让每个视频成为可阅读、可检索、可引用的知识资产。
        </p>
      </header>

      <section aria-labelledby="import-heading" className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-7">
        <h2 id="import-heading" className="text-lg font-semibold">导入来源</h2>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">添加一个来源，2.0 会把它变成可继续处理的知识资产。</p>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <input value={url} onChange={(event) => setUrl(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void submitUrl()} placeholder="粘贴 YouTube、Bilibili 或其他视频链接" className="min-w-0 flex-1 rounded-lg border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]" />
          <button disabled={busy || !url.trim()} onClick={() => void submitUrl()} className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{busy ? '处理中…' : '添加链接'} <ArrowRight size={15} /></button>
          <button disabled={busy} onClick={() => inputRef.current?.click()} className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-medium disabled:opacity-50"><Upload size={15} /> 上传文件</button>
          <input ref={inputRef} type="file" accept="video/*,audio/*,.srt,.vtt,.txt" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void submitFile(file); event.currentTarget.value = ''; }} />
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
        <ul className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {SOURCES.map(({ label, icon: Icon }) => (
            <li key={label} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 py-3 text-sm">
              <Icon size={16} className="shrink-0" aria-hidden="true" />
              {label}
            </li>
          ))}
        </ul>
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="font-semibold">最近资产</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">暂无资产可查看。</p>
          <Link to="/library" className="mt-3 inline-flex items-center gap-2 text-sm font-medium underline underline-offset-4">
            打开知识库 <ArrowRight size={15} aria-hidden="true" />
          </Link>
        </section>
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="font-semibold">失败任务</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">接入处理任务后，可在这里查看失败原因和重试入口。</p>
        </section>
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="font-semibold">待复习</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">到期的复习卡片将在这里显示。</p>
        </section>
      </div>
    </div>
  );
}
