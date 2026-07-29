'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import Shell from '@/components/Shell';
import { Card, ErrorBanner, Skeleton } from '@/components/ui';
import { apiError, COUNTRY_LABELS, seoApi, VERTICAL_LABELS } from '@/lib/seo';

interface MatrixVertical {
  vertical: string;
  label: string;
  approved_countries: { country: string; label: string }[];
  blocked_countries?: { country: string; label: string }[];
}

const SECTIONS = [
  {
    href: '/dashboard/seo/inbox',
    title: 'Inbox',
    body: 'Reddit, Quora, and People Also Ask questions waiting to be turned into articles.',
  },
  {
    href: '/dashboard/seo/articles',
    title: 'Articles',
    body: 'Every draft and published article, filterable by status, vertical, and country.',
  },
  {
    href: '/dashboard/seo/calendar',
    title: 'Calendar',
    body: 'The 12-week editorial plan as a Kanban board, imported from CSV.',
  },
  {
    href: '/dashboard/seo/team',
    title: 'Team',
    body: 'Per-member throughput, average score, and activity streak.',
  },
  {
    href: '/dashboard/seo/backlinks',
    title: 'Backlinks',
    body: 'Manual entries, Ubersuggest pastes, and HARO placements.',
  },
  {
    href: '/dashboard/seo/recommendations',
    title: 'Recommendations',
    body: 'Prioritised output from the daily, weekly, and monthly audits.',
  },
  {
    href: '/dashboard/seo/technical-audit',
    title: 'Technical audit',
    body: 'Latest audit results and integration health.',
  },
];

export default function SeoHubPage() {
  const [matrix, setMatrix] = useState<MatrixVertical[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    seoApi
      .matrix()
      .then((response) => setMatrix(response.data.verticals))
      .catch((err) => setError(apiError(err, 'Could not load the country matrix.')));
  }, []);

  return (
    <Shell
      title="SEO Operations"
      subtitle="Product C — capture questions, draft, score, and publish to the blog."
      actions={
        <Link href="/dashboard/seo/articles/new" className="btn-primary">
          New article
        </Link>
      }
    >
      <ErrorBanner message={error} />

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {SECTIONS.map((section) => (
          <Link
            key={section.href}
            href={section.href}
            className="card transition-colors hover:border-primary"
          >
            <h2 className="text-sm font-semibold text-white">{section.title}</h2>
            <p className="mt-1.5 text-sm text-muted">{section.body}</p>
          </Link>
        ))}
      </div>

      <Card title="Approved country × vertical matrix">
        <p className="mb-4 text-sm text-muted">
          Onpage articles are locked to these combinations. The API rejects anything else
          with a 422, so this is enforcement, not guidance.
        </p>
        {!matrix ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vertical</th>
                  {Object.entries(COUNTRY_LABELS).map(([key, label]) => (
                    <th key={key}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.map((row) => {
                  const approved = new Set(row.approved_countries.map((c) => c.country));
                  return (
                    <tr key={row.vertical}>
                      <td className="font-medium text-white">
                        {VERTICAL_LABELS[row.vertical as keyof typeof VERTICAL_LABELS] ??
                          row.label}
                      </td>
                      {Object.keys(COUNTRY_LABELS).map((country) => (
                        <td key={country}>
                          {approved.has(country) ? (
                            <span className="badge border-success/40 bg-success/10 text-success">
                              approved
                            </span>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </Shell>
  );
}
