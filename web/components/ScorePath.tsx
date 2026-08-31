'use client';

import { useState } from 'react';
import { Card } from '@/components/ui';
import type { PassingCheck, PathToThreshold, RankMathTest } from '@/lib/seo';

/**
 * "Path to 80" and the passing list.
 *
 * A writer on 67 already sees every individual failure. What they cannot see
 * is which of them actually gets the article published, so the list reads as
 * an endless wall rather than a finish line. This panel answers two questions
 * instead: how far away am I, and which fixes close it.
 *
 * Steps are ordered by score impact and cut off at the point the gap closes —
 * everything past that is real but optional, and presenting it as mandatory is
 * what makes writers give up at 78.
 */

export function ScorePath({ path }: { path: PathToThreshold }) {
  const [showAll, setShowAll] = useState(false);

  if (path.gap <= 0) {
    return (
      <Card title="Ready to publish">
        <p className="text-sm text-success">
          {path.current}/100 — at or above the {path.threshold}-point threshold.
        </p>
        <p className="mt-2 text-xs text-muted">
          The remaining blockers, if any, are listed above. Score alone does not
          publish an article.
        </p>
      </Card>
    );
  }

  const enough = path.closes_gap_after ?? path.steps.length;
  const shown = showAll ? path.steps : path.steps.slice(0, enough);
  const hidden = path.steps.length - shown.length;

  return (
    <Card title={`Path to ${path.threshold}`}>
      <div className="mb-4">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-slate-200">
            <span className="text-2xl font-semibold tabular-nums text-warning">
              {path.current}
            </span>
            <span className="text-muted"> / {path.threshold}</span>
          </span>
          <span className="text-xs text-muted">
            need <span className="font-semibold text-warning">+{path.gap}</span>
          </span>
        </div>

        {/* Progress toward the threshold, not toward 100 — the threshold is
            the only number that decides whether this can ship. */}
        <div className="mt-2 h-2 overflow-hidden rounded bg-raised">
          <div
            className="h-full bg-warning transition-all"
            style={{ width: `${Math.min((path.current / path.threshold) * 100, 100)}%` }}
          />
        </div>
      </div>

      {path.closes_gap_after !== null && (
        <p className="mb-3 text-xs text-muted">
          These <strong className="text-slate-200">{enough}</strong> fix
          {enough === 1 ? '' : 'es'} are enough to publish. The rest are optional.
        </p>
      )}

      <ol className="space-y-2">
        {shown.map((step, index) => (
          <li
            key={step.key}
            className={`rounded border p-2 ${
              index < enough
                ? 'border-warning/40 bg-warning/5'
                : 'border-line bg-raised'
            }`}
          >
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-xs tabular-nums text-success">
                +{step.score_gain}
              </span>
              <span className="text-xs font-medium text-slate-100">{step.label}</span>
            </div>
            {step.detail && (
              <p className="mt-1 text-xs text-muted">{step.detail}</p>
            )}
            {step.how && (
              <p className="mt-1 text-xs text-slate-300">{step.how}</p>
            )}
          </li>
        ))}
      </ol>

      {hidden > 0 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-3 text-xs text-primary hover:underline"
        >
          Show {hidden} optional improvement{hidden === 1 ? '' : 's'} (+
          {Math.round((path.headroom - shown.reduce((t, s) => t + s.score_gain, 0)) * 10) / 10}{' '}
          more)
        </button>
      )}
      {showAll && hidden === 0 && path.steps.length > enough && (
        <button
          onClick={() => setShowAll(false)}
          className="mt-3 text-xs text-primary hover:underline"
        >
          Show only what is needed
        </button>
      )}
    </Card>
  );
}

function PassRow({ label, detail }: { label: string; detail?: string }) {
  return (
    <li className="flex gap-2 text-xs">
      <span aria-hidden="true" className="text-success">
        ✓
      </span>
      <span className="flex-1">
        <span className="text-slate-200">{label}</span>
        {detail && <span className="block text-muted">{detail}</span>}
      </span>
      <span className="sr-only">passing</span>
    </li>
  );
}

/**
 * What the article already gets right, across both rulebooks.
 *
 * The two engines are kept in separate sections rather than merged: they
 * measure different things and are meant to disagree, so folding them into one
 * list would imply an agreement that isn't there.
 *
 * Collapsed by default — this is reassurance, not a task list, and it should
 * never compete with the fixes above it for attention.
 */
export function ScorePassing({
  passing = [],
  rankMathTests = [],
}: {
  passing?: PassingCheck[];
  rankMathTests?: RankMathTest[];
}) {
  const [open, setOpen] = useState(false);

  /* Informational tests carry no points, so "passing" them means nothing. */
  const rmPassed = rankMathTests.filter((t) => t.passed && !t.informational);
  const total = passing.length + rmPassed.length;

  if (!total) return null;

  return (
    <Card title={`On track · ${total} passing`}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="text-xs text-primary hover:underline"
      >
        {open ? 'Hide' : 'Show'} what this article already gets right
      </button>

      {open && (
        <div className="mt-3 space-y-4">
          {passing.length > 0 && (
            <div>
              <p className="card-title mb-2">House checks · {passing.length}</p>
              <ul className="space-y-1.5">
                {passing.map((check) => (
                  <PassRow key={check.key} label={check.label} detail={check.detail} />
                ))}
              </ul>
            </div>
          )}

          {rmPassed.length > 0 && (
            <div>
              <p className="card-title mb-2">Rank Math · {rmPassed.length}</p>
              <ul className="space-y-1.5">
                {rmPassed.map((test) => (
                  <PassRow key={test.key} label={test.label} detail={test.message} />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
