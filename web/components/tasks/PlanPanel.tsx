'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorBanner } from '@/components/ui';
import { TrackerStatus, msg } from '@/lib/tracker';
import { Person, Plan, Tier, download, tasksApi } from '@/lib/tasks';

/* Admin: monthly targets per person per site (auto-split into weeks and
   working days; weeks editable), leave days, role templates, RAG thresholds;
   Jai only: tiers + bonus notes, rank visibility, payout approval. */
export default function PlanPanel({ status }: { status: TrackerStatus }) {
  const thisMonth = status.today.slice(0, 7);
  const [people, setPeople] = useState<Person[]>([]);
  const [who, setWho] = useState('');
  const [month, setMonth] = useState(thisMonth);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [nt, setNt] = useState({ project_id: Object.keys(status.sites)[0] ?? '', unit: 'backlinks', qty: '' });
  const [leaveDay, setLeaveDay] = useState('');
  const [holiday, setHoliday] = useState(false);
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [canEditTiers, setCanEditTiers] = useState(false);
  const [rag, setRag] = useState({ green_min: '90', amber_min: '60' });
  const [rewards, setRewards] = useState<Awaited<ReturnType<typeof tasksApi.rewards>>['data'] | null>(null);
  const [tpl, setTpl] = useState<{ role: string; unit: string; qty_per_week: number }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const ok = (t: string) => { setNotice(t); setError(null); };
  const fail = (e: unknown) => { setError(msg(e)); setNotice(null); };

  useEffect(() => {
    tasksApi.people().then((r) => { setPeople(r.data.people); setWho((w) => w || r.data.people.find((p) => !['owner', 'admin'].includes(p.role))?.user_id || ''); }).catch(fail);
    tasksApi.tiers().then((r) => { setTiers(r.data.tiers); setCanEditTiers(r.data.canEdit); }).catch(fail);
    tasksApi.templates().then((r) => setTpl(r.data.templates)).catch(fail);
  }, []);
  const loadPlan = useCallback(() => { if (who) tasksApi.plan(who, month).then((r) => setPlan(r.data)).catch(fail); }, [who, month]);
  useEffect(() => { loadPlan(); }, [loadPlan]);
  useEffect(() => { tasksApi.rewards(month).then((r) => setRewards(r.data)).catch(fail); }, [month]);

  const units = plan?.units ?? [];
  const label = (p: string) => status.sites[p]?.short ?? p;

  return (
    <div className="space-y-6">
      <ErrorBanner message={error} />
      {notice && <p className="rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">{notice}</p>}

      <Card title="Targets">
        <div className="mb-4 flex flex-wrap gap-2">
          <select aria-label="Person" className="input-field w-auto" value={who} onChange={(e) => setWho(e.target.value)}>
            {people.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
          </select>
          <input aria-label="Month" type="month" className="input-field w-auto" value={month} onChange={(e) => setMonth(e.target.value)} />
          <button className="btn-secondary" onClick={() => tasksApi.applyTemplate({ user_id: who, project_id: nt.project_id, month })
            .then((r) => { setPlan(r.data); ok('Role template applied.'); }).catch(fail)}>
            Apply role template for {label(nt.project_id)}
          </button>
        </div>
        <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-4">
          <select aria-label="Website" className="input-field" value={nt.project_id} onChange={(e) => setNt({ ...nt, project_id: e.target.value })}>
            {Object.values(status.sites).map((s) => <option key={s.id} value={s.id}>{s.short}</option>)}
          </select>
          <select aria-label="What counts" className="input-field" value={nt.unit} onChange={(e) => setNt({ ...nt, unit: e.target.value })}>
            {units.map((u) => <option key={u.unit} value={u.unit}>{u.label}</option>)}
          </select>
          <input aria-label="Monthly target" type="number" min={0} className="input-field" placeholder="per month (0 removes)" value={nt.qty} onChange={(e) => setNt({ ...nt, qty: e.target.value })} />
          <button className="btn-primary" disabled={nt.qty === ''} onClick={() => tasksApi.setTarget({ user_id: who, month, ...nt, qty: Number(nt.qty) })
            .then((r) => { setPlan(r.data); setNt({ ...nt, qty: '' }); ok('Target saved; weeks and days are split automatically.'); }).catch(fail)}>Set monthly target</button>
        </div>
        {plan && plan.targets.length === 0 && <p className="text-sm text-muted">No targets for this month yet.</p>}
        {plan?.targets.map((t) => (
          <div key={t.project + t.unit} className="mb-3 rounded-lg bg-raised p-3">
            <p className="text-sm text-slate-100"><b>{label(t.project)}</b> · {t.unitLabel} · <b>{t.qty}</b> this month</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {t.weeks.map((w) => (
                <label key={w.weekStart} className="text-xs text-muted">
                  week of {w.weekStart.slice(5)}{w.edited && ' ✎'}
                  <input type="number" min={0} className="input-field mt-0.5 w-24 py-1" defaultValue={w.qty}
                         onBlur={(e) => { const v = e.target.value; if (Number(v) !== w.qty) tasksApi.setSplit({ user_id: who, project_id: t.project, unit: t.unit, month, week_start: w.weekStart, qty: v === '' ? null : Number(v) }).then((r) => { setPlan(r.data); ok('Week updated.'); }).catch(fail); }} />
                </label>
              ))}
            </div>
          </div>
        ))}
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-xs text-muted">Leave / holiday
            <input type="date" className="input-field mt-0.5 w-auto py-1" value={leaveDay} onChange={(e) => setLeaveDay(e.target.value)} />
          </label>
          <label className="flex items-center gap-1 text-xs text-muted"><input type="checkbox" checked={holiday} onChange={(e) => setHoliday(e.target.checked)} /> whole team (holiday)</label>
          <button className="btn-secondary py-1" disabled={!leaveDay} onClick={() => tasksApi.leave(holiday ? '*' : who, leaveDay, false, holiday ? 'holiday' : 'leave').then(() => { loadPlan(); ok('Marked — that day’s target is 0.'); }).catch(fail)}>Mark</button>
        </div>
        {!!plan?.leave.length && (
          <p className="mt-2 flex flex-wrap gap-2 text-xs text-slate-300">Leave this month: {plan.leave.map((d) => (
            <button key={d} className="badge border-line text-slate-300" title="Remove" onClick={() => tasksApi.leave(who, d, true).then(loadPlan).catch(fail)}>{d} ✕</button>
          ))}</p>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Role templates (per week)">
          <table className="data-table">
            <thead><tr><th>Role</th><th>Counts</th><th>Per week</th></tr></thead>
            <tbody>
              {tpl.map((t, i) => (
                <tr key={i}>
                  <td><input className="input-field py-1" value={t.role} onChange={(e) => setTpl(tpl.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))} /></td>
                  <td><select className="input-field py-1" value={t.unit} onChange={(e) => setTpl(tpl.map((x, j) => (j === i ? { ...x, unit: e.target.value } : x)))}>
                    {units.map((u) => <option key={u.unit} value={u.unit}>{u.label}</option>)}
                    {!units.some((u) => u.unit === t.unit) && <option value={t.unit}>{t.unit}</option>}
                  </select></td>
                  <td><input type="number" min={0} className="input-field w-20 py-1" value={t.qty_per_week} onChange={(e) => setTpl(tpl.map((x, j) => (j === i ? { ...x, qty_per_week: Number(e.target.value) } : x)))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex gap-2">
            <button className="btn-primary" onClick={() => tasksApi.saveTemplates(tpl).then(() => ok('Templates saved.')).catch(fail)}>Save templates</button>
            <button className="btn-secondary" onClick={() => setTpl([...tpl, { role: 'seo_lead', unit: 'backlinks', qty_per_week: 1 }])}>Add line</button>
          </div>
        </Card>

        <Card title="Red / Amber / Green">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-muted">Green from (% of expected)<input type="number" className="input-field mt-1" value={rag.green_min} onChange={(e) => setRag({ ...rag, green_min: e.target.value })} /></label>
            <label className="text-xs text-muted">Amber from (% of expected)<input type="number" className="input-field mt-1" value={rag.amber_min} onChange={(e) => setRag({ ...rag, amber_min: e.target.value })} /></label>
          </div>
          <p className="mt-2 text-xs text-muted">Below amber = red. Overdue is always red; due within 24 h and not submitted is amber.</p>
          <button className="btn-primary mt-3" onClick={() => tasksApi.ragSettings(Number(rag.green_min), Number(rag.amber_min)).then(() => ok('Thresholds saved.')).catch(fail)}>Save thresholds</button>
        </Card>
      </div>

      <Card title={canEditTiers ? 'Reward tiers (only you can change these)' : 'Reward tiers'}>
        <table className="data-table">
          <thead><tr><th>Tier</th><th>From points / month</th><th>Bonus (note — paid offline)</th></tr></thead>
          <tbody>
            {tiers.map((t, i) => (
              <tr key={i}>
                <td><input disabled={!canEditTiers} className="input-field py-1" value={t.name} onChange={(e) => setTiers(tiers.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} /></td>
                <td><input disabled={!canEditTiers} type="number" className="input-field w-28 py-1" value={t.min_points} onChange={(e) => setTiers(tiers.map((x, j) => (j === i ? { ...x, min_points: Number(e.target.value) } : x)))} /></td>
                <td><input disabled={!canEditTiers} className="input-field py-1" value={t.bonus_note ?? ''} onChange={(e) => setTiers(tiers.map((x, j) => (j === i ? { ...x, bonus_note: e.target.value } : x)))} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {canEditTiers && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button className="btn-primary" onClick={() => tasksApi.saveTiers(tiers).then((r) => { setTiers(r.data.tiers); ok('Tiers saved.'); }).catch(fail)}>Save tiers</button>
            <button className="btn-secondary" onClick={() => setTiers([...tiers, { id: 0, name: '', min_points: 0, bonus_note: '' }])}>Add tier</button>
            <label className="flex items-center gap-1 text-sm text-slate-300"><input type="checkbox" defaultChecked={status.settings?.show_rank !== false} onChange={(e) => tasksApi.mirrorSettings(e.target.checked).then(() => ok('Saved.')).catch(fail)} /> Show each person their rank</label>
          </div>
        )}
        <p className="mt-2 text-xs text-muted">Each person sees only their own tier&rsquo;s bonus note. Associates never see other people&rsquo;s.</p>
      </Card>

      <Card title={`Monthly rewards · ${month}`} action={
        <div className="flex gap-2">
          <button className="btn-secondary py-1" onClick={() => tasksApi.rewardsCsv(month).then((r) => download(r.data, `rewards-${month}.csv`)).catch(fail)}>CSV for payout</button>
          {rewards?.canApprove && <button className="btn-primary py-1" onClick={() => tasksApi.approveRewards(month).then(() => tasksApi.rewards(month)).then((r) => { setRewards(r.data); ok('Month approved.'); }).catch(fail)}>Approve month</button>}
        </div>
      }>
        <div className="overflow-x-auto">
          <table className="data-table min-w-[520px]">
            <thead><tr><th>Person</th><th className="text-right">Points</th><th>Tier</th><th>Bonus</th><th>Approved</th></tr></thead>
            <tbody>
              {rewards?.rows.map((r) => (
                <tr key={r.userId}><td>{r.name}</td><td className="text-right tabular-nums">{r.points}</td><td>{r.tier || '—'}</td><td>{r.bonusNote || '—'}</td><td>{r.approved ? '✓' : ''}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
