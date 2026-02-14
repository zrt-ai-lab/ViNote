import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from '../components/Modal';
import { ArrowRight, FileText, MessageCircle, Search, BrainCircuit, MessageSquare, X, Sparkles } from 'lucide-react';

const EXAMPLES = [
  '在B站搜索Python编程',
  '在YouTube搜索机器学习',
  '帮我找React教程视频',
  '搜索深度学习入门课程',
];

const FEATURES = [
  {
    title: 'ViNoter 智搜',
    desc: '自然语言搜索视频，一键生成笔记和问答',
    icon: Search,
    route: '/search',
    color: 'red',
    badge: 'HOT',
  },
  {
    title: '视频笔记',
    desc: '输入视频链接，AI 自动生成结构化笔记',
    icon: FileText,
    route: '/note',
    color: 'blue',
    badge: null,
  },
  {
    title: '视频问答',
    desc: '基于视频内容的智能对话，随时提问',
    icon: MessageCircle,
    route: '/qa',
    color: 'violet',
    badge: null,
  },
  {
    title: '思维导图',
    desc: '可视化知识结构，一目了然掌握核心脉络',
    icon: BrainCircuit,
    route: '/mindmap',
    color: 'emerald',
    badge: 'NEW',
  },
  {
    title: '知识卡片',
    desc: '4 种风格卡片，提炼核心知识点辅助记忆',
    icon: Sparkles,
    route: '/cards',
    color: 'amber',
    badge: 'NEW',
  },
] as const;

const COLOR_MAP: Record<string, { bg: string; iconBg: string; iconText: string; badge: string; link: string }> = {
  red: {
    bg: 'bg-red-50',
    iconBg: 'bg-red-100',
    iconText: 'text-red-600',
    badge: 'bg-red-500 text-white',
    link: 'text-red-600',
  },
  blue: {
    bg: 'bg-blue-50',
    iconBg: 'bg-blue-100',
    iconText: 'text-blue-600',
    badge: 'bg-blue-500 text-white',
    link: 'text-blue-600',
  },
  violet: {
    bg: 'bg-violet-50',
    iconBg: 'bg-violet-100',
    iconText: 'text-violet-600',
    badge: 'bg-violet-500 text-white',
    link: 'text-violet-600',
  },
  emerald: {
    bg: 'bg-emerald-50',
    iconBg: 'bg-emerald-100',
    iconText: 'text-emerald-600',
    badge: 'bg-emerald-500 text-white',
    link: 'text-emerald-600',
  },
  amber: {
    bg: 'bg-amber-50',
    iconBg: 'bg-amber-100',
    iconText: 'text-amber-600',
    badge: 'bg-amber-500 text-white',
    link: 'text-amber-600',
  },
};

export default function Home() {
  const [input, setInput] = useState('');
  const [showContact, setShowContact] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = () => {
    const q = input.trim();
    if (!q) return;
    navigate(`/search?q=${encodeURIComponent(q)}`);
  };

  const handleExample = (text: string) => {
    navigate(`/search?q=${encodeURIComponent(text)}`);
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-full px-6 py-16">
      <div className="absolute top-4 right-4 flex items-center gap-2">
        <button
          onClick={() => setShowContact(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] rounded-lg transition-colors"
        >
          <MessageSquare size={13} />
          联系作者
        </button>
      </div>

      <div className="w-full max-w-3xl">
        <div className="text-center mb-10">
          <img src="/product-logo.png" alt="ViNote" className="h-14 w-auto mx-auto mb-5" />
          <h1 className="text-3xl font-bold text-[var(--color-text)] mb-3 tracking-tight">
            让每一个视频成为知识资产
          </h1>
          <p className="text-base text-[var(--color-text-secondary)] leading-relaxed">
            搜索 · 笔记 · 问答 · 思维导图 · 知识卡片 — 一站式视频知识管理
          </p>
        </div>

        <div className="max-w-xl mx-auto mb-10">
          <div className="flex items-center gap-3 bg-white border border-[var(--color-border)] rounded-xl px-4 py-3 shadow-sm focus-within:border-[var(--color-accent)] focus-within:ring-2 focus-within:ring-[var(--color-accent)]/10 transition-all">
            <Search size={16} className="text-[var(--color-text-muted)] shrink-0" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              placeholder="告诉我你想搜索什么视频..."
              className="flex-1 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] outline-none bg-transparent"
            />
            {input && (
              <button onClick={() => setInput('')} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]">
                <X size={16} />
              </button>
            )}
            <button
              onClick={handleSubmit}
              disabled={!input.trim()}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ArrowRight size={14} />
            </button>
          </div>

          <div className="flex flex-wrap gap-2 mt-4 justify-center">
            {EXAMPLES.map((text) => (
              <button
                key={text}
                onClick={() => handleExample(text)}
                className="px-3.5 py-1.5 text-xs text-[var(--color-text-secondary)] bg-[var(--color-bg)] border border-[var(--color-border)] rounded-full hover:bg-[var(--color-surface)] hover:border-[var(--color-border)] hover:text-[var(--color-text)] transition-colors"
              >
                {text}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-12">
          {FEATURES.map((feat) => {
            const colors = COLOR_MAP[feat.color];
            const Icon = feat.icon;
            return (
              <button
                key={feat.route}
                onClick={() => navigate(feat.route)}
                className={`relative flex flex-col items-start gap-3 p-5 rounded-xl border border-[var(--color-border)] ${colors.bg} text-left hover:shadow-md hover:border-[var(--color-border)] transition-all group`}
              >
                {feat.badge && (
                  <span className={`absolute top-3 right-3 px-2 py-0.5 text-[10px] font-bold rounded-full ${colors.badge}`}>
                    {feat.badge}
                  </span>
                )}
                <div className={`w-10 h-10 rounded-lg ${colors.iconBg} flex items-center justify-center`}>
                  <Icon size={20} className={colors.iconText} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[var(--color-text)] mb-1">{feat.title}</h3>
                  <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{feat.desc}</p>
                </div>
                <span className={`flex items-center gap-1 text-xs font-medium ${colors.link} mt-auto group-hover:gap-2 transition-all`}>
                  进入 <ArrowRight size={12} />
                </span>
              </button>
            );
          })}
        </div>

        <p className="text-center text-xs text-[var(--color-text-muted)]">
          ViNote v1.3.0 · 让每个视频成为你的知识资产
        </p>
      </div>

      <Modal open={showContact} onClose={() => setShowContact(false)} title="联系作者">
        <div className="flex flex-col items-center gap-4">
          <p className="text-sm text-[var(--color-text-secondary)]">扫码添加微信</p>
          <img src="/vx.jpg" alt="WeChat QR" className="w-48 h-48 rounded-lg border border-[var(--color-border)]" />
          <p className="text-xs text-[var(--color-text-muted)]">864410260@qq.com</p>
        </div>
      </Modal>
    </div>
  );
}
