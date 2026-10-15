'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, EmptyState, ErrorBanner } from '@/components/ui';
import { Idea, Log, msg, trackerApi } from '@/lib/tracker';
import { Task, fmtDue, tasksApi } from '@/lib/tasks';

const QUALITY = [
  { q: 1, l: '1 · 0×' },
  { q: 2, l: '2 · 0.5×' },
  { q: 3, l: '3 · 1×' },
  { q: 4, l: '4 · 1.25×' },
  { q: 5, l: '5 · 1.5×' },
];

export default function ReviewPanel({ onIdeas }: { onIdeas: () => void }) {
  const [logs, setLogs] = useState<Log[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tq, setTq] = useState<Record<number, number>>({});
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [quality, setQuality] = useState<Record<number, number>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [bulkQ, setBulkQ] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await trackerApi.queue();
      setLogs(r.data.logs);
      setIdeas(r.data.ideas);
      setTasks(r.data.tasks ?? []);
      setPicked(new Set());
    } catch (e) {
      setError(msg(e, 'Could not load the review queue.'));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const one = async (id: number, status: string) => {
    try {
      await trackerApi.review(id, { status, quality: quality[id] ?? 3, note: notes[id] });
      setLogs((all) => all.filter((l) => l.id !== id));
    } catch (e) { setError(msg(e)); }
  };
  const bulk = async (status: string) => {
    if (!picked.size) return;
    try {
      await trackerApi.reviewBulk({ ids: Array.from(picked), status, quality: bulkQ });
      load();
    } catch (e) { setError(msg(e)); }
  };
  const toggle = (id: number) => setPicked((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });

  if (loading) return <p className="text-sm text-muted">Loading…</p>;

  return (
    <div className="space-y-6">
      <ErrorBanner message={error} />
      <Card
        title={`Work waiting for review · ${logs.length}`}
        action={logs.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <button className="text-xs text-primary hover:underline"
                    onClick={() => setPicked(picked.size === logs.length ? new Set() : new Set(logs.map((l) => Number(l.id))))}>
              {picked.size === logs.length ? 'Clear' : 'Select all'}
            </button>
            <select aria-label="Quality for selected" className="input-field w-auto py-1" value={bulkQ}
                    onChange={(e) => setBulkQ(Number(e.target.value))}>
              {QUALITY.map((x) => <option key={x.q} value={x.q}>{x.l}</option>)}
            </select>
            <button className="btn-primary py-1" disabled={!picked.size} onClick={() => bulk('approved')}>
              Approve {picked.size || ''}
            </button>
          </div>
        )}
      >
        {logs.length === 0 ? (
          <EmptyState title="All caught up" description="New logs land here as the team submits them." />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table min-w-[860px]">
              <thead>
                <tr><th /><th>Person · date</th><th>Work</th><th>Proof</th><th>Quality</th><th>Note to them</th><th /></tr>
              </thead>
              <tbody>
                {logs.map((l) => {
                  const id = Number(l.id);
                  return (
                    <tr key={id}>
                      <td><input type="checkbox" aria-label="Select" checked={picked.has(id)} onChange={() => toggle(id)} /></td>
                      <td>
                        <div className="text-slate-100">{l.userName}</div>
                        <div className="text-xs text-muted">{l.date} · {l.site}{l.late && <span className="ml-1 text-warning">late (50%)</span>}</div>
                      </td>
                      <td>
                        <div>{l.workType} <span className="text-xs text-muted">· {l.baseMarks} base</span></div>
                        {l.note && <div className="text-xs text-muted">{l.note}</div>}
                        {!!l.minutes && <div className="text-xs text-muted">{l.minutes} min</div>}
                      </td>
                      <td className="max-w-[220px] truncate">
                        <a className="text-primary underline" href={l.proofUrl} target="_blank" rel="noopener noreferrer">{l.proofUrl}</a>
                      </td>
                      <td>
                        <select aria-label="Quality" className="input-field w-auto py-1" value={quality[id] ?? 3}
                                onChange={(e) => setQuality({ ...quality, [id]: Number(e.target.value) })}>
                          {QUALITY.map((x) => <option key={x.q} value={x.q}>{x.l}</option>)}
                        </select>
                      </td>
                      <td>
                        <input className="input-field py-1" placeholder="optional" value={notes[id] ?? ''}
                               onChange={(e) => setNotes({ ...notes, [id]: e.target.value })} />
                      </td>
                      <td className="whitespace-nowrap">
                        <button className="text-xs text-success hover:underline" onClick={() => one(id, 'approved')}>Approve</button>
                        <button className="ml-3 text-xs text-primary hover:underline" onClick={() => one(id, 'needs_fix')}>Needs fix</button>
                        <button className="ml-3 text-xs text-danger hover:underline" onClick={() => one(id, 'rejected')}>Reject</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {tasks.length > 0 && (
        <Card title={`Tasks submitted · ${tasks.length}`}>
          <ul className="space-y-2">
            {tasks.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-raised px-3 py-2 text-sm">
                <span className="text-slate-100">{t.title} <span className="text-xs text-muted">· {t.assignees.map((a) => a.user_name).join(', ')} · {t.progress}/{t.target_qty} {t.unitLabel} · due {fmtDue(t.due_at)} · {t.marks} marks</span></span>
                <span className="flex items-center gap-2">
                  <select aria-label="Quality" className="input-field w-auto py-1" value={tq[t.id] ?? 3} onChange={(e) => setTq({ ...tq, [t.id]: Number(e.target.value) })}>
                    {QUALITY.map((x) => <option key={x.q} value={x.q}>{x.l}</option>)}
                  </select>
                  <button className="text-xs text-success hover:underline" onClick={() => tasksApi.approve(t.id, { status: 'approved', quality: tq[t.id] ?? 3 }).then(load).catch((e) => setError(msg(e)))}>Approve</button>
                  <button className="text-xs text-primary hover:underline" onClick={() => tasksApi.approve(t.id, { status: 'needs_fix' }).then(load).catch((e) => setError(msg(e)))}>Needs fix</button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {ideas.length > 0 && (
        <Card title={`Ideas to decide · ${ideas.length}`} action={<button className="btn-secondary py-1" onClick={onIdeas}>Open Idea Board</button>}>
          <ul className="space-y-1.5 text-sm">
            {ideas.map((i) => (
              <li key={i.id} className="flex justify-between gap-3 rounded-lg bg-raised px-3 py-2">
                <span className="text-slate-100">{i.title}</span>
                <span className="text-muted">{i.user_name} · {i.site} · {i.status.replace('_', ' ')}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
