'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Card, ErrorBanner } from '@/components/ui';
import { msg } from '@/lib/tracker';
import { Contact, Project, fuApi } from '@/lib/followups';

/* Projects & billing — Jai only (the API answers 403 to everyone else, and
   this card then hides). One-time ↔ recurring at any time; a recurring
   project gets a payment follow-up N days before its next due date. */

const CYCLE: Record<string, string> = { monthly: 'Monthly', quarterly: 'Quarterly', half_yearly: 'Half-yearly', yearly: 'Yearly' };
const day = (s: string) => new Date(s.slice(0, 10) + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

function Row({ p, sites, onSaved, setError }: { p: Project; sites: Record<string, string>; onSaved: () => void; setError: (s: string | null) => void }) {
  const save = (body: Record<string, unknown>) => fuApi.updateProject(p.id, body).then(onSaved).catch((e) => setError(msg(e)));
  const recurring = p.billing === 'recurring';
  return (
    <tr className={p.active ? '' : 'opacity-50'}>
      <td>
        <div className="text-slate-100">{p.name}</div>
        <div className="text-xs text-muted">{sites[p.site_id] || p.site_id || '—'} · {p.contact?.name}{p.contact?.phone ? ` · ${p.contact.phone}` : ''}</div>
      </td>
      <td>
        <div className="inline-flex overflow-hidden rounded-md border border-line text-xs" role="group" aria-label="Billing">
          {(['one_time', 'recurring'] as const).map((b) => (
            <button key={b} type="button" aria-pressed={p.billing === b}
                    onClick={() => p.billing !== b && save(b === 'recurring' && !p.next_due ? { billing: b, next_due: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10) } : { billing: b })}
                    className={`px-2.5 py-1 ${p.billing === b ? 'bg-primary text-white' : 'bg-raised text-slate-300'}`}>
              {b === 'one_time' ? 'One-time' : 'Recurring'}
            </button>
          ))}
        </div>
      </td>
      <td>
        <select aria-label="Cycle" disabled={!recurring} className="input-field w-auto py-1" value={p.cycle} onChange={(e) => save({ cycle: e.target.value })}>
          {Object.entries(CYCLE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </td>
      <td>
        <input aria-label="Next payment date" type="date" disabled={!recurring} className="input-field w-auto py-1" defaultValue={p.next_due ?? ''}
               onBlur={(e) => e.target.value && e.target.value !== p.next_due && save({ next_due: e.target.value })} />
        {recurring && p.daysToDue !== undefined && (
          <div className={`text-xs ${p.daysToDue <= 7 ? 'text-danger' : 'text-muted'}`}>{p.daysToDue < 0 ? `${-p.daysToDue} days overdue` : `in ${p.daysToDue} days`}</div>
        )}
      </td>
      <td>
        <input aria-label="Amount" className="input-field py-1" defaultValue={p.amount_note} placeholder="e.g. ₹25,000 + GST"
               onBlur={(e) => e.target.value !== p.amount_note && save({ amount_note: e.target.value })} />
      </td>
      <td className="text-xs">
        {recurring && p.reminder ? (p.reminder.status === 'open' ? `Reminder ${day(p.reminder.due_at)}` : p.reminder.status) : '—'}
      </td>
      <td><input type="checkbox" aria-label="Active" checked={!!p.active} onChange={(e) => save({ active: e.target.checked })} /></td>
    </tr>
  );
}

export default function ProjectsBilling({ onChanged }: { onChanged?: () => void }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof fuApi.projects>>['data'] | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [f, setF] = useState({ name: '', site_id: '', contact: 'new', customer: '', billing: 'one_time', cycle: 'monthly', next_due: '', amount_note: '' });

  const load = useCallback(() => {
    fuApi.projects().then((r) => setData(r.data)).catch(() => setHidden(true));
    fuApi.contacts().then((r) => setContacts(r.data.contacts)).catch(() => undefined);
  }, []);
  useEffect(() => { load(); }, [load]);
  const saved = () => { load(); onChanged?.(); };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await fuApi.createProject({
        name: f.name, site_id: f.site_id, billing: f.billing, cycle: f.cycle, next_due: f.next_due || null, amount_note: f.amount_note,
        ...(f.contact === 'new' ? (f.customer ? { contact: { name: f.customer } } : {}) : { contact_id: Number(f.contact) }),
      });
      setF({ ...f, name: '', customer: '', next_due: '', amount_note: '' });
      saved();
    } catch (err) { setError(msg(err)); }
  };

  if (hidden || !data) return null;
  return (
    <Card title="Projects & billing (only you see this)">
      <ErrorBanner message={error} />
      <div className="overflow-x-auto">
        <table className="data-table min-w-[900px]">
          <thead><tr><th>Project · customer</th><th>Billing</th><th>Cycle</th><th>Next payment</th><th>Amount</th><th>Follow-up</th><th>Active</th></tr></thead>
          <tbody>
            {data.projects.map((p) => <Row key={p.id} p={p} sites={data.sites} onSaved={saved} setError={setError} />)}
            {!data.projects.length && <tr><td colSpan={7} className="text-muted">No projects yet — add one below.</td></tr>}
          </tbody>
        </table>
      </div>
      <form onSubmit={add} className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <input required minLength={2} aria-label="Project name" className="input-field" placeholder="Project name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <select aria-label="Website" className="input-field" value={f.site_id} onChange={(e) => setF({ ...f, site_id: e.target.value })}>
          <option value="">No website / other work</option>
          {Object.entries(data.sites).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select aria-label="Customer" className="input-field" value={f.contact} onChange={(e) => setF({ ...f, contact: e.target.value })}>
          <option value="new">+ New customer</option>
          {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}{c.company ? ` (${c.company})` : ''}</option>)}
        </select>
        {f.contact === 'new' && <input aria-label="Customer name" className="input-field" placeholder="Customer name" value={f.customer} onChange={(e) => setF({ ...f, customer: e.target.value })} />}
        <select aria-label="Billing" className="input-field" value={f.billing} onChange={(e) => setF({ ...f, billing: e.target.value })}>
          <option value="one_time">One-time</option><option value="recurring">Recurring</option>
        </select>
        {f.billing === 'recurring' && (
          <>
            <select aria-label="Cycle" className="input-field" value={f.cycle} onChange={(e) => setF({ ...f, cycle: e.target.value })}>
              {Object.entries(CYCLE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <input required aria-label="Next payment date" type="date" className="input-field" value={f.next_due} onChange={(e) => setF({ ...f, next_due: e.target.value })} />
          </>
        )}
        <input aria-label="Amount" className="input-field" placeholder="Amount (note)" value={f.amount_note} onChange={(e) => setF({ ...f, amount_note: e.target.value })} />
        <button className="btn-primary" type="submit">Add project</button>
      </form>
      <p className="mt-3 text-xs text-muted">
        Recurring projects get a P1 payment follow-up {data.remindDays} days before the due date. Mark it done when paid and the
        next date moves on one cycle. Switch any project between one-time and recurring at any time.
      </p>
    </Card>
  );
}
