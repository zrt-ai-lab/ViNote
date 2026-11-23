import clsx from 'clsx';
import { Clapperboard, House, LibraryBig, Search, Settings } from 'lucide-react';
import { Link, NavLink, Outlet } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/', icon: House, label: '工作台' },
  { to: '/library', icon: LibraryBig, label: '知识库' },
  { to: '/search', icon: Search, label: '视频智搜' },
  { to: '/assets', icon: Clapperboard, label: '资产详情' },
  { to: '/settings', icon: Settings, label: '设置' },
];

export default function Layout() {
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[14rem_minmax(0,1fr)]">
      <aside className="border-b border-[var(--color-border)] bg-[var(--color-surface)] md:sticky md:top-0 md:flex md:h-dvh md:flex-col md:border-r md:border-b-0">
        <div className="flex items-center justify-between gap-3 px-4 py-4 md:px-5 md:py-6">
          <Link to="/" aria-label="ViNote 工作台">
            <img src="/product-logo.png" alt="ViNote" className="h-7 w-auto" />
          </Link>
          <span className="text-xs text-[var(--color-text-secondary)] md:hidden">v2.0.0</span>
        </div>

        <nav aria-label="主导航" className="grid grid-cols-4 gap-1 px-2 pb-2 md:flex md:flex-1 md:flex-col md:px-3">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => clsx(
                'flex min-h-11 flex-col items-center justify-center gap-1 rounded-lg px-1 py-2 text-xs transition-colors md:flex-row md:justify-start md:gap-3 md:px-3 md:text-sm',
                isActive
                  ? 'bg-[var(--color-accent-light)] font-semibold text-[var(--color-text)]'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg)] hover:text-[var(--color-text)]',
              )}
            >
              <Icon size={17} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>

        <footer className="hidden border-t border-[var(--color-border)] px-5 py-4 text-xs text-[var(--color-text-secondary)] md:block">
          v2.0.0
        </footer>
      </aside>

      <main className="min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
