'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { Card, ErrorBanner } from '@/components/ui';
import { msg } from '@/lib/tracker';
import { Board, Contact, Followup, KIND_LABEL, Kind, PRI_STYLE, fuApi, when } from '@/lib/followups';

/* The follow-up guide: To do (overdue first, then today by priority),
   Upcoming, Done — each with contact details and the last meeting's log.
   Used on the homepage (compact) and on /followups/. Hidden when the API
   says no (403 = not the owner or on the marketing list; 404 = switched off). */

const toLocal = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

function ContactLine({ c }: { c: Contact }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {c.phone && <a href={c.telLink} className="text-primary hover:underline">📞 {c.phone}</a>}
      {c.waLink && <a href={c.waLink} target="_blank" rel="noopener noreferrer" className="text-success hover:underline">WhatsApp</a>}
      {c.email && <a href={`mailto:${c.email}`} className="text-primary hover:underline">{c.email}</a>}
      {!c.phone && !c.email && <Link href={`/followups/?contact=${c.id}`} className="text-warning hover:underline">add phone / email</Link>}
    </div>
  );
}

function Item({ f, onChanged, setError }: { f: Followup; onChanged: () => void; setError: (s: string | null) => void }) {
  const [closing, setClosing] = useState(false);
  const [outcome, setOutcome] = useState('');
  const [nextOn, setNextOn] = useState(false);
  const [next, setNext] = useState({ kind: f.kind as Kind, due_at: toLocal(new Date(Date.now() + 2 * 864e5)), title: '', priority: f.priority });

  const finish = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await fuApi.done(f.id, outcome, nextOn ? { ...next, title: next.title || f.title } : undefined);
      setClosing(false);
      onChanged();
    } catch (err) { setError(msg(err)); }
  };

  return (
    <li className={`rounded-lg border p-3 ${f.overdue ? 'border-danger/50 bg-danger/5' : 'border-line bg-raised'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-100">{f.guide}</p>
          <p className="mt-0.5 text-xs text-muted">
            <span className={`badge mr-2 ${PRI_STYLE[f.priority]}`}>{f.priority}</span>
            {KIND_LABEL[f.kind]} · {f.status === 'done' ? `done ${f.done_at?.slice(0, 16).replace('T', ' ')}` : when(f.due_at, f.all_day)}
            {f.overdue && <b className="ml-1 text-danger">overdue</b>}
            {f.location && ` · 📍 ${f.location}`}
          </p>
          <ContactLine c={f.contact} />
          {f.status === 'done' && f.outcome && <p className="mt-1 text-xs text-slate-300">Outcome: {f.outcome}</p>}
          {f.status !== 'done' && f.contact.lastLog && (
            <p className="mt-1 text-xs text-slate-400">Last time ({f.contact.lastLog.at.replace('T', ' ')}): {f.contact.lastLog.text}</p>
          )}
        </div>
        {f.status === 'open' && !closing && (
          <div className="flex shrink-0 gap-2">
            <button className="btn-primary py-1 text-xs" onClick={() => setClosing(true)}>Done</button>
            <button className="btn-secondary py-1 text-xs" title="Move to tomorrow"
                    onClick={() => fuApi.snooze(f.id).then(onChanged).catch((e) => setError(msg(e)))}>+1 day</button>
          </div>
        )}
      </div>
      {closing && (
        <form onSubmit={finish} className="mt-3 space-y-2">
          <textarea required minLength={3} rows={2} className="input-field" placeholder="What happened? (this is the log for next time)"
                    value={outcome} onChange={(e) => setOutcome(e.target.value)} />
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input type="checkbox" checked={nextOn} onChange={(e) => setNextOn(e.target.checked)} /> Book the next follow-up
          </label>
          {nextOn && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
              <select aria-label="Kind" className="input-field py-1" value={next.kind} onChange={(e) => setNext({ ...next, kind: e.target.value as Kind })}>
                {(Object.keys(KIND_LABEL) as Kind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
              </select>
              <input aria-label="When" type="datetime-local" className="input-field py-1" value={next.due_at} onChange={(e) => setNext({ ...next, due_at: e.target.value })} />
              <input aria-label="About" className="input-field py-1" placeholder={f.title} value={next.title} onChange={(e) => setNext({ ...next, title: e.target.value })} />
              <select aria-label="Priority" className="input-field py-1" value={next.priority} onChange={(e) => setNext({ ...next, priority: e.target.value as Followup['priority'] })}>
                <option value="P1">P1 urgent</option><option value="P2">P2</option><option value="P3">P3</option>
              </select>
            </div>
          )}
          <div className="flex gap-2">
            <button className="btn-primary py-1 text-xs" type="submit">Save</button>
            <button className="btn-secondary py-1 text-xs" type="button" onClick={() => setClosing(false)}>Cancel</button>
          </div>
        </form>
      )}
    </li>
  );
}

export function AddFollowup({ onSaved }: { onSaved: () => void }) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [cid, setCid] = useState<string>('new');
  const [nc, setNc] = useState({ name: '', company: '', phone: '', email: '' });
  const [f, setF] = useState({ kind: 'call' as Kind, title: '', due_at: toLocal(new Date(Date.now() + 864e5)), priority: 'P2', location: '' });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fuApi.contacts().then((r) => setContacts(r.data.contacts)).catch(() => undefined); }, []);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await fuApi.create({ ...f, ...(cid === 'new' ? { contact: nc } : { contact_id: Number(cid) }) });
      setF({ ...f, title: '', location: '' });
      setNc({ name: '', company: '', phone: '', email: '' });
      onSaved();
    } catch (err) { setError(msg(err)); }
  };

  return (
    <form onSubmit={save} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="sm:col-span-2 lg:col-span-4"><ErrorBanner message={error} /></div>
      <select aria-label="Contact" className="input-field" value={cid} onChange={(e) => setCid(e.target.value)}>
        <option value="new">+ New contact</option>
        {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}{c.company ? ` (${c.company})` : ''}</option>)}
      </select>
      {cid === 'new' && (
        <>
          <input required aria-label="Name" className="input-field" placeholder="Name" value={nc.name} onChange={(e) => setNc({ ...nc, name: e.target.value })} />
          <input aria-label="Company" className="input-field" placeholder="Company" value={nc.company} onChange={(e) => setNc({ ...nc, company: e.target.value })} />
          <input aria-label="Phone" className="input-field" placeholder="Phone" value={nc.phone} onChange={(e) => setNc({ ...nc, phone: e.target.value })} />
        </>
      )}
      <select aria-label="Kind" className="input-field" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as Kind })}>
        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
      </select>
      <input required minLength={3} aria-label="About" className="input-field lg:col-span-2" placeholder="About what? e.g. pending payment" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
      <input required aria-label="When" type="datetime-local" className="input-field" value={f.due_at} onChange={(e) => setF({ ...f, due_at: e.target.value })} />
      <select aria-label="Priority" className="input-field" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
        <option value="P1">P1 — urgent</option><option value="P2">P2 — normal</option><option value="P3">P3 — low</option>
      </select>
      <input aria-label="Where" className="input-field" placeholder="Where (optional)" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} />
      <button className="btn-primary" type="submit">Add follow-up</button>
    </form>
  );
}

export default function FollowupBoard({ compact = false }: { compact?: boolean }) {
  const [b, setB] = useState<Board | null>(null);
  const [hidden, setHidden] = useState(false);
  const [tab, setTab] = useState<'todo' | 'upcoming' | 'done'>('todo');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const first = useRef(true);
  const load = useCallback(async () => {
    // Only the owner and the marketing team list see it; everyone else gets a 403 and it stays hidden.
    if (!(await fuApi.status().then((r) => r.data.allowed).catch(() => false))) { setHidden(true); return; }
    fuApi.board().then((r) => {
      setB(r.data);
      // Open on what matters: To do if anything is due, else Upcoming.
      if (first.current) { first.current = false; if (!r.data.todo.length && r.data.upcoming.length) setTab('upcoming'); }
    }).catch(() => setHidden(true));
  }, [compact]);
  useEffect(() => { load(); }, [load]);

  if (hidden || !b) return null;
  const lists = { todo: b.todo, upcoming: b.upcoming, done: b.done };
  const items = compact ? lists[tab].slice(0, 8) : lists[tab];

  return (
    <Card
      title={`Follow-ups · ${b.overdue} overdue · ${b.today} today`}
      action={
        <div className="flex items-center gap-2">
          <button className="btn-secondary py-1 text-xs" onClick={() => setAdding(!adding)}>{adding ? 'Close' : '+ Add'}</button>
          {compact && <Link href="/followups/" className="text-xs text-primary hover:underline">Open CRM follow-ups →</Link>}
        </div>
      }
      className="mb-6"
    >
      <ErrorBanner message={error} />
      {adding && <div className="mb-4"><AddFollowup onSaved={() => { setAdding(false); load(); }} /></div>}
      <div role="tablist" className="mb-3 flex gap-1">
        {([['todo', `To do (${b.todo.length})`], ['upcoming', `Upcoming (${b.upcoming.length})`], ['done', 'Done']] as const).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={`rounded-md px-3 py-1 text-sm ${tab === k ? 'bg-primary text-white' : 'bg-raised text-slate-300'}`}>{l}</button>
        ))}
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{tab === 'todo' ? 'Nothing due — all caught up.' : tab === 'upcoming' ? 'Nothing in the next 14 days.' : 'Nothing done yet.'}</p>
      ) : (
        <ul className="space-y-2">{items.map((f) => <Item key={f.id} f={f} onChanged={load} setError={setError} />)}</ul>
      )}
      {compact && lists[tab].length > items.length && (
        <Link href="/followups/" className="mt-2 inline-block text-xs text-primary hover:underline">+{lists[tab].length - items.length} more</Link>
      )}
      {tab === 'upcoming' && b.later > 0 && <p className="mt-2 text-xs text-muted">{b.later} more after 14 days — see the calendar.</p>}
    </Card>
  );
}
