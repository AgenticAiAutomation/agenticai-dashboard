'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Confetti from '@/components/Confetti';
import { Card, EmptyState, ErrorBanner } from '@/components/ui';
import { Log, Summary, TrackerStatus, WorkType, msg, trackerApi } from '@/lib/tracker';

const STATUS_STYLE: Record<string, string> = {
  submitted: 'text-warning border-warning/40 bg-warning/10',
  pending: 'text-warning border-warning/40 bg-warning/10',
  approved: 'text-success border-success/40 bg-success/10',
  needs_fix: 'text-primary border-primary/40 bg-primary/10',
  rejected: 'text-danger border-danger/40 bg-danger/10',
};
const STATUS_LABEL: Record<string, string> = {
  submitted: 'Pending review',
  pending: 'Pending review',
  approved: 'Approved',
  needs_fix: 'Needs fix',
  rejected: 'Rejected',
};

export function LogStatus({ status }: { status: string }) {
  return <span className={`badge ${STATUS_STYLE[status] ?? STATUS_STYLE.submitted}`}>{STATUS_LABEL[status] ?? status}</span>;
}

const EMPTY = { project_id: '', work_type_id: '', proof_url: '', note: '', minutes: '30', date: '' };

export default function TodayPanel({ status, types }: { status: TrackerStatus; types: WorkType[] }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [logs, setLogs] = useState<Log[]>([]);
  const [form, setForm] = useState({ ...EMPTY, project_id: status.allowed[0] ?? '', date: status.today });
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [celebrate, setCelebrate] = useState(false);

  const active = useMemo(() => types.filter((t) => t.active), [types]);
  const chosen = active.find((t) => String(t.id) === form.work_type_id);

  const load = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([trackerApi.summary('day'), trackerApi.logs({ date: status.today })]);
      setSummary(s.data);
      setLogs(l.data.logs);
      // Confetti once per person per day, the first time the target is hit.
      const key = `dt-confetti-${status.me.id}-${status.today}`;
      if (s.data.todayTotals.done) {
        let seen = false;
        try { seen = localStorage.getItem(key) === '1'; localStorage.setItem(key, '1'); } catch { /* private mode */ }
        if (!seen) setCelebrate(true);
      }
    } catch (err) {
      setError(msg(err, 'Could not load today.'));
    }
  }, [status.today, status.me.id]);

  useEffect(() => { load(); }, [load]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const body = { ...form, work_type_id: Number(form.work_type_id), minutes: Number(form.minutes) || 0 };
    try {
      if (editing) {
        await trackerApi.updateLog(editing, body);
        setNotice('Fixed and sent back for review.');
      } else {
        const res = await trackerApi.createLog(body);
        setNotice(res.data.message);
      }
      setForm({ ...form, proof_url: '', note: '', date: status.today });
      setEditing(null);
      await load();
    } catch (err) {
      setError(msg(err, 'That did not save.'));
    } finally {
      setBusy(false);
    }
  };

  const edit = (l: Log) => {
    setEditing(Number(l.id));
    setForm({ project_id: l.project, work_type_id: String(l.workTypeId ?? ''), proof_url: l.proofUrl,
              note: l.note, minutes: String(l.minutes ?? 0), date: l.date });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const remove = async (id: number) => {
    try { await trackerApi.deleteLog(id); await load(); } catch (err) { setError(msg(err)); }
  };

  const t = summary?.todayTotals;
  const target = summary?.target ?? status.target;
  const pct = t ? Math.min(100, (t.marks / Math.max(1, target)) * 100) : 0;
  const minDate = new Date(new Date(status.today + 'T00:00:00').getTime() - status.backdateDays * 864e5)
    .toISOString().slice(0, 10);

  if (!status.allowed.length) {
    return (
      <EmptyState
        title="You are not on any website yet"
        description="Ask the owner to add you, with your dashboard login email, in Backlink Ops → Difficulty & team. Your sites then appear here."
      />
    );
  }

  return (
    <div className="space-y-6">
      <Confetti fire={celebrate} />
      <Card title="Today">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="kpi-value">{t ? t.marks : '—'}<span className="ml-2 text-lg text-muted">/ {target} marks</span></p>
            <p className="mt-1 text-sm text-muted">
              {t?.done ? '✅ Target hit — nice work.' : 'Approved work counts toward your daily target.'}
            </p>
          </div>
          <dl className="grid grid-cols-3 gap-6 text-center">
            <div><dt className="text-xs text-muted">Items done</dt><dd className="text-xl font-semibold text-white">{t?.items ?? 0}</dd></div>
            <div><dt className="text-xs text-muted">Pending review</dt><dd className="text-xl font-semibold text-warning">{(t?.pending ?? 0) + (t?.bo_pending ?? 0)}</dd></div>
            <div><dt className="text-xs text-muted">Streak</dt><dd className="text-xl font-semibold text-white">{summary?.streak ?? 0}d</dd></div>
          </dl>
        </div>
        <div className="mt-4 h-3 w-full overflow-hidden rounded-full bg-raised" role="progressbar"
             aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
          <div className={`h-full rounded-full transition-all ${t?.done ? 'bg-success' : 'bg-primary'}`} style={{ width: `${pct}%` }} />
        </div>
        {t && t.bo_links > 0 && (
          <p className="mt-2 text-xs text-muted">
            Includes {t.bo_marks} marks from {t.bo_links} approved Backlink Ops link{t.bo_links === 1 ? '' : 's'} (capped per day).
          </p>
        )}
      </Card>

      <Card title={editing ? 'Fix this log' : 'Log your work'}>
        <ErrorBanner message={error} />
        {notice && <p className="mb-4 rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">{notice}</p>}
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="dt-project">Project</label>
            <select id="dt-project" className="input-field" value={form.project_id} required
                    onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
              {status.allowed.map((p) => (
                <option key={p} value={p}>{status.sites[p]?.domain || status.sites[p]?.name || p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="dt-type">Work type</label>
            <select id="dt-type" className="input-field" value={form.work_type_id} required
                    onChange={(e) => setForm({ ...form, work_type_id: e.target.value })}>
              <option value="">Pick one…</option>
              {active.map((w) => (
                <option key={w.id} value={w.id}>{w.name} · {w.base_marks} marks</option>
              ))}
            </select>
            {chosen?.kind === 'backlink' && (
              <p className="mt-1 text-xs text-muted">Links logged in Backlink Ops show up here on their own — only log ones that are not there.</p>
            )}
          </div>
          <div className="sm:col-span-2">
            <label className="label" htmlFor="dt-url">Proof link (required)</label>
            <input id="dt-url" type="url" required className="input-field" placeholder="https://…"
                   value={form.proof_url} onChange={(e) => setForm({ ...form, proof_url: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <label className="label" htmlFor="dt-note">
              Short note{chosen?.kind === 'other' ? ' (required — describe the work)' : ''} · {form.note.length}/{status.noteMax}
            </label>
            <input id="dt-note" className="input-field" maxLength={status.noteMax}
                   required={chosen?.kind === 'other'} value={form.note}
                   onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </div>
          <div>
            <label className="label" htmlFor="dt-min">Time spent (minutes)</label>
            <input id="dt-min" type="number" min={0} max={1440} className="input-field" value={form.minutes}
                   onChange={(e) => setForm({ ...form, minutes: e.target.value })} />
          </div>
          <div>
            <label className="label" htmlFor="dt-date">Date</label>
            <input id="dt-date" type="date" className="input-field" min={minDate} max={status.today}
                   value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            {form.date && form.date < status.today && (
              <p className="mt-1 text-xs text-warning">Logged after the day → half marks once approved.</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <button className="btn-primary" disabled={busy || status.readOnly} type="submit">
              {editing ? 'Send fix for review' : 'Log it'}
            </button>
            {editing && (
              <button type="button" className="btn-secondary" onClick={() => { setEditing(null); setForm({ ...EMPTY, project_id: status.allowed[0], date: status.today }); }}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </Card>

      <Card title={`Logged for ${status.today}`}>
        {logs.length === 0 ? (
          <p className="text-sm text-muted">Nothing yet today.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table min-w-[640px]">
              <thead>
                <tr><th>Work</th><th>Site</th><th>Proof</th><th>Status</th><th className="text-right">Marks</th><th /></tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={String(l.id)}>
                    <td>
                      <div className="font-medium text-slate-100">{l.workType}</div>
                      {l.note && <div className="text-xs text-muted">{l.note}</div>}
                      {l.reviewNote && <div className="text-xs text-primary">Review: {l.reviewNote}</div>}
                      {l.source === 'backlink_ops' && <div className="text-xs text-muted">from Backlink Ops — read only</div>}
                    </td>
                    <td>{l.site}</td>
                    <td className="max-w-[220px] truncate">
                      {l.source === 'backlink_ops' ? (
                        <a className="text-primary underline" href={l.proofUrl}>Open Backlink Ops</a>
                      ) : (
                        <a className="text-primary underline" href={l.proofUrl} target="_blank" rel="noopener noreferrer">{l.proofUrl}</a>
                      )}
                    </td>
                    <td><LogStatus status={l.status} />{l.late && <span className="ml-1 badge border-line text-muted">late</span>}</td>
                    <td className="text-right tabular-nums">{l.marks ?? '—'}</td>
                    <td className="whitespace-nowrap text-right">
                      {l.source === 'manual' && (l.status === 'submitted' || l.status === 'needs_fix') && (
                        <button className="text-xs text-primary hover:underline" onClick={() => edit(l)}>Edit</button>
                      )}
                      {l.source === 'manual' && l.status === 'submitted' && (
                        <button className="ml-3 text-xs text-danger hover:underline" onClick={() => remove(Number(l.id))}>Remove</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
