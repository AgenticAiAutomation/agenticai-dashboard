'use client';

import { ReactNode, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Nav from '@/components/Nav';

/**
 * Auth gate + page chrome. Rendering is deferred until the token check has run
 * so a logged-out visitor never sees a flash of dashboard content.
 */
export default function Shell({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem('access_token')) {
      router.replace('/login');
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-bg">
        <div className="mx-auto max-w-[1400px] px-4 py-10">
          <div className="skeleton h-8 w-56" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg">
      <Nav />
      <main className="mx-auto max-w-[1400px] px-4 py-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </header>
        {children}
      </main>
    </div>
  );
}
