import { useState, useRef } from 'react';
import { streamPost } from '../api/client';
import { toast } from '../components/Toast';
import { Copy, Loader2, Play } from 'lucide-react';

export default function DevTools() {
  const [cookiesInput, setCookiesInput] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const resultRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleConvert = () => {
    if (!cookiesInput.trim() || loading) return;
    setLoading(true);
    setResult('');

    let full = '';
    abortRef.current = streamPost(
      '/api/dev-tools/generate-cookies-stream',
      { cookies_text: cookiesInput },
      (data) => {
        const d = data as { content?: string; done?: boolean };
        if (d.content) {
          full += d.content;
          setResult(full);
        }
      },
      () => {
        setLoading(false);
        if (full) toast('转换完成', 'success');
      },
      (err) => {
        setResult(`错误: ${err.message}`);
        setLoading(false);
        toast('转换失败', 'error');
      },
    );
  };

  const handleCopy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result);
      setCopied(true);
      toast('已复制到剪贴板', 'success');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast('复制失败', 'error');
    }
  };

  return (
    <div className="flex h-full">
      <div className="w-96 border-r border-[var(--color-border)] bg-[var(--color-surface)] p-6 overflow-y-auto shrink-0">
        <h2 className="text-lg font-semibold text-[var(--color-text)] mb-5">开发者工具</h2>

        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text)] mb-1.5">B站 Cookies 格式转换</h3>
            <p className="text-xs text-[var(--color-text-secondary)] mb-3 leading-relaxed">
              将浏览器复制的 Cookies 转换为 yt-dlp 需要的 Netscape 格式。
            </p>
            <div className="p-3 bg-[var(--color-bg)] rounded-lg text-xs text-[var(--color-text-secondary)] space-y-1.5 leading-relaxed">
              <p className="font-medium text-[var(--color-text-secondary)]">使用步骤：</p>
              <p>1. 在浏览器中登录 bilibili.com</p>
              <p>2. 按 F12 打开开发者工具</p>
              <p>3. 切换到 Application → Cookies</p>
              <p>4. 复制所有 Cookie 值粘贴到下方</p>
            </div>
          </div>

          <textarea
            value={cookiesInput}
            onChange={(e) => setCookiesInput(e.target.value)}
            placeholder="粘贴从浏览器复制的 Cookies..."
            rows={8}
            className="w-full border border-[var(--color-border)] rounded-lg px-3 py-2.5 text-xs font-mono focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20 resize-y"
          />

          <button
            onClick={handleConvert}
            disabled={loading || !cookiesInput.trim()}
            className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium bg-[var(--color-accent)] text-white rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            转换
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {result ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-[var(--color-text)]">转换结果 (Netscape 格式)</h3>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-bg)] transition-colors"
              >
                <Copy size={12} />
                {copied ? '已复制' : '复制'}
              </button>
            </div>
            <textarea
              ref={resultRef}
              value={result}
              readOnly
              rows={20}
              className="w-full border border-[var(--color-border)] rounded-lg px-4 py-3 text-xs font-mono bg-[var(--color-bg)] resize-y focus:outline-none"
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-full bg-[var(--color-bg)] flex items-center justify-center mb-4">
              <Wrench size={24} className="text-[var(--color-text-muted)]" />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-1">Cookies 格式转换工具</p>
            <p className="text-xs text-[var(--color-text-muted)]">在左侧粘贴 Cookies 并点击转换</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Wrench(props: { size: number; className: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={props.size}
      height={props.size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={props.className}
    >
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  );
}
