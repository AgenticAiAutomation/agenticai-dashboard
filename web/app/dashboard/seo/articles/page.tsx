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
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    status: '',
    type: '',
    vertical: '',
    country: '',
  });

  /* Taking a live article down. The record survives and goes back to team
     review, so it can be corrected and republished rather than rewritten. */
  const unpublish = async (article: Article) => {
    if (!window.confirm(
      `Remove "${article.title ?? article.slug}" from the website?

` +
      'The live URL stops working immediately and the removal is submitted to ' +
      'IndexNow. The article itself is kept and returns to team review, so you ' +
      'can fix it and publish again.',
    )) return;

    setBusy(`un-${article.id}`);
    setError(null);
    setNotice(null);
    try {
      await seoApi.unpublish(article.id);
      setNotice(`"${article.title ?? article.slug}" is off the website.`);
      await load();
    } catch (err) {
      setError(apiError(err));
    } finally {
      setBusy(null);
    }
  };

  /* Permanent. The slug has to be typed, matching the server-side guard, so a
     mis-click on a stale list cannot destroy the wrong article. */
  const remove = async (article: Article) => {
    const slug = article.slug ?? '';
    const live = article.status === 'published';
    const typed = window.prompt(
      (live ? 'This article is LIVE on the website.\n\n' : '') +
      'Deleting removes the article, its FAQs, sources, versions and score ' +
      'history permanently. This cannot be undone.' +
      (live
        ? ' The page is taken off the site first and the removal is submitted to IndexNow.'
        : '') +
      `\n\nType the slug to confirm:\n${slug}`,
    );
    if (typed === null) return;
    if (typed.trim() !== slug) {
      setError('The slug did not match, so nothing was deleted.');
      return;
    }

    setBusy(`del-${article.id}`);
    setError(null);
    setNotice(null);
    try {
      const { data } = await seoApi.remove(article.id, slug);
      setNotice(
        `Deleted "${data.title ?? data.slug}". Removed ${data.deleted_faqs} FAQ(s), ` +
        `${data.deleted_scores} score(s), ${data.deleted_versions} version(s).`,
      );
      await load();
    } catch (err) {
      setError(apiError(err));
    } finally {
      setBusy(null);
    }
  };

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
        <div className="flex gap-2">
          {/* Writing is the primary path and needs no LLM key; generation is
              the assisted alternative, so it takes the secondary button. */}
          <Link href="/dashboard/seo/articles/write" className="btn-primary">
            Write an article
          </Link>
          <Link href="/dashboard/seo/articles/new" className="btn-secondary">
            Generate with AI
          </Link>
          <Link href="/dashboard/seo/articles/scoring-guide" className="btn-secondary">
            Scoring guide
          </Link>
        </div>
      }
    >
      <ErrorBanner message={error} />
      {notice && (
        <p className="mb-4 text-sm text-success" role="status">
          {notice}
        </p>
      )}

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
            description="Write one from scratch, convert a question from the inbox, or generate a draft from a keyword."
            action={
              <Link href="/dashboard/seo/articles/write" className="btn-primary">
                Write the first article
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
                        href={`/dashboard/seo/articles/write/?id=${article.id}`}
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
                      {article.status === 'published' && (
                        <>
                          <span className="mx-2 text-line">|</span>
                          <a
                            href={`https://agenticaiautomation.co/blog/${article.slug}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary hover:underline"
                          >
                            View
                          </a>
                          <span className="mx-2 text-line">|</span>
                          <button
                            onClick={() => unpublish(article)}
                            disabled={busy !== null}
                            className="text-xs text-warning hover:underline disabled:opacity-40"
                          >
                            {busy === `un-${article.id}` ? 'Removing…' : 'Unpublish'}
                          </button>
                        </>
                      )}
                      <span className="mx-2 text-line">|</span>
                      <button
                        onClick={() => remove(article)}
                        disabled={busy !== null}
                        className="text-xs text-danger hover:underline disabled:opacity-40"
                      >
                        {busy === `del-${article.id}` ? 'Deleting…' : 'Delete'}
                      </button>
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
