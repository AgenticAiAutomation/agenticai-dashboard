'use client';

import { useEffect, useState } from 'react';
import { Card, ErrorBanner, Skeleton } from '@/components/ui';
import { Ranked, Summary, TrackerStatus, msg, trackerApi } from '@/lib/tracker';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function Heatmap({ days }: { days: Summary['heatmap'] }) {
  if (!days.length) return null;
  // Monday-first calendar: pad the first week.
  const first = new Date(days[0].date + 'T00:00:00');
  const pad = (first.getDay() + 6) % 7;
  return (
    <div className="mx-auto max-w-md">
      <div className="grid grid-cols-7 gap-1.5 text-center text-[11px] text-muted">
        {WEEKDAYS.map((d) => <div key={d}>{d}</div>)}
        {Array.from({ length: pad }).map((_, i) => <div key={`p${i}`} />)}
        {days.map((d) => (
          <div
            key={d.date}
            title={`${d.date}: ${d.marks} marks${d.hit ? ' · target hit' : ''}`}
            className={`flex aspect-square items-center justify-center rounded-md text-xs ${
              d.future ? 'border border-dashed border-line text-slate-600'
                : d.hit ? 'bg-success text-white'
                : d.marks > 0 ? 'bg-success/25 text-slate-200' : 'bg-raised text-slate-500'}`}
          >
            {Number(d.date.slice(8))}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">
        <span className="mr-1 inline-block h-3 w-3 rounded bg-success align-middle" /> target hit
        <span className="ml-4 mr-1 inline-block h-3 w-3 rounded bg-success/25 align-middle" /> some marks
        <span className="ml-4 mr-1 inline-block h-3 w-3 rounded bg-raised align-middle" /> nothing approved
      </p>
    </div>
  );
}

function Board({ rows, me }: { rows: Ranked[]; me: string }) {
  if (!rows.length) return <p className="text-sm text-muted">No approved work this month yet.</p>;
  return (
    <ol className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.userId}
            className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ${r.userId === me ? 'bg-primary/15 text-white' : 'bg-raised text-slate-200'}`}>
          <span><span className="mr-3 inline-block w-6 tabular-nums text-muted">#{r.rank}</span>{r.name}</span>
          <span className="tabular-nums">{r.marks}</span>
        </li>
      ))}
    </ol>
  );
}

export default function ProgressPanel({ status }: { status: TrackerStatus }) {
  const [range, setRange] = useState<'week' | 'month'>('week');
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    trackerApi.summary(range).then((r) => setData(r.data)).catch((e) => setError(msg(e)));
  }, [range]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Skeleton className="h-64 w-full" />;

  const hit = data.series.filter((s) => s.hit).length;
  const total = data.series.reduce((a, s) => a + s.marks, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title={range === 'week' ? 'Last 7 days' : 'This month'}
          action={
            <div className="flex gap-1">
              {(['week', 'month'] as const).map((r) => (
                <button key={r} onClick={() => setRange(r)}
                        className={`rounded-md px-3 py-1 text-xs ${range === r ? 'bg-primary text-white' : 'bg-raised text-slate-300'}`}>
                  {r === 'week' ? 'Week' : 'Month'}
                </button>
              ))}
            </div>
          }
        >
          <dl className="mb-5 grid grid-cols-3 gap-4 text-center">
            <div><dt className="text-xs text-muted">Marks</dt><dd className="text-2xl font-semibold text-white">{Math.round(total * 10) / 10}</dd></div>
            <div><dt className="text-xs text-muted">Days on target</dt><dd className="text-2xl font-semibold text-white">{hit}/{data.series.length}</dd></div>
            <div><dt className="text-xs text-muted">Streak</dt><dd className="text-2xl font-semibold text-white">{data.streak}d</dd></div>
          </dl>
          <div className="space-y-1.5">
            {data.series.slice().reverse().map((s) => (
              <div key={s.date} className="flex items-center gap-3 text-xs">
                <span className="w-20 shrink-0 text-muted">{s.date.slice(5)}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-raised">
                  <div className={`h-full ${s.hit ? 'bg-success' : 'bg-primary'}`}
                       style={{ width: `${Math.min(100, (s.marks / Math.max(1, s.target)) * 100)}%` }} />
                </div>
                <span className="w-16 shrink-0 text-right tabular-nums text-slate-300">{s.marks}/{s.target}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Month calendar">
          <Heatmap days={data.heatmap} />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title={`Leaderboard · overall${data.rank ? ` · you are #${data.rank}` : ''}`}>
          <Board rows={data.leaderboard.overall} me={status.me.id} />
        </Card>
        <Card title="Leaderboard · by website">
          <div className="space-y-5">
            {Object.entries(data.leaderboard.projects).map(([p, rows]) => (
              <div key={p}>
                <h3 className="mb-2 text-sm font-medium text-slate-200">
                  {status.sites[p]?.domain || p}
                  {data.projectRanks[p] ? <span className="ml-2 text-xs text-muted">you are #{data.projectRanks[p]}</span> : null}
                </h3>
                <Board rows={rows} me={status.me.id} />
              </div>
            ))}
            {!Object.keys(data.leaderboard.projects).length && <p className="text-sm text-muted">No approved work this month yet.</p>}
          </div>
        </Card>
      </div>
    </div>
  );
}
