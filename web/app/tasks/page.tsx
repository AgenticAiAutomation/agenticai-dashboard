'use client';

import { useEffect, useState } from 'react';
import LegacyTasks from '@/components/LegacyTasks';
import Shell from '@/components/Shell';
import { ErrorBanner, Skeleton } from '@/components/ui';
import IdeasPanel from '@/components/tracker/IdeasPanel';
import ProgressPanel from '@/components/tracker/ProgressPanel';
import ReportPanel from '@/components/tracker/ReportPanel';
import ReviewPanel from '@/components/tracker/ReviewPanel';
import TodayPanel from '@/components/tracker/TodayPanel';
import { TrackerStatus, WorkType, is404, msg, trackerApi } from '@/lib/tracker';

type Tab = 'today' | 'progress' | 'ideas' | 'review' | 'report';

/* /tasks/ — the Daily Tracker + Idea Board when FEATURE_DAILY_TRACKER /
   FEATURE_IDEA_BOARD are on; the old task list, unchanged, when they are off
   (the API then has no /api/tasks/status and answers 404). */
export default function TasksPage() {
  const [mode, setMode] = useState<'loading' | 'legacy' | 'tracker'>('loading');
  const [status, setStatus] = useState<TrackerStatus | null>(null);
  const [types, setTypes] = useState<WorkType[]>([]);
  const [tab, setTab] = useState<Tab>('today');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem('access_token')) {
      setMode('tracker'); // Shell redirects to /login
      return;
    }
    (async () => {
      try {
        const s = (await trackerApi.status()).data;
        setStatus(s);
        if (s.tracker) setTypes((await trackerApi.workTypes()).data.types);
        // Deep link: /tasks/?tab=review etc.; anything unknown falls back to the first tab.
        const want = new URLSearchParams(window.location.search).get('tab') as Tab | null;
        const allowed: Tab[] = [
          ...(s.tracker ? (['today', 'progress'] as Tab[]) : []),
          ...(s.ideas ? (['ideas'] as Tab[]) : []),
          ...(s.isAdmin && s.tracker ? (['review', 'report'] as Tab[]) : []),
        ];
        setTab(want && allowed.includes(want) ? want : allowed[0] ?? 'today');
        setMode('tracker');
      } catch (err) {
        if (is404(err)) setMode('legacy');
        else { setError(msg(err, 'Could not load the tracker.')); setMode('tracker'); }
      }
    })();
  }, []);

  if (mode === 'legacy') return <LegacyTasks />;

  const tabs: [Tab, string][] = status ? [
    ...(status.tracker ? ([['today', 'Today'], ['progress', 'Progress & leaderboard']] as [Tab, string][]) : []),
    ...(status.ideas ? ([['ideas', 'Idea Board']] as [Tab, string][]) : []),
    ...(status.isAdmin && status.tracker ? ([['review', 'Review queue'], ['report', 'Report & settings']] as [Tab, string][]) : []),
  ] : [];

  return (
    <Shell
      title="Daily Tracker"
      subtitle="Log what you did today for each of your websites, with proof. Approved work earns marks toward your daily target."
    >
      <ErrorBanner message={error} />
      {!status ? (
        !error && <Skeleton className="h-64 w-full" />
      ) : (
        <>
          {status.readOnly && (
            <p className="mb-4 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
              The tracker is read-only for maintenance. If it stays down, log your work in the backup Google Sheet.
            </p>
          )}
          {status.badges.length > 0 && (
            <p className="mb-4 text-sm text-slate-200">🏆 Idea winner: {status.badges.map((b) => b.month).join(', ')}</p>
          )}
          <div role="tablist" className="mb-6 flex gap-1 overflow-x-auto border-b border-line">
            {tabs.map(([k, label]) => (
              <button
                key={k}
                role="tab"
                aria-selected={tab === k}
                onClick={() => setTab(k)}
                className={`whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
                  tab === k ? 'border-primary text-white' : 'border-transparent text-muted hover:text-slate-200'}`}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === 'today' && status.tracker && <TodayPanel status={status} types={types} />}
          {tab === 'progress' && status.tracker && <ProgressPanel status={status} />}
          {tab === 'ideas' && status.ideas && <IdeasPanel status={status} />}
          {tab === 'review' && status.isAdmin && <ReviewPanel onIdeas={() => setTab('ideas')} />}
          {tab === 'report' && status.isAdmin && <ReportPanel status={status} types={types} onTypes={setTypes} />}
        </>
      )}
    </Shell>
  );
}
