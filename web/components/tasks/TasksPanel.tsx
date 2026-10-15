'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, EmptyState, ErrorBanner } from '@/components/ui';
import { TrackerStatus, msg } from '@/lib/tracker';
import { BOARD, Person, RAG_DOT, STATUS_LABEL, Task, Unit, fmtDue, tasksApi } from '@/lib/tasks';
import TaskDrawer from './TaskDrawer';
import TaskForm from './TaskForm';

type View = 'list' | 'board' | 'calendar';

function Row({ t, onOpen }: { t: Task; onOpen: () => void }) {
  return (
    <button onClick={onOpen} className="w-full rounded-lg border border-line bg-raised p-3 text-left transition-colors hover:border-primary">
      <div className="flex items-start justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${RAG_DOT[t.rag]}`} title={t.ragWhy} />
          <span className="truncate text-sm font-medium text-slate-100">{t.title}</span>
        </span>
        <span className="shrink-0 text-xs text-muted">{t.priority}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg"><div className="h-full bg-primary" style={{ width: `${t.pct}%` }} /></div>
      <p className="mt-1.5 text-xs text-muted">
        {t.progress}/{t.target_qty} {t.unitLabel} · {t.site} · due {fmtDue(t.due_at)} · {t.assignees.map((a) => a.user_name).join(', ')}
      </p>
    </button>
  );
}

function Calendar({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: number) => void }) {
  const [base, setBase] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const days = new Date(base.getFullYear(), base.getMonth() + 1, 0).getDate();
  const pad = (base.getDay() + 6) % 7;
  const key = (d: number) => `${base.getFullYear()}-${String(base.getMonth() + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <button className="btn-secondary py-1" onClick={() => setBase(new Date(base.getFullYear(), base.getMonth() - 1, 1))}>←</button>
        <span className="text-sm font-medium text-white">{base.toLocaleString('en-IN', { month: 'long', year: 'numeric' })}</span>
        <button className="btn-secondary py-1" onClick={() => setBase(new Date(base.getFullYear(), base.getMonth() + 1, 1))}>→</button>
      </div>
      <div className="overflow-x-auto">
        <div className="grid min-w-[700px] grid-cols-7 gap-1 text-xs">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="px-1 text-muted">{d}</div>)}
          {Array.from({ length: pad }).map((_, i) => <div key={`p${i}`} />)}
          {Array.from({ length: days }, (_, i) => i + 1).map((d) => (
            <div key={d} className="min-h-[84px] rounded-md border border-line bg-raised p-1">
              <div className="text-muted">{d}</div>
              {tasks.filter((t) => t.due_at.slice(0, 10) === key(d)).map((t) => (
                <button key={t.id} onClick={() => onOpen(t.id)} className="mt-0.5 flex w-full items-center gap-1 truncate rounded bg-bg px-1 py-0.5 text-left text-slate-200 hover:text-white">
                  <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${RAG_DOT[t.rag]}`} />{t.title}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">Tasks sit on their due day.</p>
    </div>
  );
}

