'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import LeadBell from '@/components/LeadBell';
import { navRoutes, pathOf, seoTabs } from '@/lib/registry';

// Every link here comes from the route registry (web/lib/routes.json):
// `nav` entries for the top bar, `tab` entries for the SEO sub-tabs.
// `server` pages are served by the API through nginx — plain <a>, not <Link>.
type Item = { href: string; label: string; external?: boolean };

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

  const inSeo = pathname?.startsWith('/dashboard/seo');
  const items: Item[] = navRoutes(role).map((r) => ({
    href: r.server ? r.slug : pathOf(r.slug), label: r.navTitle ?? r.title, external: r.server }));
  const tabs = seoTabs(role).map((r) => ({ href: r.slug.replace(/\/(#|$)/, '$1'), label: r.tabTitle ?? r.title }));

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
        <div className="flex shrink-0 items-center gap-2">
          {/* The leads desk (CRM) is owner-only, so only the owner gets the
              new-lead bell; it hides itself on a 404 as well. */}
          {role === 'owner' && <LeadBell />}
          <button onClick={logout} className="text-sm text-muted hover:text-white">
            Log out
          </button>
        </div>
      </div>
      {/* Phones: the same links as a scrollable row. */}
      <div className="flex gap-1 overflow-x-auto border-t border-line px-4 py-1.5 md:hidden">{links}</div>

      {inSeo && (
        <div className="border-t border-line bg-bg">
          <div className="mx-auto flex max-w-[1400px] gap-1 overflow-x-auto px-4">
            {tabs.map((tab) => (
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
