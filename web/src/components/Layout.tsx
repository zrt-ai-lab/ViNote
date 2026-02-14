import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Home,
  FileText,
  MessageCircle,
  Search,
  Wrench,
  PanelLeftClose,
  PanelLeft,
  BrainCircuit,
  Sparkles,
  Clock,
} from 'lucide-react';
import clsx from 'clsx';
import Toast from './Toast';

interface NavGroup {
  title?: string;
  items: { to: string; icon: typeof Home; label: string; badge?: string }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { to: '/', icon: Home, label: '工作台' },
      { to: '/search', icon: Search, label: 'ViNoter 智搜', badge: 'HOT' },
    ],
  },
  {
    title: '工具箱',
    items: [
      { to: '/note', icon: FileText, label: '视频笔记' },
      { to: '/qa', icon: MessageCircle, label: '视频问答' },
      { to: '/mindmap', icon: BrainCircuit, label: '思维导图', badge: 'NEW' },
      { to: '/cards', icon: Sparkles, label: '知识卡片', badge: 'NEW' },
    ],
  },
  {
    title: '更多',
    items: [
      { to: '/history', icon: Clock, label: '历史记录' },
      { to: '/dev-tools', icon: Wrench, label: '开发者工具' },
    ],
  },
];

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const isHome = location.pathname === '/';

  return (
    <div className="flex h-screen overflow-hidden">
      <aside
        className={clsx(
          'flex flex-col bg-[var(--color-surface)] border-r border-[var(--color-border)] transition-all duration-200 shrink-0',
          collapsed ? 'w-0 overflow-hidden' : 'w-60',
        )}
      >
        <div className="h-14 flex items-center px-5 border-b border-[var(--color-border-light)] gap-3 shrink-0">
          <img src="/product-logo.png" alt="ViNote" className="h-7 w-auto" />
        </div>

        <nav className="flex-1 py-3 px-3 overflow-y-auto">
          {NAV_GROUPS.map((group, gi) => (
            <div key={gi} className={gi > 0 ? 'mt-5' : ''}>
              {group.title && (
                <div className="pb-2 px-3">
                  <span className="text-[11px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider">
                    {group.title}
                  </span>
                </div>
              )}
              <div className="space-y-0.5">
                {group.items.map(({ to, icon: Icon, label, badge }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === '/'}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] transition-colors',
                        isActive
                          ? 'bg-[var(--color-accent-light)] text-[var(--color-accent)] font-medium'
                          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg)] hover:text-[var(--color-text)]',
                      )
                    }
                  >
                    <Icon size={17} strokeWidth={1.8} />
                    <span className="flex-1">{label}</span>
                    {badge && (
                      <span
                        className={clsx(
                          'px-1.5 py-0.5 text-[10px] font-semibold rounded',
                          badge === 'HOT' && 'bg-red-50 text-red-500',
                          badge === 'NEW' && 'bg-emerald-50 text-emerald-600',
                        )}
                      >
                        {badge}
                      </span>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="p-4 text-[11px] text-[var(--color-text-muted)] border-t border-[var(--color-border-light)]">v1.3.0</div>
      </aside>

      <button
        onClick={() => setCollapsed(!collapsed)}
        className={clsx(
          'fixed top-4 z-50 w-8 h-8 flex items-center justify-center rounded-lg',
          'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:border-[var(--color-border)]',
          'transition-all duration-200 shadow-sm',
          collapsed ? 'left-3' : 'left-[228px]',
        )}
      >
        {collapsed ? <PanelLeft size={15} /> : <PanelLeftClose size={15} />}
      </button>

      <main className={clsx('flex-1 overflow-auto', isHome && 'bg-[var(--color-surface)]')}>
        <Outlet />
      </main>

      <Toast />
    </div>
  );
}
