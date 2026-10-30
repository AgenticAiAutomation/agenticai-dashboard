'use client';

import { useEffect, useState } from 'react';
import { Card, EmptyState, ErrorBanner } from '@/components/ui';
import { msg } from '@/lib/tracker';
import { BigIdea, IdeaBoard, wtApi } from '@/lib/worktime';

/* v3 Big Ideas: how to make Agentic AI Automation the most watched company on the internet.
   Open board: everyone checks nobody gave the idea already. Jai decides and assigns. */

const LABEL: Record<string, string> = {
  new: 'New', assigned: 'Assigned to apply', worked: 'Worked', not_applied: 'Not applied yet', repeat: 'Repeat (not counted)',
};
const TONE: Record<string, string> = {
  new: 'bg-bg text-slate-200', assigned: 'bg-primary/20 text-blue-200', worked: 'bg-emerald-500/20 text-emerald-300',
  not_applied: 'bg-bg text-muted', repeat: 'bg-danger/15 text-red-300',
};

function Decide({ i, b, done }: { i: BigIdea; b: IdeaBoard; done: (p: Promise<{ data: IdeaBoard }>, ok: string) => unknown }) {
  const [f, setF] = useState({ status: i.status, assign_to: i.assigned_to ?? '', project: i.project, note: i.note });
  return (
    <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); done(wtApi.decideIdea(i.id, f), 'Saved.'); }}>
      <select aria-label="Status" className="input-field w-auto" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
        {b.statuses.map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}
      </select>
      {f.status === 'assigned' && (
        <>
          <select aria-label="Who applies it" required className="input-field w-auto" value={f.assign_to} onChange={(e) => setF({ ...f, assign_to: e.target.value })}>
            <option value="" disabled>Who applies it…</option>
            {b.people.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
          </select>
          <input aria-label="Project" required list="idea-projects" className="input-field w-auto" placeholder="Which project"
                 value={f.project} onChange={(e) => setF({ ...f, project: e.target.value })} />
          <datalist id="idea-projects">{b.projects.map((p) => <option key={p} value={p} />)}</datalist>
        </>
      )}
      <input aria-label="Note" className="input-field w-auto flex-1" placeholder="Note (what it achieved, why not yet…)"
             value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
      <button className="btn-secondary" type="submit">Save</button>
    </form>
  );
}

