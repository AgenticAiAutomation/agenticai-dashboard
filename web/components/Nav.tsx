'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

// `external`: pages the API serves through nginx (not Next routes) — plain <a>.
// The old static /articles page was removed 2026-10-13; the SEO Articles tab
// below is the article pipeline.
type Item = { href: string; label: string; external?: boolean };

const PRIMARY: Item[] = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/dashboard/seo', label: 'SEO Operations' },
  { href: '/keywords', label: 'Keywords' },
  { href: '/seo/backlink-ops/', label: 'Backlink Ops', external: true },
  { href: '/tasks', label: 'Daily Tracker' },
];

const ADMIN: Item[] = [
  { href: '/invoices/', label: 'Invoices', external: true },
  { href: '/settings/users', label: 'Users' },
];

const SEO_TABS = [
  { href: '/dashboard/seo/inbox', label: 'Inbox' },
  { href: '/dashboard/seo/articles', label: 'Articles' },
  { href: '/dashboard/seo/calendar', label: 'Calendar' },
  { href: '/dashboard/seo/team', label: 'Team' },
  { href: '/dashboard/seo/backlinks', label: 'Backlinks' },
  { href: '/dashboard/seo/recommendations', label: 'Recommendations' },
  { href: '/dashboard/seo/technical-audit', label: 'Technical audit' },
  { href: '/dashboard/seo/articles/scoring-guide#blog-playbook', label: 'Playbook guide' },
];

export default function Nav() {
  const router = useRouter();
  const pathname = usePathname();
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    setRole(localStorage.getItem('role'));
  }, []);

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('role');
    router.push('/login');
  };

  const isAdmin = role === 'admin' || role === 'owner';
  const inSeo = pathname?.startsWith('/dashboard/seo');
  const items = isAdmin ? [...PRIMARY, ...ADMIN] : PRIMARY;

  const isActive = (href: string) =>
    href === '/dashboard' ? pathname === '/dashboard' : pathname?.startsWith(href);

  const links = items.map((item) => {
    const cls = `whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors ${
      !item.external && isActive(item.href)
        ? 'bg-primary text-white'
        : 'text-slate-300 hover:bg-raised hover:text-white'
    }`;
    return item.external ? (
      <a key={item.href} href={item.href} className={cls}>{item.label}</a>
    ) : (
      <Link key={item.href} href={item.href} className={cls}>{item.label}</Link>
    );
  });

  return (
    <nav className="border-b border-line bg-surface">
      <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between gap-6 px-4">
        <div className="flex min-w-0 items-center gap-6">
          <Link href="/dashboard" className="shrink-0 text-base font-bold text-white">
            AgenticAI <span className="text-primary">SEO</span>
          </Link>
          <div className="hidden items-center gap-1 md:flex">{links}</div>
        </div>
        <button onClick={logout} className="shrink-0 text-sm text-muted hover:text-white">
          Log out
        </button>
      </div>
      {/* Phones: the same links as a scrollable row. */}
      <div className="flex gap-1 overflow-x-auto border-t border-line px-4 py-1.5 md:hidden">{links}</div>

      {inSeo && (
        <div className="border-t border-line bg-bg">
          <div className="mx-auto flex max-w-[1400px] gap-1 overflow-x-auto px-4">
            {SEO_TABS.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                className={`whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
                  pathname?.startsWith(tab.href)
                    ? 'border-primary text-white'
                    : 'border-transparent text-muted hover:text-slate-200'
                }`}
              >
                {tab.label}
              </Link>
            ))}
          </div>
        </div>
      )}
    </nav>
  );
}
