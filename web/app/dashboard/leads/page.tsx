'use client';

/* WhatsApp leads desk.
 *
 * Reads the funnel's leads (wa.agenticaiautomation.co) and lets the team move
 * each one through the pipeline. The funnel owns the lead; this page owns only
 * its status, and every change is attributed and kept in a history the panel
 * shows — a status is a statement about a real person waiting for a reply.
 *
 * The fit score is shown here deliberately. It is hidden from the visitor and
 * always will be; internally it is the whole point of the funnel.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import Nav from '@/components/Nav';

type Status = 'new' | 'contacted' | 'on_hold' | 'converted' | 'rejected';

interface StatusEvent {
  created_at: string;
  from_status: string;
  to_status: string;
  note: string;
  actor: string;
}

interface Lead {
  id: number;
  created_at: string;
  name: string;
  whatsapp: string;
  email: string;
  language: string;
  need_type: string;
  industry: string;
  subtype: string;
  pain_points: string[];
  auto_services: string[];
  organic_channels: string[];
  inorganic_channels: string[];
  website_status: string;
  fit_score: number;
  qualified: boolean;
  consent_at: string | null;
  utm_source: string;
  utm_medium: string;
  utm_campaign: string;
  referrer: string;
  notified_at: string | null;
  status: Status;
  status_note: string;
  status_by: string;
  status_at: string | null;
  history?: StatusEvent[];
}

interface Stats {
  total: number;
  by_status: { status: string; count: number }[];
  open_leads: number;
  converted: number;
  rejected: number;
  conversion_rate: number | null;
  qualified_total: number;
  qualified_converted: number;
  last_7_days: number;
  average_fit_score: number | null;
}

interface Meta {
  statuses: Status[];
  open_statuses: Status[];
  industries: string[];
  can_write: boolean;
  db_ok: boolean;
}

/* Tone carries meaning here, so it is defined once rather than inline: a
   rejected lead should not look like a converted one at a glance. */
const STATUS_META: Record<Status, { label: string; tone: string }> = {
  new: { label: 'New', tone: 'text-primary border-primary/40 bg-primary/10' },
  contacted: { label: 'Contacted', tone: 'text-slate-200 border-line bg-raised' },
  on_hold: { label: 'On hold', tone: 'text-warning border-warning/40 bg-warning/10' },
  converted: { label: 'Converted', tone: 'text-success border-success/40 bg-success/10' },
  rejected: { label: 'Rejected', tone: 'text-danger border-danger/40 bg-danger/10' },
};

/* The funnel stores an industry id, not a label. The canonical labels live in
   wa-funnel's config/industries.json; these are the display names for the ids
   that ship today. An id with no entry falls back to its own text, so adding a
   sector to the funnel shows up here as a readable slug rather than a blank. */
const INDUSTRY_LABEL: Record<string, string> = {
  healthcare: 'Healthcare',
  insurance: 'Insurance',
  ecommerce: 'E-commerce',
  manufacturing: 'Manufacturing',
  logistics: 'Warehousing & logistics',
  bfsi: 'BFSI',
  telecom: 'Telecom & ISP',
  other: 'Retail & other services',
};

const industryLabel = (id: string) =>
  INDUSTRY_LABEL[id] ?? id.replace(/_/g, ' ');

const WEBSITE_LABEL: Record<string, string> = {
  works: 'Works well',
  needs_work: 'Needs work',
  none: 'None',
};

function StatusBadge({ status }: { status: Status }) {
  const meta = STATUS_META[status] ?? STATUS_META.new;
  return <span className={`badge ${meta.tone}`}>{meta.label}</span>;
}

function when(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: '2-digit' });
}

