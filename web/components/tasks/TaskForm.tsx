'use client';

import { FormEvent, useEffect, useState } from 'react';
import { ErrorBanner } from '@/components/ui';
import { TrackerStatus, msg } from '@/lib/tracker';
import { Person, Task, Unit, tasksApi } from '@/lib/tasks';

/* SMART task form (admins). The API refuses to save with any field empty and
   says which SMART letter is missing; the form mirrors that with `required`. */

const toLocal = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

export default function TaskForm({ status, people, units, task, onSaved, onCancel }: {
  status: TrackerStatus; people: Person[]; units: Unit[]; task?: Task;
  onSaved: (t: Task, warnings: string[]) => void; onCancel: () => void;
}) {
  const now = new Date();
  const [f, setF] = useState({
    title: task?.title ?? '', description: task?.description ?? '',
    project_id: task?.project_id ?? Object.keys(status.sites)[0] ?? '', goal: task?.goal ?? 'traffic',
    target_qty: String(task?.target_qty ?? ''), unit: task?.unit ?? 'backlinks', customUnit: '',
    proof_type: task?.proof_type ?? 'link', effort_hours: String(task?.effort_hours ?? ''),
    priority: task?.priority ?? 'P2', recurrence: task?.recurrence ?? 'none',
    start_at: task?.start_at ?? toLocal(now), due_at: task?.due_at ?? toLocal(new Date(now.getTime() + 7 * 864e5)),
    marks: task ? String(task.marks) : '', checklist: '',
  });
  const [assignees, setAssignees] = useState<string[]>(task?.assignees.map((a) => a.user_id) ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const known = units.some((u) => u.unit === f.unit);
  useEffect(() => { if (task && !units.some((u) => u.unit === task.unit)) setF((x) => ({ ...x, unit: '__custom', customUnit: task.unit })); }, [task, units]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      ...f, unit: f.unit === '__custom' ? f.customUnit.trim() : f.unit,
      target_qty: Number(f.target_qty), effort_hours: Number(f.effort_hours),
      marks: f.marks === '' ? null : Number(f.marks), assignees,
      checklist: f.checklist.split('\n').map((x) => x.trim()).filter(Boolean),
    };
    try {
      const r = task ? await tasksApi.update(task.id, body) : await tasksApi.create(body);
      onSaved(r.data.task, (r.data as { warnings?: string[] }).warnings ?? []);
    } catch (err) {
      setError(msg(err, 'The task did not save.'));
    } finally {
      setBusy(false);
    }
  };

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2"><ErrorBanner message={error} /></div>
      <fieldset className="contents">
        <div className="sm:col-span-2">
          <label className="label" htmlFor="t-title"><b className="text-primary">S</b>pecific · title</label>
          <input id="t-title" required minLength={5} className="input-field" value={f.title} onChange={set('title')}
                 placeholder="Publish 2 blogs on UiPath for CA firms" />
        </div>
        <div className="sm:col-span-2">
          <label className="label" htmlFor="t-desc">Specific · the deliverable</label>
          <textarea id="t-desc" required minLength={10} rows={2} className="input-field" value={f.description} onChange={set('description')} />
        </div>
      </fieldset>
      <div>
        <label className="label" htmlFor="t-qty"><b className="text-primary">M</b>easurable · target number</label>
        <input id="t-qty" type="number" min={1} step="any" required className="input-field" value={f.target_qty} onChange={set('target_qty')} />
      </div>
      <div>
        <label className="label" htmlFor="t-unit">Measurable · unit (what counts)</label>
        <select id="t-unit" className="input-field" value={known ? f.unit : '__custom'} onChange={set('unit')}>
          {units.map((u) => <option key={u.unit} value={u.unit}>{u.label}{u.unit === 'backlinks' || u.unit === 'blogs' || u.unit.startsWith('wt:') ? ' · counts itself' : ''}</option>)}
          <option value="__custom">Something else (counted by hand)…</option>
        </select>
        {(f.unit === '__custom' || !known) && (
          <input aria-label="Unit name" required className="input-field mt-2" placeholder="e.g. GBP posts" value={f.customUnit} onChange={set('customUnit')} />
        )}
      </div>
      <div>
        <label className="label" htmlFor="t-proof">Measurable · proof type</label>
        <select id="t-proof" className="input-field" value={f.proof_type} onChange={set('proof_type')}>
          <option value="link">Link</option>
          <option value="screenshot link">Screenshot link</option>
          <option value="document link">Document link</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor="t-effort"><b className="text-primary">A</b>chievable · effort (hours)</label>
        <input id="t-effort" type="number" min={0.5} step="0.5" required className="input-field" value={f.effort_hours} onChange={set('effort_hours')} />
      </div>
      <div>
        <label className="label" htmlFor="t-site"><b className="text-primary">R</b>elevant · website</label>
        <select id="t-site" className="input-field" value={f.project_id} onChange={set('project_id')}>
          {Object.values(status.sites).map((s) => <option key={s.id} value={s.id}>{s.domain || s.name}</option>)}
        </select>
      </div>
      <div>
        <label className="label" htmlFor="t-goal">Relevant · goal it supports</label>
        <select id="t-goal" className="input-field" value={f.goal} onChange={set('goal')}>
          <option value="traffic">Traffic</option><option value="leads">Leads</option><option value="rankings">Rankings</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor="t-start"><b className="text-primary">T</b>ime-bound · start</label>
        <input id="t-start" type="datetime-local" required className="input-field" value={f.start_at} onChange={set('start_at')} />
      </div>
      <div>
        <label className="label" htmlFor="t-due">Time-bound · due</label>
        <input id="t-due" type="datetime-local" required className="input-field" value={f.due_at} onChange={set('due_at')} />
      </div>
      <div className="sm:col-span-2">
        <span className="label">Assignees</span>
        <div className="flex flex-wrap gap-2">
          {people.filter((p) => p.role !== 'owner').map((p) => (
            <label key={p.user_id} className={`cursor-pointer rounded-md border px-2.5 py-1 text-sm ${assignees.includes(p.user_id) ? 'border-primary bg-primary/15 text-white' : 'border-line text-slate-300'}`}>
              <input type="checkbox" className="sr-only" checked={assignees.includes(p.user_id)}
                     onChange={(e) => setAssignees(e.target.checked ? [...assignees, p.user_id] : assignees.filter((a) => a !== p.user_id))} />
              {p.name}
            </label>
          ))}
          {!people.length && <p className="text-sm text-muted">People appear here once they have opened the tracker.</p>}
        </div>
      </div>
      <div>
        <label className="label" htmlFor="t-pri">Priority</label>
        <select id="t-pri" className="input-field" value={f.priority} onChange={set('priority')}>
          <option value="P1">P1 — urgent</option><option value="P2">P2 — normal</option><option value="P3">P3 — when free</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor="t-rec">Repeats</label>
        <select id="t-rec" className="input-field" value={f.recurrence} onChange={set('recurrence')}>
          <option value="none">No</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor="t-marks">Marks on approval (blank = automatic)</label>
        <input id="t-marks" type="number" min={0} className="input-field" value={f.marks} onChange={set('marks')} />
      </div>
      {!task && (
        <div>
          <label className="label" htmlFor="t-check">Checklist (one per line, optional)</label>
          <textarea id="t-check" rows={2} className="input-field" value={f.checklist} onChange={set('checklist')} />
        </div>
      )}
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <button className="btn-primary" disabled={busy || !assignees.length} type="submit">{task ? 'Save changes' : 'Create task'}</button>
        <button className="btn-secondary" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
