import { LibraryBig } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { listAssets } from '../api/v2';
import type { Asset } from '../api/v2';

export default function Library() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => { listAssets().then(setAssets).catch((err) => setError(err instanceof Error ? err.message : '加载失败')).finally(() => setLoading(false)); }, []);
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-8 sm:py-12">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">知识库</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">查看已导入的来源、检索内容，并按主题整理资产。</p>
      </header>

      {loading && <p className="py-12 text-center text-sm text-[var(--color-text-secondary)]">加载中…</p>}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {!loading && assets.length > 0 && <div className="grid gap-3 sm:grid-cols-2">{assets.map((asset) => <Link key={asset.id} to={'/assets/' + asset.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 hover:border-[var(--color-accent)]"><h2 className="font-semibold">{asset.title}</h2><p className="mt-2 text-sm text-[var(--color-text-secondary)]">{asset.source_type} · {new Date(asset.created_at).toLocaleString()}</p></Link>)}</div>}
      {!loading && !error && assets.length === 0 && <section aria-labelledby="library-empty" className="rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-12 text-center">
        <LibraryBig className="mx-auto mb-4 text-[var(--color-text-secondary)]" size={30} aria-hidden="true" />
        <h2 id="library-empty" className="text-lg font-semibold">暂无可查看的资产</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--color-text-secondary)]">
          资产列表、全文检索和主题集合尚未接入。
        </p>
        <Link to="/" className="mt-5 inline-block text-sm font-medium underline underline-offset-4">返回工作台</Link>
      </section>}
    </div>
  );
}