function fullWhen(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function LeadsPage() {
  const router = useRouter();

  const [leads, setLeads] = useState<Lead[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [status, setStatus] = useState('');
  const [industry, setIndustry] = useState('');
  const [qualified, setQualified] = useState('');
  const [days, setDays] = useState('');
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [sort, setSort] = useState('created_at');
  const [direction, setDirection] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);

  const [selected, setSelected] = useState<Lead | null>(null);
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  /* Typing in the search box should not fire a request per keystroke. */
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (status) p.set('status', status);
    if (industry) p.set('industry', industry);
    if (qualified) p.set('qualified', qualified);
    if (days) p.set('days', days);
    if (debounced.trim()) p.set('search', debounced.trim());
    p.set('sort', sort);
    p.set('direction', direction);
    p.set('page', String(page));
    return p.toString();
  }, [status, industry, qualified, days, debounced, sort, direction, page]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listRes, statsRes, metaRes] = await Promise.all([
        api.get(`/api/wa-leads?${query}`),
        api.get('/api/wa-leads/stats'),
        api.get('/api/wa-leads/meta'),
      ]);
      setLeads(listRes.data.leads);
      setTotal(listRes.data.total);
      setPages(listRes.data.pages);
      setStats(statsRes.data);
      setMeta(metaRes.data);
    } catch (e: any) {
      // 503 is the expected answer while the funnel is not deployed yet, and
      // it carries a sentence written for a person. Show that, not "error".
      setError(e?.response?.data?.detail ?? 'Could not load the leads desk.');
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    if (!localStorage.getItem('access_token')) {
      router.push('/login');
      return;
    }
    load();
  }, [router, load]);

  const openLead = async (id: number) => {
    setSaveError(null);
    try {
      const res = await api.get(`/api/wa-leads/${id}`);
      setSelected(res.data);
      setNote('');
    } catch {
      setSaveError('Could not open that lead.');
    }
  };

  const move = async (next: Status) => {
    if (!selected) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.patch(`/api/wa-leads/${selected.id}/status`, {
        status: next,
        note,
      });
      setSelected(res.data);
      setNote('');
      // The row in the table behind is now stale. Patch it in place rather
      // than refetching the page, so the list does not jump under the panel.
      setLeads((rows) =>
        rows.map((r) => (r.id === res.data.id ? { ...r, ...res.data } : r)),
      );
      api.get('/api/wa-leads/stats').then((s) => setStats(s.data)).catch(() => {});
    } catch (e: any) {
      setSaveError(e?.response?.data?.detail ?? 'Could not save that change.');
    } finally {
      setSaving(false);
    }
  };

  const sortBy = (column: string) => {
    if (sort === column) {
      setDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(column);
      setDirection('desc');
    }
    setPage(1);
  };

  const arrow = (column: string) =>
    sort === column ? (direction === 'asc' ? ' ↑' : ' ↓') : '';

  const clearFilters = () => {
    setStatus(''); setIndustry(''); setQualified(''); setDays(''); setSearch('');
    setPage(1);
  };

  const filtersOn = Boolean(status || industry || qualified || days || search);

  return (
    <div className="min-h-screen bg-bg">
      <Nav />
      <div className="mx-auto max-w-[1400px] px-4 py-8">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white">Leads</h1>
            <p className="mt-1 text-sm text-muted">
              Everyone who finished the questionnaire at wa.agenticaiautomation.co.
              {meta && !meta.can_write && ' You have read access — ask an owner to change a status.'}
            </p>
          </div>
          <button onClick={load} className="btn-secondary" disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </header>

        {error && (
          <div className="card mb-6 border-danger/40 bg-danger/10">
            <p className="text-sm text-danger">{error}</p>
          </div>
        )}

        {/* ---- the numbers someone actually asks about ---- */}
        {stats && (
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            {[
              { label: 'Total leads', value: stats.total, sub: `${stats.last_7_days} in 7 days` },
              { label: 'Open', value: stats.open_leads, sub: 'still to answer' },
              { label: 'Converted', value: stats.converted, sub: `${stats.rejected} rejected` },
              {
                label: 'Conversion',
                value: stats.conversion_rate === null ? '—' : `${stats.conversion_rate}%`,
                sub: 'of decided leads',
              },
              {
                label: 'Avg fit score',
                value: stats.average_fit_score ?? '—',
                sub: `${stats.qualified_total} above threshold`,
              },
            ].map((k) => (
              <div key={k.label} className="card">
                <h3 className="card-title">{k.label}</h3>
                <p className="mt-2 text-2xl font-semibold tabular-nums text-white">{k.value}</p>
                <p className="mt-1 text-xs text-muted">{k.sub}</p>
              </div>
            ))}
          </div>
        )}

        {/* ---- filters ---- */}
        <div className="card mb-4">
          <div className="grid gap-3 md:grid-cols-6">
            <div className="md:col-span-2">
              <label className="label" htmlFor="q">Search</label>
              <input
                id="q"
                className="input-field"
                placeholder="Name, email or number"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="f-status">Status</label>
              <select id="f-status" className="input-field" value={status}
                      onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
                <option value="">All</option>
                <option value="open">Open (undecided)</option>
                {(meta?.statuses ?? []).map((s) => (
                  <option key={s} value={s}>{STATUS_META[s]?.label ?? s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="f-industry">Industry</label>
              <select id="f-industry" className="input-field" value={industry}
                      onChange={(e) => { setIndustry(e.target.value); setPage(1); }}>
                <option value="">All</option>
                {(meta?.industries ?? []).map((i) => (
                  <option key={i} value={i}>{industryLabel(i)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="f-qualified">Fit</label>
              <select id="f-qualified" className="input-field" value={qualified}
                      onChange={(e) => { setQualified(e.target.value); setPage(1); }}>
                <option value="">All</option>
                <option value="true">Above threshold</option>
                <option value="false">Below threshold</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="f-days">Arrived</label>
              <select id="f-days" className="input-field" value={days}
                      onChange={(e) => { setDays(e.target.value); setPage(1); }}>
                <option value="">Any time</option>
                <option value="7">Last 7 days</option>
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
              </select>
            </div>
          </div>
          {filtersOn && (
            <button onClick={clearFilters} className="mt-3 text-xs text-muted hover:text-white">
              Clear filters
            </button>
          )}
        </div>

        {/* ---- the table ---- */}
        <div className="card overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  {[
                    ['created_at', 'Arrived'],
                    ['name', 'Name'],
                    ['industry', 'Business'],
                    ['fit_score', 'Fit'],
                    ['status', 'Status'],
                  ].map(([key, label]) => (
                    <th key={key}>
                      <button
                        onClick={() => sortBy(key)}
                        className="uppercase tracking-wide hover:text-white"
                      >
                        {label}{arrow(key)}
                      </button>
                    </th>
                  ))}
                  <th>Contact</th>
                  <th>Last moved</th>
                </tr>
              </thead>
              <tbody>
                {loading && leads.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-muted">Loading…</td>
                  </tr>
                )}
                {!loading && leads.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-muted">
                      {filtersOn
                        ? 'No leads match those filters.'
                        : 'No leads yet. They appear here the moment someone finishes the form.'}
                    </td>
                  </tr>
                )}
                {leads.map((lead) => (
                  <tr
                    key={lead.id}
                    onClick={() => openLead(lead.id)}
                    className="cursor-pointer"
                  >
                    <td className="whitespace-nowrap text-muted">{when(lead.created_at)}</td>
                    <td>
                      <span className="font-medium text-white">{lead.name}</span>
                      <span className="block text-xs text-muted">{lead.language}</span>
                    </td>
                    <td>
                      <span>{industryLabel(lead.industry)}</span>
                      <span className="block text-xs text-muted">{lead.subtype}</span>
                    </td>
                    <td className="tabular-nums">
                      <span className={lead.qualified ? 'text-success' : 'text-muted'}>
                        {lead.fit_score}
                      </span>
                      <span className="block text-xs text-muted">
                        {lead.qualified ? 'above' : 'below'}
                      </span>
                    </td>
                    <td><StatusBadge status={lead.status} /></td>
                    <td className="text-xs text-muted">
                      <span className="block">{lead.whatsapp}</span>
                      <span className="block">{lead.email}</span>
                    </td>
                    <td className="whitespace-nowrap text-xs text-muted">
                      {lead.status_at ? (
                        <>
                          {when(lead.status_at)}
                          <span className="block">{lead.status_by}</span>
                        </>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {pages > 1 && (
          <div className="mt-4 flex items-center justify-between text-sm text-muted">
            <span>{total} leads · page {page} of {pages}</span>
            <div className="flex gap-2">
              <button className="btn-secondary" disabled={page <= 1}
                      onClick={() => setPage((p) => p - 1)}>Previous</button>
              <button className="btn-secondary" disabled={page >= pages}
                      onClick={() => setPage((p) => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </div>

      {/* ---- detail panel ---- */}
      {selected && (
        <div className="fixed inset-0 z-40 flex justify-end">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setSelected(null)}
            aria-hidden="true"
          />
          <aside
            role="dialog"
            aria-label={`Lead: ${selected.name}`}
            className="relative z-10 flex h-full w-full max-w-xl flex-col overflow-y-auto
                       border-l border-line bg-surface"
          >
            <header className="sticky top-0 border-b border-line bg-surface px-6 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold text-white">{selected.name}</h2>
                  <p className="text-sm text-muted">
                    {selected.subtype} · {industryLabel(selected.industry)}
                  </p>
                </div>
                <button onClick={() => setSelected(null)}
                        className="text-muted hover:text-white" aria-label="Close">✕</button>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <StatusBadge status={selected.status} />
                <span className={`badge ${selected.qualified
                  ? 'border-success/40 bg-success/10 text-success'
                  : 'border-line bg-raised text-muted'}`}>
                  Fit {selected.fit_score}/100 · {selected.qualified ? 'above' : 'below'} threshold
                </span>
                {!selected.consent_at && (
                  <span className="badge border-danger/40 bg-danger/10 text-danger">
                    No consent — do not message
                  </span>
                )}
              </div>
            </header>

            <div className="flex-1 space-y-6 px-6 py-5">
              {/* Reaching them. The consent line is here rather than buried,
                  because it is the thing that decides whether we may. */}
              <section>
                <h3 className="card-title mb-2">Reaching them</h3>
                <dl className="space-y-1.5 text-sm">
                  <Row label="WhatsApp">
                    {selected.consent_at ? (
                      <a className="text-primary hover:underline"
                         href={`https://wa.me/${selected.whatsapp.replace(/[^0-9]/g, '')}`}
                         target="_blank" rel="noopener noreferrer">
                        {selected.whatsapp}
                      </a>
                    ) : (
                      <span className="text-danger">{selected.whatsapp} — no opt-in on record</span>
                    )}
                  </Row>
                  <Row label="Email">
                    <a className="text-primary hover:underline" href={`mailto:${selected.email}`}>
                      {selected.email}
                    </a>
                  </Row>
                  <Row label="Reply in">{selected.language}</Row>
                  <Row label="Consented">{fullWhen(selected.consent_at)}</Row>
                  <Row label="Arrived">{fullWhen(selected.created_at)}</Row>
                </dl>
              </section>

              <section>
                <h3 className="card-title mb-2">What they told us</h3>
                <dl className="space-y-1.5 text-sm">
                  <Row label="Here for"><span className="capitalize">{selected.need_type}</span></Row>
                  <Row label="Website">
                    {WEBSITE_LABEL[selected.website_status] ?? selected.website_status}
                  </Row>
                  <Row label="Pain points"><Chips items={selected.pain_points} /></Row>
                  <Row label="Automation"><Chips items={selected.auto_services} /></Row>
                  <Row label="Organic"><Chips items={selected.organic_channels} /></Row>
                  <Row label="Paid"><Chips items={selected.inorganic_channels} /></Row>
                </dl>
              </section>

              {(selected.utm_source || selected.utm_campaign || selected.referrer) && (
                <section>
                  <h3 className="card-title mb-2">Where they came from</h3>
                  <dl className="space-y-1.5 text-sm">
                    {selected.utm_source && <Row label="Source">{selected.utm_source}</Row>}
                    {selected.utm_medium && <Row label="Medium">{selected.utm_medium}</Row>}
                    {selected.utm_campaign && <Row label="Campaign">{selected.utm_campaign}</Row>}
                    {selected.referrer && (
                      <Row label="Referrer">
                        <span className="break-all text-xs">{selected.referrer}</span>
                      </Row>
                    )}
                  </dl>
                </section>
              )}

              {/* ---- move the lead ---- */}
              <section>
                <h3 className="card-title mb-2">Move this lead</h3>
                {meta?.can_write ? (
                  <>
                    <textarea
                      className="input-field mb-3"
                      rows={2}
                      placeholder="What happened? (optional, kept in the history)"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={1000}
                    />
                    <div className="flex flex-wrap gap-2">
                      {(meta.statuses ?? []).map((s) => (
                        <button
                          key={s}
                          onClick={() => move(s)}
                          disabled={saving || s === selected.status}
                          className={`badge px-3 py-1.5 transition-colors disabled:opacity-40
                                      disabled:cursor-not-allowed ${STATUS_META[s].tone}
                                      hover:brightness-125`}
                        >
                          {s === selected.status ? `● ${STATUS_META[s].label}` : STATUS_META[s].label}
                        </button>
                      ))}
                    </div>
                    {saveError && <p className="mt-2 text-sm text-danger">{saveError}</p>}
                  </>
                ) : (
                  <p className="text-sm text-muted">
                    Your account can read this desk but not change a status.
                  </p>
                )}
                {selected.status_note && (
                  <p className="mt-3 rounded-lg border border-line bg-raised p-3 text-sm text-slate-200">
                    {selected.status_note}
                  </p>
                )}
              </section>

              {/* ---- history ---- */}
              <section>
                <h3 className="card-title mb-2">History</h3>
                {selected.history && selected.history.length > 0 ? (
                  <ol className="space-y-3">
                    {[...selected.history].reverse().map((e, i) => (
                      <li key={i} className="border-l-2 border-line pl-3">
                        <p className="text-sm text-slate-200">
                          {STATUS_META[e.from_status as Status]?.label ?? e.from_status}
                          {' → '}
                          <span className="font-medium text-white">
                            {STATUS_META[e.to_status as Status]?.label ?? e.to_status}
                          </span>
                        </p>
                        <p className="text-xs text-muted">
                          {fullWhen(e.created_at)} · {e.actor || 'unknown'}
                        </p>
                        {e.note && <p className="mt-1 text-sm text-slate-300">{e.note}</p>}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-sm text-muted">
                    Nobody has moved this lead yet. It arrived and has been sitting at New.
                  </p>
                )}
              </section>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-28 shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 flex-1 text-slate-200">{children}</dd>
    </div>
  );
}

function Chips({ items }: { items: string[] }) {
  if (!items || items.length === 0) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((i) => (
        <span key={i} className="badge border-line bg-raised text-slate-300">
          {i.replace(/_/g, ' ')}
        </span>
      ))}
    </span>
  );
}
