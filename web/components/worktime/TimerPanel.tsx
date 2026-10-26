'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Card, EmptyState, ErrorBanner } from '@/components/ui';
import { TrackerStatus, msg } from '@/lib/tracker';
import { Category, WState, WTask, hm, slotLabel, wtApi } from '@/lib/worktime';

const STATUS: Record<string, string> = {
  todo: 'To do', in_progress: 'Running', paused: 'Paused', blocked: 'Blocked', pool: 'In the Pool',
};

function Details({ t }: { t: WTask }) {
  const parts = Object.values(t.details).filter(Boolean);
  return (
    <p className="mt-1 text-xs text-muted">
      {t.category}{parts.length ? ` · ${parts.join(' · ')}` : ''} · {t.priority}{t.due_date ? ` · due ${t.due_date}` : ''}
    </p>
  );
}

/* The live clock: server start time, corrected by the server/browser clock gap. */
function Elapsed({ start, skew }: { start: string; skew: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const i = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(i); }, []);
  const s = Math.max(0, Math.floor((now + skew - new Date(start).getTime()) / 1000));
  return <span className="font-mono text-2xl text-white">{hm(s / 60)} {String(s % 60).padStart(2, '0')}s</span>;
}

function AddTask({ s, isAdmin, onDone }: { s: WState; isAdmin: boolean; onDone: (m: string) => void }) {
  const [catId, setCatId] = useState<number>(s.categories[0]?.id ?? 0);
  const [f, setF] = useState({ title: '', priority: 'P2', due_date: '', estimate_min: '', assign_to: '' });
  const [details, setDetails] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const cat: Category | undefined = s.categories.find((c) => c.id === catId);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await wtApi.create({ ...f, category_id: catId, details, estimate_min: Number(f.estimate_min) || 0,
                           assign_to: f.assign_to || undefined, due_date: f.due_date || undefined });
      setF({ ...f, title: '' }); setDetails({}); setError(null);
      onDone('Task added.');
    } catch (err) { setError(msg(err, 'Could not add the task.')); }
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <ErrorBanner message={error} />
      <div className="sm:col-span-2">
        <label className="label" htmlFor="w-title">What is the task?</label>
        <input id="w-title" required minLength={3} className="input-field" value={f.title}
               onChange={(e) => setF({ ...f, title: e.target.value })} />
      </div>
      <div>
        <label className="label" htmlFor="w-cat">Category</label>
        <select id="w-cat" className="input-field" value={catId} onChange={(e) => { setCatId(Number(e.target.value)); setDetails({}); }}>
          {s.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {cat?.deadline_workdays ? <p className="mt-1 text-xs text-muted">Due {cat.deadline_workdays} working days after it starts.</p> : null}
      </div>
      {cat?.fields.map((fl) => (
        <div key={fl.key}>
          <label className="label" htmlFor={`w-${fl.key}`}>{fl.label}</label>
          {fl.type === 'choice' ? (
            <select id={`w-${fl.key}`} required className="input-field" value={details[fl.key] ?? ''}
                    onChange={(e) => setDetails({ ...details, [fl.key]: e.target.value })}>
              <option value="" disabled>Choose…</option>
              {fl.options?.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input id={`w-${fl.key}`} required className="input-field" value={details[fl.key] ?? ''}
                   onChange={(e) => setDetails({ ...details, [fl.key]: e.target.value })} />
          )}
        </div>
      ))}
      <div>
        <label className="label" htmlFor="w-pri">Priority</label>
        <select id="w-pri" className="input-field" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
          <option value="P1">P1 — urgent</option><option value="P2">P2 — normal</option><option value="P3">P3 — when free</option>
        </select>
      </div>
      {!cat?.deadline_workdays && (
        <div>
          <label className="label" htmlFor="w-due">Due (optional)</label>
          <input id="w-due" type="date" className="input-field" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} />
        </div>
      )}
      <div>
        <label className="label" htmlFor="w-est">Estimate, minutes (optional)</label>
        <input id="w-est" type="number" min={0} className="input-field" value={f.estimate_min}
               onChange={(e) => setF({ ...f, estimate_min: e.target.value })} />
      </div>
      {isAdmin && (
        <div>
          <label className="label" htmlFor="w-who">For</label>
          <select id="w-who" className="input-field" value={f.assign_to} onChange={(e) => setF({ ...f, assign_to: e.target.value })}>
            <option value="">Me</option>
            <option value="pool">The Task Pool (anyone can pick it)</option>
            {s.people.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
          </select>
        </div>
      )}
      <div className="sm:col-span-2"><button className="btn-primary" type="submit">Add task</button></div>
    </form>
  );
}

