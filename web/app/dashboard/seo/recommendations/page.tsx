'use client';

import { useCallback, useEffect, useState } from 'react';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, Skeleton } from '@/components/ui';
import { apiError, Recommendation, seoApi } from '@/lib/seo';

const PRIORITY_TONE: Record<string, string> = {
  high: 'border-danger/40 bg-danger/10 text-danger',
  medium: 'border-warning/40 bg-warning/10 text-warning',
  low: 'border-line bg-raised text-muted',
};

export default function RecommendationsPage() {
  const [items, setItems] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showResolved, setShowResolved] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setItems(null);
    try {
      const { data } = await seoApi.recommendations({
        resolved: String(showResolved),
      });
      setItems(data);
      setError(null);
    } catch (err) {
      setError(apiError(err, 'Could not load recommendations.'));
      setItems([]);
    }
  }, [showResolved]);

  useEffect(() => {
    load();
  }, [load]);

  const resolve = async (id: string) => {
    setBusy(id);
    try {
      await seoApi.resolveRecommendation(id);
      await load();
    } catch (err) {
      setError(apiError(err, 'Could not resolve that item.'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Shell
      title="Recommendations"
      subtitle="Written by the daily, weekly, and monthly audit crons, highest priority first."
      actions={
        <button className="btn-secondary" onClick={() => setShowResolved((v) => !v)}>
          {showResolved ? 'Show open' : 'Show resolved'}
        </button>
      }
    >
      <ErrorBanner message={error} />

      {!items ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            title={showResolved ? 'Nothing resolved yet' : 'No open recommendations'}
            description={
              showResolved
                ? 'Resolved items land here once you clear them.'
                : 'The audit crons run daily at 06:00 IST, weekly on Sunday, and monthly on the 1st.'
            }
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {items.map((rec) => (
            <li key={rec.id}>
              <Card>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`badge ${PRIORITY_TONE[rec.priority]}`}>
                        {rec.priority}
                      </span>
                      <span className="badge border-line bg-raised text-muted">
                        {rec.category}
                      </span>
                      <span className="text-xs text-muted">
                        {new Date(rec.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <h2 className="mt-2 text-base font-semibold text-white">{rec.title}</h2>
                    {rec.description && (
                      <p className="mt-1 text-sm text-slate-300">{rec.description}</p>
                    )}
                    {rec.action_required && (
                      <p className="mt-2 rounded-lg bg-raised px-3 py-2 text-sm text-slate-200">
                        <span className="font-medium text-white">Do this: </span>
                        {rec.action_required}
                      </p>
                    )}
                  </div>
                  {!rec.resolved_at && (
                    <button
                      className="btn-secondary shrink-0"
                      onClick={() => resolve(rec.id)}
                      disabled={busy === rec.id}
                    >
                      {busy === rec.id ? 'Resolving…' : 'Mark resolved'}
                    </button>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}
