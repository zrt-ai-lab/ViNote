import { Play } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

const ARTIFACTS = ['摘要', '问答', '高亮与批注', '复习卡片', '思维导图', '导出'];

export default function AssetDetail() {
  const { assetId } = useParams();

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-8 sm:py-12">
      <header>
        <Link to="/library" className="text-sm text-[var(--color-text-secondary)] underline underline-offset-4">返回知识库</Link>
        <h1 className="mt-3 text-3xl font-bold tracking-tight">资产详情</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
          {assetId ? '资产数据尚未接入，暂时无法加载该资产。' : '暂未选择资产。接入资产后，从知识库打开视频即可阅读和查看产物。'}
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
          <p className="mt-3 text-sm text-[var(--color-text-secondary)]">暂无转录片段。带时间戳的原文将在这里显示。</p>
        </section>
      </div>

      <section aria-labelledby="artifacts-heading" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 id="artifacts-heading" className="font-semibold">知识产物</h2>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">产物生成和导出尚未接入。</p>
        <ul className="mt-4 flex flex-wrap gap-2">
          {ARTIFACTS.map((item) => (
            <li key={item} className="rounded-full border border-[var(--color-border)] px-3 py-1 text-sm">{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
