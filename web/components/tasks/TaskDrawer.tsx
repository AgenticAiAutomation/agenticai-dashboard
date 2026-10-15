'use client';

import { useEffect, useState } from 'react';
import { ErrorBanner } from '@/components/ui';
import { msg } from '@/lib/tracker';
import { RAG_DOT, STATUS_LABEL, Task, TaskStatus, fmtDue, tasksApi } from '@/lib/tasks';

/* One task: progress, status moves, checklist, links, comments; review for admins. */
export default function TaskDrawer({ id, isAdmin, readOnly, onClose, onChanged, onEdit }: {
  id: number; isAdmin: boolean; readOnly: boolean;
  onClose: () => void; onChanged: () => void; onEdit: (t: Task) => void;
}) {
  const [t, setT] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [qty, setQty] = useState('1');
  const [proof, setProof] = useState('');
  const [comment, setComment] = useState('');
  const [check, setCheck] = useState('');
  const [link, setLink] = useState('');
  const [quality, setQuality] = useState(3);
  const [note, setNote] = useState('');

  useEffect(() => {
    tasksApi.get(id).then((r) => setT(r.data.task)).catch((e) => setError(msg(e)));
  }, [id]);

  const run = async (p: Promise<{ data: { task: Task; points?: number } }>, after?: () => void) => {
    setError(null);
    try {
      const r = await p;
      setT(r.data.task);
      onChanged();
      after?.();
    } catch (e) { setError(msg(e)); }
  };
  const move = (s: TaskStatus) => t && run(tasksApi.status(t.id, s, s === 'blocked' ? reason : undefined), () => setReason(''));

  if (!t) return null;
  const mine = !readOnly;
  const open = t.status !== 'approved';
  const moves: [TaskStatus, string][] = (
    { todo: [['in_progress', 'Start'], ['submitted', 'Submit']], in_progress: [['submitted', 'Submit for review']],
      blocked: [['in_progress', 'Unblock']], needs_fix: [['in_progress', 'Fixing it'], ['submitted', 'Resubmit']],
      submitted: [['in_progress', 'Take back']], approved: [] } as Record<TaskStatus, [TaskStatus, string][]>
  )[t.status];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-surface p-5" onClick={(e) => e.stopPropagation()}
             role="dialog" aria-label={t.title}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white">{t.title}</h2>
            <p className="text-xs text-muted">{t.site} · {t.priority} · goal: {t.goal} · due {fmtDue(t.due_at)}
              {t.recurrence !== 'none' && ` · repeats ${t.recurrence}`}</p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-white" aria-label="Close">✕</button>
        </div>
        <ErrorBanner message={error} />
        <p className="mb-3 text-sm text-slate-300">{t.description}</p>

        <div className="mb-4 rounded-lg bg-raised p-3">
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-slate-200">
              <span className={`inline-block h-2.5 w-2.5 rounded-full ${RAG_DOT[t.rag]}`} />{STATUS_LABEL[t.status]} · {t.ragWhy}
            </span>
            <span className="tabular-nums text-slate-200">{t.progress} / {t.target_qty} {t.unitLabel}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-bg"><div className="h-full bg-primary" style={{ width: `${t.pct}%` }} /></div>
          <p className="mt-2 text-xs text-muted">
            {t.auto ? 'Counts itself from where the work is logged — no double entry.' : 'Add progress below with a proof link.'}
            {' '}Assignees: {t.assignees.map((a) => a.user_name).join(', ')} · {t.effort_hours} h · {t.marks} marks
          </p>
          {t.status === 'blocked' && <p className="mt-1 text-xs text-warning">Blocked: {t.blocked_reason}</p>}
          {t.review_note && <p className="mt-1 text-xs text-primary">Review: {t.review_note}</p>}
        </div>

        {mine && open && (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {moves.map(([s, l]) => <button key={s} className="btn-secondary py-1" onClick={() => move(s)}>{l}</button>)}
            {t.status !== 'blocked' && t.status !== 'submitted' && (
              <>
                <input className="input-field max-w-[200px] py-1" placeholder="What's blocking it?" value={reason} onChange={(e) => setReason(e.target.value)} />
                <button className="btn-secondary py-1" disabled={reason.trim().length < 5} onClick={() => move('blocked')}>Blocked</button>
              </>
            )}
          </div>
        )}

        {isAdmin && open && (
          <div className="mb-4 rounded-lg border border-line p-3">
            <p className="mb-2 text-sm font-medium text-slate-200">Review</p>
            <div className="flex flex-wrap items-center gap-2">
              <select aria-label="Quality" className="input-field w-auto py-1" value={quality} onChange={(e) => setQuality(Number(e.target.value))}>
                {[1, 2, 3, 4, 5].map((q) => <option key={q} value={q}>Quality {q}</option>)}
              </select>
              <input className="input-field max-w-[220px] py-1" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn-primary py-1" onClick={() => run(tasksApi.approve(t.id, { status: 'approved', quality, note }))}>Approve</button>
              <button className="btn-secondary py-1" onClick={() => run(tasksApi.approve(t.id, { status: 'needs_fix', note }))}>Needs fix</button>
              <button className="text-xs text-primary hover:underline" onClick={() => onEdit(t)}>Edit task</button>
            </div>
          </div>
        )}

        {mine && open && !t.auto && (
          <div className="mb-4 flex flex-wrap gap-2">
            <input type="number" min={1} aria-label="Quantity" className="input-field w-20 py-1" value={qty} onChange={(e) => setQty(e.target.value)} />
            <input type="url" className="input-field min-w-0 flex-1 py-1" placeholder="Proof link https://…" value={proof} onChange={(e) => setProof(e.target.value)} />
            <button className="btn-primary py-1" disabled={!proof} onClick={() => run(tasksApi.progress(t.id, Number(qty), proof), () => setProof(''))}>Add progress</button>
          </div>
        )}

        <section className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-200">Checklist</h3>
          <ul className="space-y-1">
            {t.checklist.map((c) => (
              <li key={c.id}>
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input type="checkbox" disabled={!mine && !isAdmin} checked={!!c.done} onChange={(e) => run(tasksApi.check(t.id, c.id, e.target.checked))} />
                  <span className={c.done ? 'line-through text-muted' : ''}>{c.text}</span>
                </label>
              </li>
            ))}
          </ul>
          {(mine || isAdmin) && open && (
            <div className="mt-2 flex gap-2">
              <input className="input-field py-1" placeholder="Add an item" value={check} onChange={(e) => setCheck(e.target.value)} />
              <button className="btn-secondary py-1" disabled={!check.trim()} onClick={() => run(tasksApi.addCheck(t.id, check), () => setCheck(''))}>Add</button>
            </div>
          )}
        </section>

        <section className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-200">Links</h3>
          <ul className="space-y-1 text-sm">
            {(t.links ?? []).map((l) => <li key={l.id}><a className="text-primary underline" href={l.url} target="_blank" rel="noopener noreferrer">{l.label || l.url}</a></li>)}
          </ul>
          {(mine || isAdmin) && (
            <div className="mt-2 flex gap-2">
              <input type="url" className="input-field py-1" placeholder="https://…" value={link} onChange={(e) => setLink(e.target.value)} />
              <button className="btn-secondary py-1" disabled={!link} onClick={() => run(tasksApi.link(t.id, link), () => setLink(''))}>Attach</button>
            </div>
          )}
        </section>

        {!!t.entries?.length && (
          <section className="mb-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-200">Counted work</h3>
            <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
              {t.entries.map((e) => (
                <li key={e.id} className="flex justify-between gap-2 text-slate-300">
                  <span className="truncate">{e.proof_url ? <a className="text-primary underline" href={e.proof_url} target="_blank" rel="noopener noreferrer">{e.proof_url}</a> : `${e.source} #${e.id}`}</span>
                  <span className="shrink-0 text-muted">{e.source} · {e.user_name}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h3 className="mb-2 text-sm font-semibold text-slate-200">Comments</h3>
          <ul className="space-y-2 text-sm">
            {(t.comments ?? []).map((c) => (
              <li key={c.id} className="rounded-lg bg-raised px-3 py-2 text-slate-300">
                <span className="text-xs text-muted">{c.user_name} · {c.created_at.slice(0, 16).replace('T', ' ')}</span><br />{c.text}
              </li>
            ))}
          </ul>
          {(mine || isAdmin) && (
            <div className="mt-2 flex gap-2">
              <input className="input-field py-1" placeholder="Write a comment" value={comment} onChange={(e) => setComment(e.target.value)} />
              <button className="btn-secondary py-1" disabled={!comment.trim()} onClick={() => run(tasksApi.comment(t.id, comment), () => setComment(''))}>Post</button>
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}
