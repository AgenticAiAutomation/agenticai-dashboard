'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, ScoreBadge, Skeleton, StatusBadge } from '@/components/ui';
import {
  apiError,
  Article,
  ArticleStatus,
  COUNTRY_LABELS,
  seoApi,
  VERTICAL_LABELS,
} from '@/lib/seo';

const STATUSES: ArticleStatus[] = [
  'drafted_by_author',
  'in_team_review',
  'submitted_for_scoring',
  'author_review',
  'ready_to_publish',
  'published',
  'archived',
];

export default function ArticlesPage() {
  const [articles, setArticles] = useState<Article[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    status: '',
    type: '',
    vertical: '',
    country: '',
  });

  const load = useCallback(async () => {
    setArticles(null);
    try {
      const response = await seoApi.listArticles({
        status: filters.status || undefined,
        type: filters.type || undefined,
        vertical: filters.vertical || undefined,
        country: filters.country || undefined,
      });
      setArticles(response.data);
      setError(null);
    } catch (err) {
      setError(apiError(err, 'Could not load articles.'));
      setArticles([]);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  const set = (key: keyof typeof filters) => (e: React.ChangeEvent<HTMLSelectElement>) =>
    setFilters((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <Shell
      title="Articles"
      subtitle="Every draft and published article in the SEO pipeline."
      actions={
        <Link href="/dashboard/seo/articles/new" className="btn-primary">
          New article
        </Link>
      }
    >
      <ErrorBanner message={error} />

      <Card className="mb-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div>
            <label className="label">Status</label>
            <select className="input-field" value={filters.status} onChange={set('status')}>
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Type</label>
            <select className="input-field" value={filters.type} onChange={set('type')}>
              <option value="">All</option>
              <option value="onpage">Onpage</option>
              <option value="content">Content</option>
            </select>
          </div>
          <div>
            <label className="label">Vertical</label>
            <select className="input-field" value={filters.vertical} onChange={set('vertical')}>
              <option value="">All</option>
              {Object.entries(VERTICAL_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Country</label>
            <select className="input-field" value={filters.country} onChange={set('country')}>
              <option value="">All</option>
              {Object.entries(COUNTRY_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      <Card>
        {!articles ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : articles.length === 0 ? (
          <EmptyState
            title="No articles match these filters"
            description="Convert a question from the inbox, or generate a draft from a keyword."
            action={
              <Link href="/dashboard/seo/articles/new" className="btn-primary">
                Create the first article
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Vertical</th>
                  <th>Country</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {articles.map((article) => (
                  <tr key={article.id}>
                    <td className="max-w-sm">
                      <div className="truncate font-medium text-white">
                        {article.title ?? '(untitled)'}
                      </div>
                      <div className="truncate text-xs text-muted">
                        {article.primary_keyword}
                      </div>
                    </td>
                    <td className="capitalize">{article.type}</td>
                    <td>{VERTICAL_LABELS[article.vertical]}</td>
                    <td>{article.country ? COUNTRY_LABELS[article.country] : '—'}</td>
                    <td>
                      <StatusBadge status={article.status} />
                    </td>
                    <td>
                      <ScoreBadge score={article.current_score} />
                    </td>
                    <td className="whitespace-nowrap text-xs text-muted">
                      {new Date(article.updated_at).toLocaleDateString()}
                    </td>
                    <td className="whitespace-nowrap">
                      <Link
                        href={`/dashboard/seo/articles/edit/?id=${article.id}`}
                        className="text-xs text-primary hover:underline"
                      >
                        Edit
                      </Link>
                      <span className="mx-2 text-line">|</span>
                      <Link
                        href={`/dashboard/seo/articles/author-review/?id=${article.id}`}
                        className="text-xs text-primary hover:underline"
                      >
                        Review
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </Shell>
  );
}