function ProofForm({ slot, minutes, onSave }: { slot: string; minutes: number; onSave: (b: Record<string, string>) => Promise<void> }) {
  const [f, setF] = useState({ url: '', image_name: '', logo_name: '', note: '' });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <form className="grid gap-2 rounded-lg border border-line bg-raised p-3 sm:grid-cols-2"
          onSubmit={async (e) => { e.preventDefault(); await onSave({ slot, ...f }); }}>
      <p className="text-sm font-medium text-white sm:col-span-2">{slotLabel(slot)} <span className="text-xs text-muted">· {Math.round(minutes)} min on the timer</span></p>
      <input aria-label="What you did" required className="input-field sm:col-span-2" placeholder="What you did (e.g. wrote the pricing section)" value={f.note} onChange={set('note')} />
      <input aria-label="Link" type="url" className="input-field" placeholder="Link / URL (domain and slug are read from it)" value={f.url} onChange={set('url')} />
      <input aria-label="Image name" className="input-field" placeholder="Image name (e.g. hero-banner.webp)" value={f.image_name} onChange={set('image_name')} />
      <input aria-label="Logo name" className="input-field" placeholder="Logo name" value={f.logo_name} onChange={set('logo_name')} />
      <button className="btn-primary" type="submit">Save proof</button>
    </form>
  );
}

