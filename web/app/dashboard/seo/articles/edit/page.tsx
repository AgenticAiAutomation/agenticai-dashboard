'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import Shell from '@/components/Shell';
import MarkdownEditor from '@/components/MarkdownEditor';
import {
  Card,
  EmptyState,
  ErrorBanner,
  ScoreBadge,
  Skeleton,
  StatusBadge,
} from '@/components/ui';
import {
  apiError,
  ArticleDetail,
  COUNTRY_LABELS,
  SITE_LINK_TARGETS,
  ScoreReport,
  seoApi,
  VERTICAL_LABELS,
} from '@/lib/seo';

const GROUP_LABELS: Record<string, string> = {
  content_quality: 'Content quality',
  onpage_seo: 'On-page SEO',
  faq_eeat: 'FAQ + EEAT',
  technical: 'Technical',
};

// Weeks 1-4 hand off at 70; from week 5 the bar is 80.
const HANDOFF_MIN_SCORE = 70;

export default function EditArticleRoute() {
  return (
    <Suspense
      fallback={
        <Shell title="Edit article">
          <Skeleton className="h-96 w-full" />
        </Shell>
      }
    >
      <EditArticlePage />
    </Suspense>
  );
}

function EditArticlePage() {
  const params = useSearchParams();
  const id = params.get('id');

  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [draft, setDraft] = useState('');
  const [metaTitle, setMetaTitle] = useState('');
  const [metaDescription, setMetaDescription] = useState('');
  const [imageAlt, setImageAlt] = useState('');
  const [report, setReport] = useState<ScoreReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const { data } = await seoApi.getArticle(id);
      setArticle(data);
      // The team panel starts as a copy of the author draft.
      setDraft(data.team_edit_md ?? data.author_draft_md ?? '');
      setMetaTitle(data.meta_title ?? '');
      setMetaDescription(data.meta_description ?? '');
      setImageAlt(data.featured_image_alt ?? '');
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

  const save = () =>
    run('save', async () => {
      if (!id) return;
      const { data } = await seoApi.teamEdit(id, {
        team_edit_md: draft,
        meta_title: metaTitle || null,
        meta_description: metaDescription || null,
        featured_image_alt: imageAlt || null,
      });
      setArticle(data);
      setNotice('Team edit saved as a new version.');
    });

  const score = () =>
    run('score', async () => {
      if (!id) return;
      await seoApi.teamEdit(id, {
        team_edit_md: draft,
        meta_title: metaTitle || null,
        meta_description: metaDescription || null,
        featured_image_alt: imageAlt || null,
      });
      const { data } = await seoApi.score(id);
      setReport(data);
      await load();
    });

  const submitForAuthor = () =>
    run('submit', async () => {
      if (!id) return;
      await seoApi.submitForAuthor(id, HANDOFF_MIN_SCORE);
      await load();
      setNotice('Sent to the author for the From Author section.');
    });

  const uploadImage = (file: File) =>
    run('image', async () => {
      if (!id) return;
      await seoApi.uploadImage(id, file);
      await load();
      setNotice('Featured image uploaded. Generate the alt caption next.');
    });

  const generateAlt = () =>
    run('alt', async () => {
      if (!id) return;
      const { data } = await seoApi.generateAlt(id);
      await load();
      setNotice(`Alt caption generated: "${data.featured_image_alt}"`);
    });

  if (!id) {
    return (
      <Shell title="Edit article">
        <EmptyState
          title="No article selected"
          description="Open an article from the list to edit it."
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
      <Shell title="Edit article">
        <ErrorBanner message={error} />
        <Skeleton className="h-96 w-full" />
      </Shell>
    );
  }

  const currentScore = report?.total_score ?? article.current_score;
  const canSubmit = (currentScore ?? 0) >= HANDOFF_MIN_SCORE;

  return (
    <Shell
      title={article.title ?? 'Untitled article'}
      subtitle={`${VERTICAL_LABELS[article.vertical]}${
        article.country ? ` · ${COUNTRY_LABELS[article.country]}` : ''
      } · ${article.primary_keyword}`}
      actions={
        <>
          <StatusBadge status={article.status} />
          <button className="btn-secondary" onClick={save} disabled={busy !== null}>
            {busy === 'save' ? 'Saving…' : 'Save'}
          </button>
          <button className="btn-secondary" onClick={score} disabled={busy !== null}>
            {busy === 'score' ? 'Scoring…' : 'Score draft'}
          </button>
          <button
            className="btn-primary"
            onClick={submitForAuthor}
            disabled={busy !== null || !canSubmit}
            title={
              canSubmit
                ? undefined
                : `Score must reach ${HANDOFF_MIN_SCORE} before hand-off (currently ${
                    currentScore ?? 0
                  }).`
            }
          >
            Submit for author review
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

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr_360px]">
        {/* Left: author draft, read-only */}
        <Card title="Author draft (read-only)">
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg bg-raised p-4 font-mono text-xs leading-relaxed text-slate-300">
            {article.author_draft_md ?? 'No author draft was generated for this article.'}
          </pre>
        </Card>

        {/* Middle: team edit */}
        <Card title="Team edit">
          {/* Same editor as the write page: headings, links and the internal
              link picker, rather than raw markdown in a bare textarea. */}
          <MarkdownEditor
            id="team-edit-body"
            value={draft}
            onChange={setDraft}
            rows={28}
            linkTargets={SITE_LINK_TARGETS}
          />
          <div className="mt-3 grid grid-cols-1 gap-3">
            <div>
              <label className="label" htmlFor="meta-title">
                Meta title
              </label>
              <input
                id="meta-title"
                className="input-field"
                value={metaTitle}
                onChange={(e) => setMetaTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="meta-desc">
                Meta description{' '}
                <span
                  className={
                    metaDescription.length >= 140 && metaDescription.length <= 160
                      ? 'text-success'
                      : 'text-warning'
                  }
                >
                  {metaDescription.length}/140-160
                </span>
              </label>
              <textarea
                id="meta-desc"
                className="input-field min-h-[70px]"
                value={metaDescription}
                onChange={(e) => setMetaDescription(e.target.value)}
              />
            </div>
          </div>
        </Card>

        {/* Right: score sidebar + image */}
        <div className="space-y-4">
          <Card title="SEO score">
            <div className="flex items-baseline gap-3">
              <span className="text-kpi font-semibold tabular-nums text-white">
                {currentScore ?? '—'}
              </span>
              <span className="text-lg text-muted">/ 100</span>
            </div>
            {!report && (
              <p className="mt-2 text-xs text-muted">
                Run Score draft to get the group breakdown and line-by-line comments.
              </p>
            )}

            {report && (
              <>
                <ul className="mt-4 space-y-2">
                  {Object.entries(report.groups).map(([key, values]) => (
                    <li key={key}>
                      <div className="flex justify-between text-xs">
                        <span className="text-muted">{GROUP_LABELS[key] ?? key}</span>
                        <span className="tabular-nums text-slate-200">
                          {values.earned} / {values.available}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-raised">
                        <div
                          className="h-1.5 rounded-full bg-primary"
                          style={{
                            width: `${
                              values.available > 0
                                ? (values.earned / values.available) * 100
                                : 0
                            }%`,
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>

                {report.blocking_issues.length > 0 && (
                  <div className="mt-4 rounded-lg border border-warning/40 bg-warning/10 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-warning">
                      Blocking publish
                    </p>
                    <ul className="mt-1.5 space-y-1 text-xs text-warning/90">
                      {report.blocking_issues.map((issue) => (
                        <li key={issue}>• {issue}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </Card>

          <Card title="Featured image">
            {article.featured_image_path ? (
              <p className="break-all text-xs text-muted">{article.featured_image_path}</p>
            ) : (
              <p className="text-xs text-muted">
                No image uploaded. WordPress rejects a publish without one.
              </p>
            )}

            <input
              ref={fileInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadImage(file);
                e.target.value = '';
              }}
            />
            <div className="mt-3 flex gap-2">
              <button
                className="btn-secondary flex-1"
                onClick={() => fileInput.current?.click()}
                disabled={busy !== null}
              >
                {busy === 'image' ? 'Uploading…' : 'Upload'}
              </button>
              <button
                className="btn-secondary flex-1"
                onClick={generateAlt}
                disabled={busy !== null || !article.featured_image_path}
              >
                {busy === 'alt' ? 'Writing…' : 'Generate alt'}
              </button>
            </div>

            {/* Typed by hand. "Generate alt" above needs an Anthropic key, and
                publishing is blocked while this is empty — so without a key
                there was previously no way to fill it at all. */}
            <div className="mt-4">
              <label className="label" htmlFor="imageAlt">
                Alt text · {imageAlt.length} characters
              </label>
              <textarea
                id="imageAlt"
                className="input-field text-xs"
                rows={2}
                value={imageAlt}
                onChange={(e) => setImageAlt(e.target.value)}
                placeholder="Describe the image for someone who cannot see it"
              />
              <p className="mt-1.5 text-xs text-muted">
                Saved with the draft. Required before publishing.
              </p>
            </div>
          </Card>

          <Card title={`FAQs (${article.faqs.length})`}>
            {article.faqs.length === 0 ? (
              <p className="text-xs text-muted">No FAQs captured for this article.</p>
            ) : (
              <ul className="space-y-2">
                {article.faqs.map((faq) => (
                  <li key={faq.id} className="rounded-lg bg-raised p-2">
                    <p className="text-xs font-medium text-slate-200">{faq.question}</p>
                    {faq.source_url ? (
                      <a
                        href={faq.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-xs text-primary hover:underline"
                      >
                        proof source
                      </a>
                    ) : (
                      <span className="text-xs text-warning">no proof URL</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {report && report.comments.length > 0 && (
        <Card title="Line-by-line comments" className="mt-4">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-16">Line</th>
                  <th className="w-20">Impact</th>
                  <th>Current text</th>
                  <th>Suggested fix</th>
                </tr>
              </thead>
              <tbody>
                {report.comments.map((comment, index) => (
                  <tr key={`${comment.line_number}-${index}`}>
                    <td className="tabular-nums text-muted">{comment.line_number}</td>
                    <td className="tabular-nums text-warning">
                      −{comment.impact_points}
                    </td>
                    <td className="max-w-md truncate font-mono text-xs text-slate-300">
                      {comment.current_text}
                    </td>
                    <td className="text-xs text-slate-200">{comment.suggested_fix}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </Shell>
  );
}
