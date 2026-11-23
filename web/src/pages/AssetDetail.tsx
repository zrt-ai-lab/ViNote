import { Play } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { getAsset } from '../api/v2';
import { askAsset, createFlashcard, createHighlight } from '../api/v2';
import type { AssetDetail as AssetDetailData } from '../api/v2';

const ARTIFACTS = ['摘要', '问答', '高亮与批注', '复习卡片', '思维导图', '导出'];

export default function AssetDetail() {
  const { assetId } = useParams();
  const [asset, setAsset] = useState<AssetDetailData | null>(null);
  const [error, setError] = useState('');
  const refresh = () => { if (assetId) void getAsset(assetId).then(setAsset).catch(() => undefined); };
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<{ answer: string; citations: { start_ms: number; end_ms: number; quote: string }[] } | null>(null);
  const [actionMessage, setActionMessage] = useState('');
  useEffect(() => { if (assetId) getAsset(assetId).then(setAsset).catch((err) => setError(err instanceof Error ? err.message : '加载失败')); }, [assetId]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-8 sm:py-12">
      <header>
        <Link to="/library" className="text-sm text-[var(--color-text-secondary)] underline underline-offset-4">返回知识库</Link>
        <h1 className="mt-3 text-3xl font-bold tracking-tight">{asset?.title || '资产详情'}</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
          {error || (assetId ? (asset ? asset.source_type + ' · ' + asset.jobs.length + ' 个处理任务' : '加载中…') : '暂未选择资产。')}
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="font-semibold">播放器</h2>
          <div className="mt-4 flex aspect-video flex-col items-center justify-center gap-2 rounded-lg bg-[var(--color-bg)] text-sm text-[var(--color-text-secondary)]">
            <Play size={24} aria-hidden="true" />
            暂无可播放媒体
          </div>
        </section>
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="font-semibold">时间轴原文</h2>
          {asset?.segments.length === 0 && <p className="mt-3 text-sm text-[var(--color-text-secondary)]">暂无转录片段。处理任务完成后，带时间戳的原文将在这里显示。</p>}
          {asset?.segments.map((segment) => <div key={segment.id} className="mt-3 rounded-lg border border-[var(--color-border)] p-3 text-sm"><span className="mr-2 text-xs text-[var(--color-text-secondary)]">{Math.floor(segment.start_ms / 60000)}:{String(Math.floor(segment.start_ms / 1000) % 60).padStart(2, '0')}</span>{segment.edited_text || segment.text}</div>)}
        </section>
      </div>

      <section aria-labelledby="artifacts-heading" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 id="artifacts-heading" className="font-semibold">知识产物</h2>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{asset ? asset.artifacts.length + ' 个产物，' + asset.highlights.length + ' 条高亮，' + asset.flashcards.length + ' 张卡片' : '产物生成和导出尚未接入。'}</p>
        <ul className="mt-4 flex flex-wrap gap-2">
          {ARTIFACTS.map((item) => (
            <li key={item} className="rounded-full border border-[var(--color-border)] px-3 py-1 text-sm">{item}</li>
          ))}
        </ul>
      </section>
      {asset && <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"><h2 className="font-semibold">基于原文提问</h2><div className="mt-3 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && question.trim()) void askAsset(asset.id, question).then(setAnswer).catch((err) => setActionMessage(err instanceof Error ? err.message : '提问失败')); }} placeholder="问这个视频里的一个问题" className="min-w-0 flex-1 rounded-lg border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm" /><button disabled={!question.trim()} onClick={() => void askAsset(asset.id, question).then(setAnswer).catch((err) => setActionMessage(err instanceof Error ? err.message : '提问失败'))} className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm text-white disabled:opacity-50">提问</button></div>{answer && <div className="mt-4 space-y-3 text-sm"><p>{answer.answer}</p>{answer.citations.map((citation) => <blockquote key={citation.start_ms} className="border-l-2 border-[var(--color-accent)] pl-3 text-[var(--color-text-secondary)]">[{Math.floor(citation.start_ms / 60000)}:{String(Math.floor(citation.start_ms / 1000) % 60).padStart(2, '0')}] {citation.quote}</blockquote>)}</div>}{actionMessage && <p role="alert" className="mt-3 text-sm text-red-600">{actionMessage}</p>}<div className="mt-4 flex gap-2"><button disabled={!asset.segments.length} onClick={() => { const segment = asset.segments[0]; void createHighlight(asset.id, { start_ms: segment.start_ms, end_ms: segment.end_ms, text_snapshot: segment.text, segment_id: segment.id }).then(() => { setActionMessage('已保存第一条高亮'); refresh(); }).catch((err) => setActionMessage(err instanceof Error ? err.message : '保存高亮失败')); }} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs disabled:opacity-50">保存当前片段为高亮</button><button disabled={!asset.segments.length} onClick={() => { const segment = asset.segments[0]; void createFlashcard(asset.id, { question: '这段内容讲了什么？', answer: segment.text, segment_id: segment.id }).then(() => { setActionMessage('已创建复习卡片'); refresh(); }).catch((err) => setActionMessage(err instanceof Error ? err.message : '创建卡片失败')); }} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs disabled:opacity-50">从第一段创建卡片</button></div></section>}
    </div>
  );
}