export default function BigIdeasPanel() {
  const [b, setB] = useState<IdeaBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [form, setForm] = useState({ title: '', channel: '', idea: '' });
  const [filter, setFilter] = useState('');

  useEffect(() => { wtApi.ideas().then((r) => setB(r.data)).catch((e) => setError(msg(e, 'Could not load the ideas.'))); }, []);

  const done = (p: Promise<{ data: IdeaBoard }>, ok: string) =>
    p.then((r) => { setB(r.data); setError(null); setNotice(ok); return true; })
     .catch((e) => { setError(msg(e, 'That did not work.')); return false; });

  if (!b) return error ? <ErrorBanner message={error} /> : null;
  const me = b.people.find((p) => p.user_id === b.me);
  const q = filter.trim().toLowerCase();
  const shown = q ? b.ideas.filter((i) => `${i.title} ${i.idea} ${i.channel}`.toLowerCase().includes(q)) : b.ideas;
  const nominees = b.people.filter((p) => p.nominated);

  return (
    <div className="space-y-5">
      <ErrorBanner message={error} />
      {notice && <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">{notice}</p>}

      <Card title="Big Ideas">
        <p className="text-sm text-slate-200">
          How do we make <b className="text-white">Agentic AI Automation</b> the most watched company on the internet:
          social media, Google, ChatGPT, Gemini, DeepSeek, Grok, Perplexity, Claude, Copilot, Google Maps, Apple Maps?
        </p>
        <p className="mt-2 text-sm text-slate-200">
          {b.required} idea a month is required. {b.forNomination} counted ideas in a month nominate you for Employee of the Month;
          the most proven and applied ideas decide it. An idea anyone gave before (Jai too) doesn&apos;t count, so search the board first.
        </p>
        <p className="mt-2 text-xs text-muted">Leaves and hours don&apos;t decide pay, growth or your future here. Smart, quality delivery does.</p>
        {me && (
          <p className="mt-3 flex flex-wrap gap-2">
            <span className={`rounded-full px-3 py-1 text-xs ${me.counted >= b.required ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'}`}>
              {me.counted >= b.required ? 'This month’s idea: done' : 'This month’s idea: still due'}
            </span>
            <span className={`rounded-full px-3 py-1 text-xs ${me.nominated ? 'bg-emerald-500/20 text-emerald-300' : 'bg-bg text-slate-200'}`}>
              {me.nominated ? 'Nominated for Employee of the Month' : `${me.counted} of ${b.forNomination} for nomination`}
            </span>
          </p>
        )}
      </Card>

      <Card title="Give an idea">
        <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => {
          e.preventDefault();
          done(wtApi.submitIdea(form), 'Idea added. Jai will review it.').then((ok) => ok && setForm({ title: '', channel: '', idea: '' }));
        }}>
          <input aria-label="Title" required minLength={4} maxLength={140} className="input-field" placeholder="Short title"
                 value={form.title} onChange={(e) => { setForm({ ...form, title: e.target.value }); setFilter(e.target.value); }} />
          <select aria-label="Where it makes us show up" required className="input-field" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
            <option value="" disabled>Where it makes us show up…</option>
            {b.channels.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <textarea aria-label="How it works" required minLength={20} maxLength={2000} rows={3} className="input-field sm:col-span-2"
                    placeholder="How it works, step by step, and how we'd know it worked" value={form.idea} onChange={(e) => setForm({ ...form, idea: e.target.value })} />
          <div className="sm:col-span-2"><button className="btn-primary" type="submit">Submit idea</button></div>
        </form>
      </Card>

      {b.isSuperuser && (
        <Card title={`Employee of the Month · ${b.month}`}>
          {b.employeeOfMonth ? <p className="text-sm text-emerald-300">🏆 {b.employeeOfMonth.name}{b.employeeOfMonth.note && ` · ${b.employeeOfMonth.note}`}</p>
            : nominees.length === 0 ? <p className="text-sm text-muted">No nominees yet ({b.forNomination} counted ideas this month).</p>
            : (
              <ul className="space-y-2 text-sm">
                {nominees.map((p) => (
                  <li key={p.user_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-raised p-3">
                    <span className="text-slate-200"><b className="text-white">{p.name}</b> · {p.counted} ideas · {p.worked} worked · {p.assigned} being applied</span>
                    <button className="btn-primary" onClick={() => {
                      if (window.confirm(`Make ${p.name} Employee of the Month for ${b.month}? This is final.`)) done(wtApi.pickEmployeeOfMonth(p.user_id), 'Chosen.');
                    }}>Choose</button>
                  </li>
                ))}
              </ul>
            )}
        </Card>
      )}

      <Card title={q ? `Ideas matching “${filter}”` : 'All ideas'}>
        <input aria-label="Search ideas" className="input-field mb-3" placeholder="Search before you submit…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        {shown.length === 0 ? <EmptyState title={q ? 'Nothing like it yet' : 'No ideas yet'} description={q ? 'Looks new. Go ahead.' : 'Be the first.'} /> : (
          <ul className="space-y-2">
            {shown.map((i) => (
              <li key={i.id} className="rounded-lg border border-line bg-raised p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <b className="text-white">{i.title}</b>
                  <span className={`rounded-full px-3 py-1 text-xs ${TONE[i.status]}`}>{LABEL[i.status]}</span>
                </div>
                <p className="mt-1 text-xs text-muted">{i.name} · {i.month} · {i.channel}
                  {i.assignedName && ` · applying: ${i.assignedName} on ${i.project}`}</p>
                <p className="mt-2 whitespace-pre-line text-slate-200">{i.idea}</p>
                {i.note && <p className="mt-1 text-xs text-slate-300">Jai: {i.note}</p>}
                {b.isSuperuser && <Decide i={i} b={b} done={done} />}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
