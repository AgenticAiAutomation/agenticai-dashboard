'use client';

import { ReactNode } from 'react';

/* Small shared primitives. Kept in one file because the set is small and every
   page pulls from it. */

export function Card({
  title,
  action,
  children,
  className = '',
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between mb-4">
          {title && <h2 className="card-title">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export type Trend = 'up' | 'down' | 'flat';

export function TrendPill({
  direction,
  value,
  label,
  invert = false,
}: {
  direction: Trend;
  value: number | null | undefined;
  label?: string;
  invert?: boolean;
}) {
  if (value === null || value === undefined) return null;
  // `invert` is for metrics where down is good (e.g. average SERP position).
  const good = invert ? direction === 'down' : direction === 'up';
  const tone =
    direction === 'flat'
      ? 'text-muted border-line bg-raised'
      : good
      ? 'text-success border-success/40 bg-success/10'
      : 'text-danger border-danger/40 bg-danger/10';
  const arrow = direction === 'up' ? '↑' : direction === 'down' ? '↓' : '→';
  const sign = value > 0 ? '+' : '';

  return (
    <span className={`badge ${tone}`}>
      {arrow} {sign}
      {Number.isInteger(value) ? value : value.toFixed(1)}
      {label ? <span className="ml-1 opacity-70">{label}</span> : null}
    </span>
  );
}

export function KpiCard({
  label,
  value,
  unit,
  delta,
  deltaLabel,
  direction = 'flat',
  target,
  percentOfTarget,
  healthy,
  invertTrend = false,
}: {
  label: string;
  value: number;
  unit?: string | null;
  delta?: number | null;
  deltaLabel?: string | null;
  direction?: Trend;
  target?: number | null;
  percentOfTarget?: number | null;
  healthy?: boolean | null;
  invertTrend?: boolean;
}) {
  return (
    <div className="card flex flex-col justify-between min-h-[168px]">
      <div className="flex items-start justify-between gap-3">
        <h3 className="card-title">{label}</h3>
        {healthy !== null && healthy !== undefined && (
          <span
            aria-label={healthy ? 'On target' : 'Below target'}
            className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${
              healthy ? 'bg-success' : 'bg-danger'
            }`}
          />
        )}
      </div>

      <p className="kpi-value mt-3">
        {Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1)}
        {unit && <span className="text-xl text-muted ml-1">{unit}</span>}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <TrendPill
          direction={direction}
          value={delta}
          label={deltaLabel ?? undefined}
          invert={invertTrend}
        />
        {target !== null && target !== undefined && (
          <span className="text-xs text-muted">
            target {target}
            {percentOfTarget !== null && percentOfTarget !== undefined
              ? ` · ${percentOfTarget.toFixed(0)}%`
              : ''}
          </span>
        )}
      </div>
    </div>
  );
}

const PROJECTION_TONE: Record<string, string> = {
  on_track: 'text-success border-success/40 bg-success/10',
  achieved: 'text-success border-success/40 bg-success/10',
  slipping: 'text-warning border-warning/40 bg-warning/10',
  at_risk: 'text-danger border-danger/40 bg-danger/10',
  on_hold: 'text-muted border-line bg-raised',
};

export function ProjectionCard({
  label,
  currentValue,
  targetValue,
  projectedDate,
  confidenceDays,
  status,
  message,
}: {
  label: string;
  currentValue: number;
  targetValue: number;
  projectedDate?: string | null;
  confidenceDays?: number | null;
  status: string;
  message: string;
}) {
  const pct = targetValue > 0 ? Math.min((currentValue / targetValue) * 100, 100) : 0;
  const tone = PROJECTION_TONE[status] ?? PROJECTION_TONE.on_hold;
  const barColor =
    status === 'at_risk'
      ? 'bg-danger'
      : status === 'slipping'
      ? 'bg-warning'
      : status === 'on_hold'
      ? 'bg-slate-600'
      : 'bg-success';

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3">
        <h3 className="card-title">{label}</h3>
        <span className={`badge ${tone}`}>{status.replace(/_/g, ' ')}</span>
      </div>

      <p className="mt-3 text-3xl font-semibold tabular-nums text-white">
        {currentValue % 1 === 0 ? currentValue : currentValue.toFixed(1)}
        <span className="text-lg text-muted"> / {targetValue}</span>
      </p>

      <div className="mt-3 h-1.5 w-full rounded-full bg-raised">
        <div className={`h-1.5 rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>

      <p className="mt-3 text-sm text-slate-300">
        {projectedDate ? (
          <>
            Projected <span className="font-medium text-white">{projectedDate}</span>
            {confidenceDays !== null && confidenceDays !== undefined
              ? ` (±${confidenceDays} days)`
              : ''}
          </>
        ) : (
          message
        )}
      </p>
      {projectedDate && <p className="mt-1 text-xs text-muted">{message}</p>}
    </div>
  );
}

export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card space-y-3">
      <Skeleton className="h-3 w-28" />
      <Skeleton className="h-10 w-24" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-3 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-200">{title}</p>
      <p className="mt-1 max-w-md text-sm text-muted">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
    >
      {message}
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  drafted_by_author: 'text-slate-300 border-line bg-raised',
  in_team_review: 'text-primary border-primary/40 bg-primary/10',
  submitted_for_scoring: 'text-primary border-primary/40 bg-primary/10',
  author_review: 'text-warning border-warning/40 bg-warning/10',
  ready_to_publish: 'text-success border-success/40 bg-success/10',
  published: 'text-success border-success/40 bg-success/20',
  archived: 'text-muted border-line bg-raised',
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${STATUS_TONE[status] ?? STATUS_TONE.archived}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) {
    return <span className="text-muted">—</span>;
  }
  const tone =
    score >= 80
      ? 'text-success border-success/40 bg-success/10'
      : score >= 70
      ? 'text-warning border-warning/40 bg-warning/10'
      : 'text-danger border-danger/40 bg-danger/10';
  return <span className={`badge ${tone} tabular-nums`}>{score}</span>;
}
