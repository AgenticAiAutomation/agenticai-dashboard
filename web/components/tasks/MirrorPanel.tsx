'use client';

import { useEffect, useState } from 'react';
import { Card, ErrorBanner, Skeleton } from '@/components/ui';
import { TrackerStatus, msg } from '@/lib/tracker';
import { Mirror, Person, RAG_DOT, RAG_LABEL, Signal, tasksApi } from '@/lib/tasks';

const PERIOD = { day: 'Today', week: 'This week', month: 'This month' } as const;

export function SignalTile({ s }: { s: Signal }) {
  return (
    <div className="rounded-lg border border-line bg-raised p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-muted">{PERIOD[s.period]}</span>
        <span className="flex items-center gap-1.5 text-sm font-semibold text-white">
          <span className={`inline-block h-3 w-3 rounded-full ${RAG_DOT[s.signal]}`} />{RAG_LABEL[s.signal]}
        </span>
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-white">{s.pct === null ? '—' : `${s.pct}%`}</p>
      <ul className="mt-1 space-y-0.5 text-xs text-muted">
        {s.lines.slice(0, 4).map((l, i) => <li key={i}>{l.unitLabel}: {l.actual} / {l.expected}</li>)}
        {s.overdue.length > 0 && <li className="text-danger">Overdue: {s.overdue.map((o) => o.title).join(', ')}</li>}
        {!s.lines.length && !s.overdue.length && <li>No target for this period</li>}
      </ul>
    </div>
  );
}

export default function MirrorPanel({ status }: { status: TrackerStatus }) {
  const [who, setWho] = useState<string>('');
  const [people, setPeople] = useState<Person[]>([]);
  const [m, setM] = useState<Mirror | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (status.isAdmin) tasksApi.people().then((r) => setPeople(r.data.people)).catch(() => undefined); }, [status.isAdmin]);
  useEffect(() => {
    setM(null);
    tasksApi.mirror(who || undefined).then((r) => setM(r.data)).catch((e) => setError(msg(e)));
  }, [who]);

  if (error) return <ErrorBanner message={error} />;
  return (
    <div className="space-y-6">
      {status.isAdmin && (
        <select aria-label="Whose mirror" className="input-field max-w-xs" value={who} onChange={(e) => setWho(e.target.value)}>
          <option value="">My own</option>
          {people.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
        </select>
      )}
      {!m ? <Skeleton className="h-64 w-full" /> : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {(['day', 'week', 'month'] as const).map((p) => <SignalTile key={p} s={m.signals[p]} />)}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card title={`Points · ${m.month}`}>
              <p className="kpi-value">{m.points}</p>
              <p className="mt-1 text-sm text-slate-300">
                {m.tier ? <>Tier: <b className="text-white">{m.tier.name}</b>{m.tier.bonus_note && <span className="text-muted"> · bonus {m.tier.bonus_note}</span>}</> : 'No tier yet this month'}
              </p>
              {m.nextTier && (
                <>
                  <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-raised">
                    <div className="h-full bg-primary" style={{ width: `${Math.min(100, (m.points / m.nextTier.min_points) * 100)}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-muted">{m.nextTier.gap} points to <b className="text-slate-200">{m.nextTier.name}</b>
                    {m.nextTier.bonus_note && ` (bonus ${m.nextTier.bonus_note})`}</p>
                </>
              )}
              {m.ways.length > 0 && (
                <>
                  <h3 className="mb-1 mt-4 text-sm font-semibold text-slate-200">Scope to earn more</h3>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">{m.ways.map((w) => <li key={w}>{w}</li>)}</ul>
                </>
              )}
              {m.badges.length > 0 && (
                <p className="mt-4 flex flex-wrap gap-2">{m.badges.map((b) => <span key={b.key} className="badge border-success/40 bg-success/10 text-success">🏅 {b.label}</span>)}</p>
              )}
            </Card>

            <Card title="How you work">
              <dl className="grid grid-cols-3 gap-4 text-center">
                <div><dt className="text-xs text-muted">On time</dt><dd className="text-2xl font-semibold text-white">{m.onTimePct ?? '—'}{m.onTimePct !== null && '%'}</dd></div>
                <div><dt className="text-xs text-muted">Quality avg</dt><dd className="text-2xl font-semibold text-white">{m.qualityAvg ?? '—'}</dd></div>
                <div><dt className="text-xs text-muted">Rework</dt><dd className="text-2xl font-semibold text-white">{m.rework}</dd></div>
              </dl>
              {m.rank && <p className="mt-4 text-sm text-slate-300">Rank this month: <b className="text-white">#{m.rank.rank}</b> of {m.rank.of}{!m.showRank && ' (hidden from the team)'}</p>}
              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <h3 className="mb-1 text-sm font-semibold text-success">Strengths</h3>
                  <ul className="text-sm text-slate-300">{m.strengths.map((x) => <li key={x.type}>{x.type} · {x.avg}/5</li>)}{!m.strengths.length && <li className="text-muted">Needs 2+ reviewed items per type</li>}</ul>
                </div>
                <div>
                  <h3 className="mb-1 text-sm font-semibold text-warning">To work on</h3>
                  <ul className="text-sm text-slate-300">{m.gaps.map((x) => <li key={x.type}>{x.type} · {x.avg}/5</li>)}{!m.gaps.length && <li className="text-muted">—</li>}</ul>
                </div>
              </div>
            </Card>
          </div>

          <Card title="Last 30 days">
            <div className="flex flex-wrap gap-1">
              {m.history.map((h) => (
                <span key={h.date} title={`${h.date}: ${RAG_LABEL[h.signal]}`} className={`inline-block h-6 w-6 rounded ${RAG_DOT[h.signal]}`} />
              ))}
            </div>
            <p className="mt-2 text-xs text-muted">Each square is a day: green / amber / red against your targets; grey = no target that day.</p>
          </Card>
        </>
      )}
    </div>
  );
}
