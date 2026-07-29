'use client';

import { useEffect, useState } from 'react';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, Skeleton } from '@/components/ui';
import { apiError, seoApi } from '@/lib/seo';

interface Audit {
  id: string;
  audit_type: 'daily' | 'weekly' | 'monthly';
  audit_date: string;
  results_json: Record<string, unknown> | null;
  created_at: string;
}

/** Reads the shape each integration block returns from /health/integrations. */
function statusOf(value: unknown): 'ok' | 'warn' | 'off' {
  if (!value || typeof value !== 'object') return 'off';
  const v = value as Record<string, unknown>;
  if (v.configured === false) return 'off';
  if (v.error || v.reachable === false || v.authenticated === false) return 'warn';
  return 'ok';
}

const TONE: Record<string, string> = {
  ok: 'border-success/40 bg-success/10 text-success',
  warn: 'border-warning/40 bg-warning/10 text-warning',
  off: 'border-line bg-raised text-muted',
};

const LABEL: Record<string, string> = {
  ok: 'connected',
  warn: 'error',
  off: 'not configured',
};

export default function TechnicalAuditPage() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [audits, setAudits] = useState<Audit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    seoApi
      .integrationHealth()
      .then((response) => setHealth(response.data))
      .catch((err) =>
        setError(
          apiError(
            err,
            'Could not read integration health. This endpoint is admin-only.',
          ),
        ),
      );
    seoApi
      .audits({})
      .then((response) => setAudits(response.data))
      .catch(() => setAudits([]));
  }, []);

  const integrations = health
    ? Object.entries(health).filter(
        ([key]) => !['checked_at', 'go_live'].includes(key),
      )
    : [];
  const goLive = health?.go_live as Record<string, unknown> | undefined;

  return (
    <Shell
      title="Technical audit"
      subtitle="Integration health and the latest crawl/audit output."
    >
      <ErrorBanner message={error} />

      {goLive && (
        <div
          className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
            goLive.approved
              ? 'border-success/40 bg-success/10 text-success'
              : 'border-warning/40 bg-warning/10 text-warning'
          }`}
        >
          <strong className="font-semibold">
            {goLive.approved ? 'Live publishing is approved.' : 'Draft-only mode.'}
          </strong>{' '}
          {String(goLive.reason)}
          <span className="ml-1 opacity-80">
            Posts are sent to WordPress as “{String(goLive.wp_status_posts_will_use)}”.
          </span>
        </div>
      )}

      <Card title="Integrations" className="mb-4">
        {!health ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {integrations.map(([name, value]) => {
              const state = statusOf(value);
              const detail = value as Record<string, unknown>;
              return (
                <div key={name} className="rounded-lg border border-line bg-raised p-3">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-medium capitalize text-white">
                      {name.replace(/_/g, ' ')}
                    </h3>
                    <span className={`badge ${TONE[state]}`}>{LABEL[state]}</span>
                  </div>
                  {typeof detail?.note === 'string' && (
                    <p className="mt-1.5 text-xs text-muted">{detail.note}</p>
                  )}
                  {typeof detail?.error === 'string' && (
                    <p className="mt-1.5 break-words text-xs text-warning">{detail.error}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card title="Audit history">
        {!audits ? (
          <Skeleton className="h-32 w-full" />
        ) : audits.length === 0 ? (
          <EmptyState
            title="No audits recorded yet"
            description="The daily cron writes the first one at 06:00 IST; you can also POST to /api/seo/cron/daily-audit with the cron secret."
          />
        ) : (
          <ul className="space-y-3">
            {audits.map((audit) => (
              <li key={audit.id} className="rounded-lg border border-line bg-raised p-3">
                <div className="flex items-center gap-3">
                  <span className="badge border-primary/40 bg-primary/10 text-primary">
                    {audit.audit_type}
                  </span>
                  <span className="text-sm text-slate-200">{audit.audit_date}</span>
                </div>
                <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-surface p-2 font-mono text-xs text-slate-400">
                  {JSON.stringify(audit.results_json, null, 2)}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Shell>
  );
}
