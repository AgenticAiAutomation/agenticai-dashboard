'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorBanner } from '@/components/ui';
import { ReportRow, TrackerStatus, WorkType, msg, trackerApi } from '@/lib/tracker';

export default function ReportPanel({ status, types, onTypes }: {
  status: TrackerStatus;
  types: WorkType[];
  onTypes: (t: WorkType[]) => void;
}) {
  const monthStart = status.today.slice(0, 8) + '01';
  const [start, setStart] = useState(monthStart);
  const [end, setEnd] = useState(status.today);
  const [rows, setRows] = useState<ReportRow[]>([]);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [cfg, setCfg] = useState({
    default_daily_target: String(status.settings?.default_daily_target ?? 40),
    backlink_daily_cap: String(status.settings?.backlink_daily_cap ?? 20),
  });
  const [draft, setDraft] = useState<WorkType[]>(types);
  const [csv, setCsv] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows((await trackerApi.report(start, end)).data.people);
    } catch (e) { setError(msg(e)); }
  }, [start, end]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setDraft(types); }, [types]);

  const done = (text: string) => { setNotice(text); setError(null); };

  const download = async () => {
    try {
      const r = await trackerApi.exportCsv(start, end);
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `daily-tracker-${start}-to-${end}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(msg(e)); }
  };

  const saveTarget = async (userId: string) => {
    try { await trackerApi.setTarget(userId, Number(targets[userId])); done('Target saved — it applies from today.'); load(); }
    catch (e) { setError(msg(e)); }
  };
  const saveCfg = async () => {
    try {
      await trackerApi.saveSettings({ default_daily_target: Number(cfg.default_daily_target),
                                      backlink_daily_cap: Number(cfg.backlink_daily_cap) });
      done('Settings saved.');
    } catch (e) { setError(msg(e)); }
  };
  const saveTypes = async () => {
    try { onTypes((await trackerApi.saveWorkTypes(draft)).data.types); done('Work types saved.'); }
    catch (e) { setError(msg(e)); }
  };
  const runImport = async () => {
    try {
      const r = (await trackerApi.importCsv(csv)).data;
      done(`Imported ${r.added} row(s).` + (r.skipped.length ? ` Skipped: ${r.skipped.map((s) => `row ${s.row} (${s.why})`).join('; ')}` : ''));
      setCsv('');
    } catch (e) { setError(msg(e)); }
  };

  const siteName = (p: string) => status.sites[p]?.short || p;

  return (
    <div className="space-y-6">
      <ErrorBanner message={error} />
      {notice && <p className="rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">{notice}</p>}

      <Card
        title="Team report"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <input type="date" aria-label="From" className="input-field w-auto py-1" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
            <input type="date" aria-label="To" className="input-field w-auto py-1" value={end} max={status.today} onChange={(e) => setEnd(e.target.value)} />
            <button className="btn-secondary py-1" onClick={download}>Export CSV</button>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="data-table min-w-[760px]">
            <thead><tr><th>Person</th><th className="text-right">Marks</th><th>Days on target</th><th>By website</th><th>Daily target</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.userId}>
                  <td>
                    <div className="text-slate-100">{r.name} {r.badges.length > 0 && <span title="Idea winner">🏆{r.badges.length > 1 ? `×${r.badges.length}` : ''}</span>}</div>
                    <div className="text-xs text-muted">{r.email}</div>
                  </td>
                  <td className="text-right tabular-nums">{r.marks}</td>
                  <td>{r.daysHit}/{r.days} <span className="text-xs text-muted">({r.pctHit}%)</span></td>
                  <td className="text-xs">
                    {Object.entries(r.projects).map(([p, x]) => (
                      <div key={p}>{siteName(p)}: {x.marks} marks · {x.items} items{x.pending ? ` · ${x.pending} pending` : ''}</div>
                    ))}
                  </td>
                  <td className="whitespace-nowrap">
                    <input type="number" min={1} className="input-field w-20 py-1" placeholder={String(r.target)}
                           value={targets[r.userId] ?? ''} onChange={(e) => setTargets({ ...targets, [r.userId]: e.target.value })} />
                    <button className="ml-2 text-xs text-primary hover:underline" disabled={!targets[r.userId]} onClick={() => saveTarget(r.userId)}>Set</button>
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={5} className="text-muted">Nobody has opened the tracker yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Rules">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="dt-def">Default daily target (marks)</label>
              <input id="dt-def" type="number" min={1} className="input-field" value={cfg.default_daily_target}
                     onChange={(e) => setCfg({ ...cfg, default_daily_target: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="dt-cap">Backlink Ops marks per day (cap)</label>
              <input id="dt-cap" type="number" min={0} className="input-field" value={cfg.backlink_daily_cap}
                     onChange={(e) => setCfg({ ...cfg, backlink_daily_cap: e.target.value })} />
            </div>
          </div>
          <p className="mt-3 text-xs text-muted">
            Each approved Backlink Ops link earns the “Backlink built” marks here, up to the cap per person per day. 0 = show the links but count nothing.
            Late logs earn 50%. Quality 1–5 multiplies by 0, 0.5, 1, 1.25, 1.5.
          </p>
          <button className="btn-primary mt-4" onClick={saveCfg}>Save rules</button>
        </Card>

        <Card title="Import from the backup sheet">
          <p className="mb-2 text-xs text-muted">
            Paste CSV with columns: Email, Project, Work type, Link, Note, Minutes, Date. Rows arrive as “pending review”.
          </p>
          <textarea rows={5} className="input-field font-mono text-xs" value={csv} onChange={(e) => setCsv(e.target.value)}
                    placeholder={'Email,Project,Work type,Link,Note,Minutes,Date\nakash0710yadav@gmail.com,whatsappautomation.co.in,Guest post,https://…,,60,2026-10-13'} />
          <button className="btn-secondary mt-3" disabled={!csv.trim()} onClick={runImport}>Import</button>
        </Card>
      </div>

      <Card title="Work types and marks">
        <div className="overflow-x-auto">
          <table className="data-table min-w-[560px]">
            <thead><tr><th>Name</th><th>Base marks</th><th>Order</th><th>Active</th></tr></thead>
            <tbody>
              {draft.map((t, i) => (
                <tr key={t.id || `new-${i}`}>
                  <td><input className="input-field py-1" value={t.name} onChange={(e) => setDraft(draft.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} /></td>
                  <td><input type="number" min={0} className="input-field w-24 py-1" value={t.base_marks}
                             onChange={(e) => setDraft(draft.map((x, j) => (j === i ? { ...x, base_marks: Number(e.target.value) } : x)))} /></td>
                  <td><input type="number" className="input-field w-20 py-1" value={t.sort_order}
                             onChange={(e) => setDraft(draft.map((x, j) => (j === i ? { ...x, sort_order: Number(e.target.value) } : x)))} /></td>
                  <td><input type="checkbox" aria-label="Active" checked={!!t.active}
                             onChange={(e) => setDraft(draft.map((x, j) => (j === i ? { ...x, active: e.target.checked ? 1 : 0 } : x)))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-primary" onClick={saveTypes}>Save work types</button>
          <button className="btn-secondary" onClick={() => setDraft([...draft, { id: 0, name: '', base_marks: 3, active: 1, sort_order: 999, kind: '' }])}>
            Add a work type
          </button>
        </div>
        <p className="mt-3 text-xs text-muted">Changing marks affects new logs only — logged work keeps the marks it was submitted with.</p>
      </Card>
    </div>
  );
}
