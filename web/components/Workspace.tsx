'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card } from '@/components/ui';
import { LevelRow, trackerApi } from '@/lib/tracker';

/* Homepage "Workspace": the desks people actually work in, plus their level
   on each website (Backlink Ops, per person and per site). Backlink Ops and
   Invoices are pages served by the API through nginx, so they are plain
   <a> links, not Next routes. */

const DESKS = [
  { href: '/seo/backlink-ops/', label: 'Backlink Ops', blurb: 'Log links, keyword lab, your level per website.', external: true },
  { href: '/tasks/', label: 'Daily Tracker', blurb: 'Log today’s work with proof, marks, streaks and the Idea Board.', external: false },
  { href: '/invoices/', label: 'Invoices', blurb: 'Client fill links, review queue and PDF invoices.', external: true, admin: true },
];

function Bar({ value, max, done }: { value: number; max: number; done: boolean }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-raised">
      <div className={`h-full ${done ? 'bg-success' : 'bg-primary'}`} style={{ width: `${Math.min(100, (value / Math.max(1, max)) * 100)}%` }} />
    </div>
  );
}

export function MyLevels() {
  const [rows, setRows] = useState<LevelRow[] | null>(null);
  const [grid, setGrid] = useState<Awaited<ReturnType<typeof trackerApi.allLevels>>['data'] | null>(null);

  useEffect(() => {
    // 404 = per-site levels not switched on; 403 on /all = not the superuser. Both just hide.
    trackerApi.myLevels().then((r) => setRows(r.data.rows)).catch(() => setRows(null));
    trackerApi.allLevels().then((r) => setGrid(r.data)).catch(() => setGrid(null));
  }, []);

  if (!rows && !grid) return null;
  const sites = grid ? Object.keys(grid.projects) : [];
  const people = grid ? Array.from(new Map(grid.rows.map((r) => [r.userId, r.name])).entries()) : [];
  const cell = (u: string, p: string) => grid?.rows.find((r) => r.userId === u && r.project === p);

  return (
    <div className="mb-6 space-y-4">
      {rows && rows.length > 0 && (
        <Card title="My levels" action={<a href="/seo/backlink-ops/" className="text-xs text-primary hover:underline">Open Backlink Ops</a>}>
          <ul className="space-y-3">
            {rows.map((r) => (
              <li key={r.project} className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[180px_120px_1fr_90px]">
                <span className="text-sm text-slate-100">
                  <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: r.hue }} />
                  {r.domain || r.site}
                </span>
                <span className="text-sm text-slate-300">L{r.level} · {r.levelName}{r.ready && <span className="ml-1 text-success" title="Ready for the next level">↑</span>}</span>
                <div>
                  <Bar value={r.todayPoints} max={r.target} done={r.todayDone} />
                  <span className="text-xs text-muted">{r.todayPoints} / {r.target} points today</span>
                </div>
                <span className="text-sm text-slate-300 sm:text-right">🔥 {r.streak}d</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {grid && grid.rows.length > 0 && (
        <Card title="Levels · everyone × every website" action={<a href="/seo/backlink-ops/#settings" className="text-xs text-primary hover:underline">Change levels on the desk</a>}>
          <div className="overflow-x-auto">
            <table className="data-table min-w-[560px]">
              <thead>
                <tr><th>Person</th>{sites.map((p) => <th key={p}>{grid.projects[p].short}</th>)}</tr>
              </thead>
              <tbody>
                {people.map(([u, name]) => (
                  <tr key={u}>
                    <td className="text-slate-100">{name}</td>
                    {sites.map((p) => {
                      const c = cell(u, p);
                      return (
                        <td key={p} className="text-xs">
                          {c ? (
                            <>
                              <b className="text-slate-100">L{c.level}</b> · {c.todayPoints}/{c.target} · 🔥{c.streak}
                              {c.ready && <span className="ml-1 text-success">ready</span>}
                            </>
                          ) : <span className="text-slate-600">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {grid.unmatched.length > 0 && (
            <p className="mt-3 text-xs text-warning">
              On the roster but not matched to a login yet: {grid.unmatched.map((u) => `${u.name} (${u.project})`).join(', ')}.
              Put their dashboard login email on the roster row.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

export default function Workspace() {
  const [role, setRole] = useState<string | null>(null);
  useEffect(() => { setRole(localStorage.getItem('role')); }, []);
  const isAdmin = role === 'admin' || role === 'owner';

  return (
    <div className="mb-6">
      <h2 className="card-title mb-3">Workspace</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {DESKS.filter((d) => !d.admin || isAdmin).map((d) => {
          const inner = (
            <>
              <p className="font-semibold text-white">{d.label} →</p>
              <p className="mt-1 text-sm text-muted">{d.blurb}</p>
            </>
          );
          return d.external ? (
            <a key={d.href} href={d.href} className="card block transition-colors hover:border-primary">{inner}</a>
          ) : (
            <Link key={d.href} href={d.href} className="card block transition-colors hover:border-primary">{inner}</Link>
          );
        })}
      </div>
    </div>
  );
}