export default function TasksPanel({ status }: { status: TrackerStatus }) {
  const isAdmin = status.isAdmin;
  const readOnly = status.role === 'viewer' || status.readOnly;
  const [view, setView] = useState<View>('list');
  const [scope, setScope] = useState<'mine' | 'all'>(isAdmin ? 'all' : 'mine');
  const [filter, setFilter] = useState({ user_id: '', project_id: '', status: '', due_before: '' });
  const [tasks, setTasks] = useState<Task[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [form, setForm] = useState<{ task?: Task } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await tasksApi.list({ scope, ...Object.fromEntries(Object.entries(filter).filter(([, v]) => v)) });
      setTasks(r.data.tasks);
    } catch (e) { setError(msg(e, 'Could not load tasks.')); }
  }, [scope, filter]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    tasksApi.people().then((r) => setPeople(r.data.people)).catch(() => undefined);
    if (isAdmin) tasksApi.plan().then((r) => setUnits(r.data.units)).catch(() => undefined);
  }, [isAdmin]);

  const counts = useMemo(() => ({
    red: tasks.filter((t) => t.rag === 'red' && t.status !== 'approved').length,
    amber: tasks.filter((t) => t.rag === 'amber' && t.status !== 'approved').length,
  }), [tasks]);

  return (
    <div className="space-y-4">
      <ErrorBanner message={error} />
      {notice && <p className="rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">{notice}</p>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1">
          {(['list', 'board', 'calendar'] as View[]).map((v) => (
            <button key={v} onClick={() => setView(v)} className={`rounded-md px-3 py-1.5 text-sm ${view === v ? 'bg-primary text-white' : 'bg-raised text-slate-300'}`}>
              {v === 'list' ? 'List' : v === 'board' ? 'Board' : 'Calendar'}
            </button>
          ))}
          {isAdmin && (
            <button onClick={() => setScope(scope === 'all' ? 'mine' : 'all')} className="ml-2 rounded-md bg-raised px-3 py-1.5 text-sm text-slate-300">
              {scope === 'all' ? 'All team ▾' : 'My tasks ▾'}
            </button>
          )}
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-danger">{counts.red} red</span>
          <span className="text-warning">{counts.amber} amber</span>
          {isAdmin && !readOnly && <button className="btn-primary" onClick={() => setForm({})}>New task</button>}
        </div>
      </div>

      {isAdmin && scope === 'all' && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <select aria-label="Person" className="input-field" value={filter.user_id} onChange={(e) => setFilter({ ...filter, user_id: e.target.value })}>
            <option value="">Everyone</option>{people.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
          </select>
          <select aria-label="Website" className="input-field" value={filter.project_id} onChange={(e) => setFilter({ ...filter, project_id: e.target.value })}>
            <option value="">All websites</option>{Object.values(status.sites).map((s) => <option key={s.id} value={s.id}>{s.short}</option>)}
          </select>
          <select aria-label="Status" className="input-field" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
            <option value="">Any status</option>{BOARD.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
          <input aria-label="Due by" type="date" className="input-field" value={filter.due_before} onChange={(e) => setFilter({ ...filter, due_before: e.target.value })} />
        </div>
      )}

      {form && (
        <Card title={form.task ? 'Edit task' : 'New SMART task'}>
          <TaskForm status={status} people={people} units={units} task={form.task}
                    onCancel={() => setForm(null)}
                    onSaved={(_, warnings) => { setForm(null); setNotice(warnings.length ? warnings.join(' ') : null); load(); }} />
        </Card>
      )}

      {tasks.length === 0 ? (
        <EmptyState title="No tasks here" description={isAdmin ? 'Create a SMART task with “New task”.' : 'Tasks Jai assigns to you show up here.'} />
      ) : view === 'list' ? (
        isAdmin && scope === 'all' ? (
          <div className="overflow-x-auto">
            <table className="data-table min-w-[820px]">
              <thead><tr><th /><th>Task</th><th>Who</th><th>Site</th><th>Progress</th><th>Status</th><th>Due</th></tr></thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.id} className="cursor-pointer" onClick={() => setOpen(t.id)}>
                    <td><span className={`inline-block h-2.5 w-2.5 rounded-full ${RAG_DOT[t.rag]}`} title={t.ragWhy} /></td>
                    <td className="text-slate-100">{t.title} <span className="text-xs text-muted">{t.priority}</span></td>
                    <td>{t.assignees.map((a) => a.user_name).join(', ')}</td>
                    <td>{t.site}</td>
                    <td className="tabular-nums">{t.progress}/{t.target_qty} {t.unitLabel}</td>
                    <td>{STATUS_LABEL[t.status]}</td>
                    <td className="whitespace-nowrap">{fmtDue(t.due_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">{tasks.map((t) => <Row key={t.id} t={t} onOpen={() => setOpen(t.id)} />)}</div>
        )
      ) : view === 'board' ? (
        <div className="overflow-x-auto">
          <div className="grid min-w-[1100px] grid-cols-6 gap-3">
            {BOARD.map((s) => (
              <div key={s} className="rounded-lg bg-bg p-2">
                <h3 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-muted">{STATUS_LABEL[s]} · {tasks.filter((t) => t.status === s).length}</h3>
                <div className="space-y-2">{tasks.filter((t) => t.status === s).map((t) => <Row key={t.id} t={t} onOpen={() => setOpen(t.id)} />)}</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <Calendar tasks={tasks} onOpen={setOpen} />
      )}

      {open !== null && (
        <TaskDrawer id={open} isAdmin={isAdmin} readOnly={readOnly}
                    onClose={() => setOpen(null)} onChanged={load}
                    onEdit={(t) => { setOpen(null); setForm({ task: t }); }} />
      )}
    </div>
  );
}
