'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card } from '@/components/ui';
import { Flags, PUBLIC_ORIGIN, RouteEntry, homeGroups, pinnedRoutes } from '@/lib/registry';
import api from '@/lib/api';
import { LevelRow, trackerApi } from '@/lib/tracker';
import { RAG_DOT, RAG_LABEL, Rag, Signal, tasksApi } from '@/lib/tasks';
import { SignalTile } from '@/components/tasks/MirrorPanel';

/* Homepage "Workspace": every dashboard page this person may open, grouped,
   straight from the route registry (web/lib/routes.json) — no list here.
   Plus their level on each website (Backlink Ops, per person and per site).
   `server` pages (Backlink Ops, Invoices) are served by the API through
   nginx, so they are plain <a> links, not Next routes. */

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

function RouteCard({ r }: { r: RouteEntry }) {
  const [copied, setCopied] = useState(false);
  const url = PUBLIC_ORIGIN + r.slug;
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* clipboard blocked: the URL is selectable text anyway */ }
  };
  const title = <span className="font-semibold text-white group-hover:text-primary">{r.title} →</span>;
  return (
    <div className="card group flex flex-col gap-1.5 p-4 transition-colors hover:border-primary">
      {r.server ? <a href={r.slug}>{title}</a> : <Link href={r.slug}>{title}</Link>}
      <p className="text-sm text-muted">{r.purpose}</p>
      <div className="mt-auto flex items-center gap-2 pt-1">
        <code className="min-w-0 flex-1 select-all truncate text-xs text-slate-400" title={url}>{url}</code>
        <button type="button" onClick={copy} className="shrink-0 text-xs text-primary hover:underline" aria-label={`Copy ${url}`}>
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

/* T7: your own Today / Week / Month signal at the top of the homepage; admins
   also get the team grid. Hidden when the task manager is off (404). */
export function RagSignals() {
  const [mine, setMine] = useState<Record<'day' | 'week' | 'month', Signal> | null>(null);
  const [team, setTeam] = useState<{ userId: string; name: string; day: Rag; week: Rag; month: Rag }[] | null>(null);
  useEffect(() => {
    tasksApi.rag().then((r) => setMine(r.data.signals)).catch(() => setMine(null));
    tasksApi.teamRag().then((r) => setTeam(r.data.rows)).catch(() => setTeam(null));
  }, []);
  if (!mine && !team) return null;
  const hasOwn = mine && Object.values(mine).some((s) => s.signal !== 'none');
  return (
    <div className="mb-6 space-y-4">
      {mine && hasOwn && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(['day', 'week', 'month'] as const).map((p) => <SignalTile key={p} s={mine[p]} />)}
        </div>
      )}
      {team && team.length > 0 && (
        <Card title="Team signals" action={<Link href="/tasks/?tab=plan" className="text-xs text-primary hover:underline">Targets</Link>}>
          <div className="overflow-x-auto">
            <table className="data-table min-w-[420px]">
              <thead><tr><th>Person</th><th>Today</th><th>This week</th><th>This month</th></tr></thead>
              <tbody>
                {team.map((r) => (
                  <tr key={r.userId}>
                    <td className="text-slate-100">{r.name}</td>
                    {(['day', 'week', 'month'] as const).map((p) => (
                      <td key={p}><span className="flex items-center gap-1.5"><span className={`inline-block h-3 w-3 rounded-full ${RAG_DOT[r[p]]}`} />{RAG_LABEL[r[p]]}</span></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

/** Role + feature flags for the registry (flagged pages hide until switched on). */
function useRegistryContext() {
  const [role, setRole] = useState<string | null>(null);
  const [flags, setFlags] = useState<Flags>(null);
  useEffect(() => {
    setRole(localStorage.getItem('role'));
    const fu = api.get<{ allowed: boolean }>('/api/followups/status').then((r) => !!r.data.allowed).catch(() => false);
    trackerApi.status()
      .then(async (r) => { const f = await fu; setFlags({ tracker: r.data.tracker, ideas: r.data.ideas, taskManager: !!r.data.taskManager, followups: f, leads: f }); })
      .catch(async () => { const f = await fu; setFlags({ followups: f, leads: f }); });
  }, []);
  return { role, flags };
}

/* The first thing on the homepage: one click to each desk people use daily
   (registry entries with `pin`). */
export function DeskRow() {
  const { role, flags } = useRegistryContext();
  const pinned = pinnedRoutes(role, flags);
  if (!pinned.length) return null;
  return (
    <div className="mb-6">
        <nav aria-label="Your desks" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {pinned.map((r) => {
            const cls = 'card flex items-center justify-between gap-2 p-4 text-base font-semibold text-white transition-colors hover:border-primary hover:text-primary';
            return r.server
              ? <a key={r.slug} href={r.slug} className={cls}>{r.title}<span aria-hidden>→</span></a>
              : <Link key={r.slug} href={r.slug} className={cls}>{r.title}<span aria-hidden>→</span></Link>;
          })}
        </nav>
    </div>
  );
}

export default function Workspace() {
  // Flagged pages (Idea Board, Mirror, Follow-ups…) show only when switched on.
  const { role, flags } = useRegistryContext();

  return (
    <div className="mb-6 space-y-5">
      <h2 className="card-title">Workspace · every page</h2>
      {homeGroups(role, flags).map(({ group, routes }) => (
        <section key={group} aria-label={group}>
          <h3 className="mb-2 text-sm font-semibold text-slate-300">{group}</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {routes.map((r) => <RouteCard key={r.slug} r={r} />)}
          </div>
        </section>
      ))}
    </div>
  );
}