export default function TimerPanel({ status }: { status: TrackerStatus }) {
  const [s, setS] = useState<WState | null>(null);
  const [skew, setSkew] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [blocking, setBlocking] = useState<WTask | null>(null);
  const [block, setBlock] = useState({ who: '', name: '', reason: '' });
  const [completing, setCompleting] = useState<WTask | null>(null);
  const [evidence, setEvidence] = useState('');
  const [stopAt, setStopAt] = useState('');
  const [adding, setAdding] = useState(false);
  const [suggest, setSuggest] = useState<{ list: WTask[]; approval: boolean } | null>(null);
  const readOnly = status.role === 'viewer' || status.readOnly;

  const take = (st: WState) => { setS(st); setSkew(new Date(st.now).getTime() - Date.now()); };
  const load = useCallback(async () => {
    try { take((await wtApi.state()).data); } catch (e) { setError(msg(e, 'Could not load the timer.')); }
  }, []);
  // A minute is fine: the clock ticks locally, this only picks up new 15-minute slots.
  useEffect(() => { load(); const i = setInterval(load, 60_000); return () => clearInterval(i); }, [load]);

  const act = async (fn: () => Promise<{ data: WState }>, ok?: string) => {
    try { take((await fn()).data); setError(null); if (ok) setNotice(ok); } catch (e) { setError(msg(e, 'That did not work.')); }
  };

  if (!s) return <><ErrorBanner message={error} />{!error && <p className="text-sm text-muted">Loading…</p>}</>;

  const run = s.running;
  const pct = Math.min(100, (s.work.provenMinutes / s.work.targetMinutes) * 100);
  const due = s.work.needProof;
  const workable = s.tasks.filter((t) => t.status !== 'blocked');
  const blocked = s.tasks.filter((t) => t.status === 'blocked');

  return (
    <div className="space-y-5">
      <ErrorBanner message={error} />
      {notice && <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">{notice}</p>}

      {run?.stale && (
        <Card title="You left a timer running">
          <p className="text-sm text-slate-200">
            “{run.task?.title}” started {new Date(run.interval.start_ts).toLocaleString('en-IN')} and was never stopped.
            When did you stop? Nothing else can start until you say.
          </p>
          <form className="mt-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); act(() => wtApi.endSession(stopAt), 'Saved.'); }}>
            <input aria-label="Stopped at" type="datetime-local" required className="input-field w-auto" value={stopAt} onChange={(e) => setStopAt(e.target.value)} />
            <button className="btn-primary" type="submit">Save stop time</button>
          </form>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Now">
          {run && !run.stale ? (
            <div>
              <p className="text-sm font-medium text-white">{run.task?.title ?? run.interval.type}</p>
              {run.task && <Details t={run.task} />}
              <div className="mt-3"><Elapsed start={run.interval.start_ts} skew={skew} /></div>
              {!readOnly && run.task && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button className="btn-secondary" onClick={() => act(wtApi.pause, 'Paused.')}>Pause</button>
                  <button className="btn-primary" onClick={() => { setCompleting(run.task); setEvidence(''); }}>Complete</button>
                  <button className="btn-danger" onClick={() => { setBlocking(run.task); setBlock({ who: '', name: '', reason: '' }); }}>Road blocker</button>
                </div>
              )}
            </div>
          ) : !run && <p className="text-sm text-muted">No timer running. Start a task below. Only timer time with proof counts.</p>}
        </Card>
        <Card title="Today">
          <p className="text-sm text-slate-200">
            <b className="text-white">{hm(s.work.provenMinutes)}</b> proven of {s.settings.dailyTargetHours}h ·{' '}
            <b className="text-white">{hm(s.work.leftMinutes)}</b> left
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-bg" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-2 text-xs text-muted">
            On the timer: {hm(s.work.workedMinutes)}. A {s.settings.slotMinutes}-minute block counts once it has proof.
          </p>
        </Card>
      </div>

      {completing && (
        <Card title={`Complete “${completing.title}”`}>
          <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); act(() => wtApi.complete(completing.id, evidence), 'Sent for review.').then(() => setCompleting(null)); }}>
            <input aria-label="Proof link" type="url" required className="input-field flex-1" placeholder="Proof link (the published page, doc or design)" value={evidence} onChange={(e) => setEvidence(e.target.value)} />
            <button className="btn-primary" type="submit">Complete</button>
            <button className="btn-secondary" type="button" onClick={() => setCompleting(null)}>Cancel</button>
          </form>
        </Card>
      )}

      {blocking && (
        <Card title={`Road blocker on “${blocking.title}”`}>
          <form className="grid gap-2 sm:grid-cols-2" onSubmit={async (e) => {
            e.preventDefault();
            try {
              const r = (await wtApi.block(blocking.id, { depends_on_user_id: block.who || undefined,
                                                          depends_on_name: block.who ? undefined : block.name, reason: block.reason })).data;
              take(r); setBlocking(null); setError(null);
              setSuggest({ list: r.suggestions ?? [], approval: !!r.needsApproval });
            } catch (err) { setError(msg(err, 'Could not stop the watch.')); }
          }}>
            <select aria-label="Waiting on" className="input-field" value={block.who} onChange={(e) => setBlock({ ...block, who: e.target.value })}>
              <option value="">Someone outside the team…</option>
              {s.people.filter((p) => p.user_id !== status.me.id).map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
            </select>
            {!block.who && <input aria-label="Their name" required className="input-field" placeholder="Their name (e.g. the client)" value={block.name} onChange={(e) => setBlock({ ...block, name: e.target.value })} />}
            <input aria-label="Reason" required className="input-field sm:col-span-2" placeholder="What are you waiting for?" value={block.reason} onChange={(e) => setBlock({ ...block, reason: e.target.value })} />
            <div className="flex gap-2 sm:col-span-2">
              <button className="btn-danger" type="submit">Stop the watch</button>
              <button className="btn-secondary" type="button" onClick={() => setBlocking(null)}>Cancel</button>
            </div>
          </form>
        </Card>
      )}

      {suggest && (
        <Card title="Watch stopped. Stay on track: pick your next task">
          {suggest.approval && <p className="mb-2 text-sm text-amber-200">This stop goes to Jai for approval.</p>}
          {suggest.list.length ? (
            <ul className="space-y-2">
              {suggest.list.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-2 rounded-lg border border-line bg-raised p-3">
                  <span className="min-w-0"><span className="block truncate text-sm text-white">{t.title}</span><Details t={t} /></span>
                  <button className="btn-primary shrink-0" onClick={() => act(() => wtApi.start(t.id), 'Started.').then(() => setSuggest(null))}>
                    {t.pool ? 'Pick & start' : 'Start'}
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">Nothing else in your list or the Pool. Add a task below.</p>}
          <button className="btn-secondary mt-3" onClick={() => setSuggest(null)}>Close</button>
        </Card>
      )}

      {due.length > 0 && !readOnly && (
        <Card title={`Proof needed (${due.length})`}>
          <p className="mb-3 text-xs text-muted">Every {s.settings.slotMinutes} minutes on the timer needs what you did and a link, image name or logo name. Today only; earlier days are locked.</p>
          <div className="space-y-3">
            {due.slice(0, 3).map((p) => (
              <ProofForm key={p.slot} slot={p.slot} minutes={p.minutes} onSave={(b) => act(() => wtApi.proof(b), 'Proof saved.')} />
            ))}
          </div>
        </Card>
      )}

      {s.isSuperuser && s.approve.length > 0 && (
        <Card title="Stops waiting for you">
          <ul className="space-y-2">
            {s.approve.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-raised p-3 text-sm">
                <span className="text-slate-200">“{h.title}” waiting on <b className="text-white">{h.depends_on_name}</b>: {h.reason}</span>
                <span className="flex gap-2">
                  <button className="btn-primary" onClick={() => act(() => wtApi.decide(h.id, true), 'Approved.')}>Approve</button>
                  <button className="btn-secondary" onClick={() => act(() => wtApi.decide(h.id, false), 'Rejected: that time counts as normal.')}>Reject</button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="My tasks">
        {workable.length ? (
          <ul className="space-y-2">
            {workable.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-2 rounded-lg border border-line bg-raised p-3">
                <span className="min-w-0"><span className="block truncate text-sm text-white">{t.title} <span className="text-xs text-muted">· {STATUS[t.status] ?? t.status}</span></span><Details t={t} /></span>
                {!readOnly && t.status !== 'in_progress' && (
                  <button className="btn-secondary shrink-0" onClick={() => act(() => wtApi.start(t.id))}>Start</button>
                )}
              </li>
            ))}
          </ul>
        ) : <EmptyState title="No tasks yet" description="Add one below, or pick one from the Pool." />}
        {blocked.length > 0 && (
          <div className="mt-4">
            <p className="label">Blocked</p>
            <ul className="space-y-2">
              {blocked.map((t) => {
                const h = s.holds.find((x) => x.task_id === t.id && !x.end_ts);
                return (
                  <li key={t.id} className="flex items-center justify-between gap-2 rounded-lg border border-line bg-raised p-3">
                    <span className="min-w-0 text-sm text-slate-200">{t.title}{h && <span className="block text-xs text-muted">Waiting on {h.depends_on_name}: {h.reason}{h.status === 'pending' ? ' · Jai to approve' : ''}</span>}</span>
                    {!readOnly && <button className="btn-secondary shrink-0" onClick={() => act(() => wtApi.unblock(t.id), 'Unblocked.')}>Unblock</button>}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </Card>

      {s.pool.length > 0 && (
        <Card title="Task Pool">
          <ul className="space-y-2">
            {s.pool.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-2 rounded-lg border border-line bg-raised p-3">
                <span className="min-w-0"><span className="block truncate text-sm text-white">{t.title}</span><Details t={t} /></span>
                {!readOnly && <button className="btn-primary shrink-0" onClick={() => act(() => wtApi.start(t.id), 'Picked and started.')}>Pick & start</button>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {!readOnly && (
        <Card title="Add a task">
          {adding ? <AddTask s={s} isAdmin={status.isAdmin} onDone={(m) => { setNotice(m); setAdding(false); load(); }} />
                  : <button className="btn-secondary" onClick={() => setAdding(true)}>+ Add a task</button>}
        </Card>
      )}
    </div>
  );
}
