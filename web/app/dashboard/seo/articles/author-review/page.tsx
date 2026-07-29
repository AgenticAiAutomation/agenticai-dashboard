'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, Skeleton, StatusBadge } from '@/components/ui';
import {
  apiError,
  ArticleDetail,
  COUNTRY_LABELS,
  seoApi,
  VERTICAL_LABELS,
} from '@/lib/seo';

export default function AuthorReviewRoute() {
  return (
    <Suspense
      fallback={
        <Shell title="Author review">
          <Skeleton className="h-96 w-full" />
        </Shell>
      }
    >
      <AuthorReviewPage />
    </Suspense>
  );
}

function AuthorReviewPage() {
  const params = useSearchParams();
  const id = params.get('id');

  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [story, setStory] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const { data } = await seoApi.getArticle(id);
      setArticle(data);
      setStory(data.from_author_story ?? '');
      setError(null);
    } catch (err) {
      setError(apiError(err, 'Could not load this article.'));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await fn();
    } catch (err) {
      setError(apiError(err));
    } finally {
      setBusy(null);
    }
  };

  const saveStory = () =>
    run('story', async () => {
      if (!id) return;
      await seoApi.setFromAuthor(id, story);
      await load();
      setNotice('From Author section saved and merged into the final copy.');
    });

  const regenerateAlt = () =>
    run('alt', async () => {
      if (!id) return;
      const { data } = await seoApi.generateAlt(id);
      await load();
      setNotice(`New alt caption: "${data.featured_image_alt}"`);
    });

  const publish = () =>
    run('publish', async () => {
      if (!id) return;
      const { data } = await seoApi.publish(id);
      await load();
      setNotice(data.message);
    });

  if (!id) {
    return (
      <Shell title="Author review">
        <EmptyState
          title="No article selected"
          description="Open an article from the list to review it."
          action={
            <Link href="/dashboard/seo/articles" className="btn-primary">
              Back to articles
            </Link>
          }
        />
      </Shell>
    );
  }

  if (!article) {
    return (
      <Shell title="Author review">
        <ErrorBanner message={error} />
        <Skeleton className="h-96 w-full" />
      </Shell>
    );
  }

  const wordCount = story.trim() ? story.trim().split(/\s+/).length : 0;
  const blockers: string[] = [];
  if ((article.current_score ?? 0) < 80)
    blockers.push(`Score is ${article.current_score ?? 0}/100; publishing needs 80.`);
  if (!article.from_author_story?.trim())
    blockers.push('The From Author section is not saved yet.');
  if (!article.featured_image_alt?.trim()) blockers.push('The alt caption is missing.');
  if (!article.featured_image_path) blockers.push('No featured image is uploaded.');

  return (
    <Shell
      title={article.title ?? 'Untitled article'}
      subtitle={`${VERTICAL_LABELS[article.vertical]}${
        article.country ? ` · ${COUNTRY_LABELS[article.country]}` : ''
      } · author review`}
      actions={
        <>
          <StatusBadge status={article.status} />
          <button
            className="btn-primary"
            onClick={publish}
            disabled={busy !== null || blockers.length > 0}
            title={blockers.length ? blockers.join(' ') : undefined}
          >
            {busy === 'publish' ? 'Publishing…' : 'Approve & publish'}
          </button>
        </>
      }
    >
      <ErrorBanner message={error} />
      {notice && (
        <div className="mb-4 rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
          {notice}
        </div>
      )}

      {blockers.length > 0 && (
        <div className="mb-4 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          <p className="font-semibold">Publishing is blocked until these are resolved:</p>
          <ul className="mt-1.5 space-y-1">
            {blockers.map((blocker) => (
              <li key={blocker}>• {blocker}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_400px]">
        <Card title="Final copy">
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg bg-raised p-4 font-mono text-xs leading-relaxed text-slate-300">
            {article.final_md ?? article.team_edit_md ?? '(nothing submitted yet)'}
          </pre>
        </Card>

        <div className="space-y-4">
          <Card title="From Author">
            <p className="mb-2 text-xs text-muted">
              A real production story with specifics — numbers, timelines, what broke. Around
              200 words. Currently {wordCount}.
            </p>
            <textarea
              className="input-field min-h-[240px]"
              value={story}
              onChange={(e) => setStory(e.target.value)}
              placeholder="When we rolled this out for a client in…"
            />
            <button
              className="btn-primary mt-3 w-full"
              onClick={saveStory}
              disabled={busy !== null || !story.trim()}
            >
              {busy === 'story' ? 'Saving…' : 'Save From Author section'}
            </button>
          </Card>

          <Card title="Alt caption">
            {article.featured_image_alt ? (
              <p className="rounded-lg bg-raised p-3 text-sm text-slate-200">
                {article.featured_image_alt}
              </p>
            ) : (
              <p className="text-xs text-muted">No alt caption generated yet.</p>
            )}
            <button
              className="btn-secondary mt-3 w-full"
              onClick={regenerateAlt}
              disabled={busy !== null || !article.featured_image_path}
            >
              {busy === 'alt' ? 'Regenerating…' : 'Regenerate alt caption'}
            </button>
          </Card>

          {article.wp_published_url && (
            <Card title="WordPress">
              <a
                href={article.wp_published_url}
                target="_blank"
                rel="noreferrer noopener"
                className="break-all text-sm text-primary hover:underline"
              >
                {article.wp_published_url}
              </a>
              <p className="mt-1 text-xs text-muted">Post ID {article.wp_post_id}</p>
            </Card>
          )}
        </div>
      </div>
    </Shell>
  );
}
