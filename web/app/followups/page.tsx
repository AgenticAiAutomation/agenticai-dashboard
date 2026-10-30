'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import Shell from '@/components/Shell';
import { Card, ErrorBanner } from '@/components/ui';
import FollowupBoard from '@/components/followups/FollowupBoard';
import ProjectsBilling from '@/components/followups/ProjectsBilling';
import { msg } from '@/lib/tracker';
import { Contact, Followup, KIND_LABEL, Note, PRI_STYLE, fuApi, when } from '@/lib/followups';

/* /followups/ — the CRM's follow-up desk: board, month calendar, contacts
   with their full history. Owner/admin only (the API answers 403 otherwise). */

function MonthCalendar({ onOpen }: { onOpen: (cid: number) => void }) {
  const [base, setBase] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [items, setItems] = useState<Followup[]>([]);
  const days = new Date(base.getFullYear(), base.getMonth() + 1, 0).getDate();
  const key = (d: number) => `${base.getFullYear()}-${String(base.getMonth() + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  useEffect(() => {
    fuApi.calendar(key(1), key(days)).then((r) => setItems(r.data.items)).catch(() => setItems([]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);
  const pad = (base.getDay() + 6) % 7;
  return (
    <Card title="Calendar" action={
      <div className="flex items-center gap-2">
        <button className="btn-secondary py-1" onClick={() => setBase(new Date(base.getFullYear(), base.getMonth() - 1, 1))}>←</button>
        <span className="text-sm text-white">{base.toLocaleString('en-IN', { month: 'long', year: 'numeric' })}</span>
        <button className="btn-secondary py-1" onClick={() => setBase(new Date(base.getFullYear(), base.getMonth() + 1, 1))}>→</button>
      </div>
    }>
      <div className="overflow-x-auto">
        <div className="grid min-w-[700px] grid-cols-7 gap-1 text-xs">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="px-1 text-muted">{d}</div>)}
          {Array.from({ length: pad }).map((_, i) => <div key={`p${i}`} />)}
          {Array.from({ length: days }, (_, i) => i + 1).map((d) => (
            <div key={d} className="min-h-[90px] rounded-md border border-line bg-raised p-1">
              <div className="text-muted">{d}</div>
              {items.filter((f) => f.due_at.slice(0, 10) === key(d)).map((f) => (
                <button key={f.id} onClick={() => onOpen(f.contact_id)} title={f.guide}
                        className={`mt-0.5 block w-full truncate rounded px-1 py-0.5 text-left ${f.status === 'done' ? 'text-muted line-through' : f.overdue ? 'bg-danger/20 text-white' : 'bg-bg text-slate-200'}`}>
                  {f.due_at.slice(11, 16)} {f.contact.name}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function ContactPanel({ id, onClose }: { id: number; onClose: () => void }) {
  const [c, setC] = useState<(Contact & { followups: Followup[]; notes: Note[] }) | null>(null);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    fuApi.contact(id).then((r) => { setC(r.data.contact); setEdit({}); }).catch((e) => setError(msg(e)));
  }, [id]);
  useEffect(() => { load(); }, [load]);
  if (!c) return null;
  const field = (k: 'name' | 'company' | 'phone' | 'whatsapp' | 'email' | 'city', label: string) => (
    <label className="text-xs text-muted">{label}
      <input className="input-field mt-0.5 py-1" value={edit[k] ?? c[k] ?? ''} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} />
    </label>
  );
  const history = [
    ...c.followups.map((f) => ({ at: f.done_at || f.due_at, el: (
      <li key={`f${f.id}`} className="rounded-lg bg-raised px-3 py-2">
        <span className={`badge mr-2 ${PRI_STYLE[f.priority]}`}>{f.priority}</span>
        {KIND_LABEL[f.kind]} · {f.title} · <span className="text-muted">{f.status === 'done' ? `done ${String(f.done_at).slice(0, 16).replace('T', ' ')}` : when(f.due_at, f.all_day)}</span>
        {f.outcome && <p className="mt-1 text-slate-300">→ {f.outcome}</p>}
      </li>) })),
    ...c.notes.map((n) => ({ at: n.created_at, el: (
      <li key={`n${n.id}`} className="rounded-lg border border-line px-3 py-2"><span className="text-muted">{n.created_at.slice(0, 16).replace('T', ' ')} · note</span><p className="text-slate-300">{n.text}</p></li>) })),
  ].sort((a, b) => (a.at < b.at ? 1 : -1));
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <aside className="h-full w-full max-w-lg overflow-y-auto border-l border-line bg-surface p-5" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={c.name}>
        <div className="mb-3 flex items-start justify-between">
          <h2 className="text-lg font-semibold text-white">{c.name}{c.company && <span className="text-muted"> · {c.company}</span>}</h2>
          <button onClick={onClose} className="text-muted hover:text-white" aria-label="Close">✕</button>
        </div>
        <ErrorBanner message={error} />
        <div className="mb-2 flex flex-wrap gap-3 text-sm">
          {c.phone && <a className="text-primary hover:underline" href={c.telLink}>📞 {c.phone}</a>}
          {c.waLink && <a className="text-success hover:underline" href={c.waLink} target="_blank" rel="noopener noreferrer">WhatsApp</a>}
          {c.email && <a className="text-primary hover:underline" href={`mailto:${c.email}`}>{c.email}</a>}
        </div>
        <div className="mb-4 grid grid-cols-2 gap-2">
          {field('name', 'Name')}{field('company', 'Company')}{field('phone', 'Phone')}{field('whatsapp', 'WhatsApp (if different)')}{field('email', 'Email')}{field('city', 'City')}
        </div>
        {Object.keys(edit).length > 0 && (
          <button className="btn-primary mb-4 py-1" onClick={() => fuApi.updateContact(c.id, edit).then(load).catch((e) => setError(msg(e)))}>Save contact</button>
        )}
        <div className="mb-4 flex gap-2">
          <input className="input-field py-1" placeholder="Add a note (what happened, what they said)" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn-secondary py-1" disabled={note.trim().length < 2} onClick={() => fuApi.note(c.id, note).then(() => { setNote(''); load(); }).catch((e) => setError(msg(e)))}>Add</button>
        </div>
        <h3 className="mb-2 text-sm font-semibold text-slate-200">History</h3>
        <ul className="space-y-2 text-sm">{history.map((h) => h.el)}</ul>
      </aside>
    </div>
  );
}

/* Owner only: who besides the owner may use Follow-ups and Leads. A role alone gives no access. */
function MarketingTeam() {
  const [team, setTeam] = useState<{ email: string; name: string; added_at: string }[] | null>(null);
  const [f, setF] = useState({ email: '', name: '' });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fuApi.team().then((r) => setTeam(r.data.team)).catch(() => setTeam(null)); }, []);
  if (!team) return null;
  const run = (p: Promise<{ data: { team: { email: string; name: string; added_at: string }[] } }>) =>
    p.then((r) => { setTeam(r.data.team); setError(null); setF({ email: '', name: '' }); }).catch((e) => setError(msg(e)));
  return (
    <Card title={`Marketing team · ${team.length}`}>
      <p className="mb-3 text-sm text-slate-300">Only you and these people see Follow-ups and Leads. SEO and writers don&apos;t, whatever their role.</p>
      <ErrorBanner message={error} />
      <form className="mb-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); run(fuApi.teamAdd(f.email, f.name)); }}>
        <input aria-label="Login email" type="email" required className="input-field w-64" placeholder="Their dashboard login email"
               value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <input aria-label="Name" className="input-field w-48" placeholder="Name (optional)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <button className="btn-secondary" type="submit">Add</button>
      </form>
      {team.length === 0 ? <p className="text-sm text-muted">Nobody yet: only you have access.</p> : (
        <ul className="space-y-1 text-sm">
          {team.map((m) => (
            <li key={m.email} className="flex items-center justify-between gap-2 rounded-md bg-raised px-3 py-2 text-slate-200">
              <span>{m.name ? <><b className="text-white">{m.name}</b> · </> : null}{m.email}</span>
              <button className="text-xs text-muted hover:text-white" onClick={() => {
                if (window.confirm(`Remove ${m.name || m.email}? They lose Follow-ups and Leads.`)) run(fuApi.teamRemove(m.email));
              }}>Remove</button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function FollowupsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<number | null>(null);
  const [denied, setDenied] = useState(false);
  const [key, setKey] = useState(0);

  useEffect(() => {
    const c = new URLSearchParams(window.location.search).get('contact');
    if (c) setOpen(Number(c));
  }, []);
  useEffect(() => {
    fuApi.contacts(q || undefined).then((r) => setContacts(r.data.contacts)).catch((e) => {
      if ((e as { response?: { status?: number } })?.response?.status) setDenied(true);
    });
  }, [q, key]);

  return (
    <Shell title="Follow-ups" subtitle="Who to call or meet, when, and about what — with their details and what happened last time."
           actions={<Link href="/dashboard/leads/" className="btn-secondary">WhatsApp leads →</Link>}>
      {denied ? (
        <ErrorBanner message="Follow-ups are for the owner and the marketing team (or the feature is not switched on yet)." />
      ) : (
        <div className="space-y-6">
          <FollowupBoard key={key} />
          <ProjectsBilling onChanged={() => setKey((k) => k + 1)} />
          <MarketingTeam />
          <MonthCalendar onOpen={setOpen} />
          <Card title={`Contacts · ${contacts.length}`} action={
            <input aria-label="Search contacts" className="input-field w-56 py-1" placeholder="Search name, company, phone" value={q} onChange={(e) => setQ(e.target.value)} />
          }>
            <div className="overflow-x-auto">
              <table className="data-table min-w-[640px]">
                <thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Last log</th></tr></thead>
                <tbody>
                  {contacts.map((c) => (
                    <tr key={c.id} className="cursor-pointer" onClick={() => setOpen(c.id)}>
                      <td className="text-slate-100">{c.name}</td><td>{c.company}</td><td>{c.phone || <span className="text-warning">add</span>}</td>
                      <td className="max-w-[320px] truncate text-xs text-slate-400">{c.lastLog ? `${c.lastLog.at.slice(0, 10)} · ${c.lastLog.text}` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
      {open !== null && <ContactPanel id={open} onClose={() => { setOpen(null); setKey((k) => k + 1); }} />}
    </Shell>
  );
}
