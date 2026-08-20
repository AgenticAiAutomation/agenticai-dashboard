'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Shell from '@/components/Shell';
import { Card, ErrorBanner, Skeleton } from '@/components/ui';
import {
  APPROVED_MATRIX,
  COUNTRY_LABELS,
  Country,
  ManualFaqInput,
  RankMathReport,
  ScoreReport,
  VERTICAL_LABELS,
  Vertical,
  apiError,
  seoApi,
} from '@/lib/seo';

/**
 * The writer's page. A blank editor that creates and saves an article with no
 * LLM involved at any point — /generate is a separate, optional route.
 *
 * Rank Math's checklist runs on every score and is shown live in the sidebar,
 * so the writer fixes things while writing rather than after submitting.
 */

const EMPTY_FAQ: ManualFaqInput = { question: '', answer: '', source_url: '' };

function ScoreDial({ label, score, grade }: {
  label: string;
  score: number | null;
  grade?: string;
}) {
  // Rank Math's own banding: 0-50 red, 51-80 amber, 81-100 green.
  const tone =
    score === null ? 'text-muted'
      : score >= 81 ? 'text-success'
      : score >= 51 ? 'text-warning'
      : 'text-danger';
  return (
    <div className="flex-1">
      <p className="card-title mb-1">{label}</p>
      <p className={`text-4xl font-semibold tabular-nums ${tone}`}>
        {score ?? '—'}
        <span className="text-base text-muted font-normal">/100</span>
      </p>
      {grade && <p className="text-xs text-muted mt-1 capitalize">{grade}</p>}
    </div>
  );
}

function RankMathPanel({ report }: { report: RankMathReport }) {
  return (
    <div className="space-y-4">
      {Object.entries(report.groups).map(([key, group]) => (
        <div key={key}>
          <div className="flex justify-between text-xs text-muted mb-1">
            <span>{group.label}</span>
            <span className="tabular-nums">
              {group.earned}/{group.available}
            </span>
          </div>
          <div className="h-1.5 bg-raised rounded overflow-hidden">
            <div
              className="h-full bg-primary"
              style={{
                width: `${group.available ? (group.earned / group.available) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      ))}

      <ul className="space-y-1.5 pt-2 border-t border-line">
        {report.tests.map((test) => (
          <li key={test.key} className="flex gap-2 text-xs">
            <span
              aria-hidden="true"
              className={test.passed ? 'text-success' : 'text-danger'}
            >
              {test.passed ? '✓' : '✗'}
            </span>
            <span className="flex-1">
              <span className={test.passed ? 'text-slate-300' : 'text-slate-100'}>
                {test.label}
              </span>
              {!test.passed && (
                <span className="block text-muted mt-0.5">{test.message}</span>
              )}
            </span>
            <span className="sr-only">{test.passed ? 'passed' : 'failed'}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* useSearchParams forces client-side rendering, which the static export cannot
   prerender without a Suspense boundary. Same wrapper pattern as the edit
   page — without it `next build` fails outright on this route. */
export default function WriteArticleRoute() {
  return (
    <Suspense
      fallback={
        <Shell title="Write an article">
          <Skeleton className="h-96 w-full" />
        </Shell>
      }
    >
      <WriteArticlePage />
    </Suspense>
  );
}

function WriteArticlePage() {
  const router = useRouter();
  const params = useSearchParams();
  const existingId = params.get('id');

  const [articleId, setArticleId] = useState<string | null>(existingId);
  const [vertical, setVertical] = useState<Vertical>('whatsapp');
  const [country, setCountry] = useState<Country | ''>('');
  const [keyword, setKeyword] = useState('');
  const [title, setTitle] = useState('');
  const [slug, setSlug] = useState('');
  const [metaTitle, setMetaTitle] = useState('');
  const [metaDescription, setMetaDescription] = useState('');
  const [body, setBody] = useState('');
  const [fromAuthor, setFromAuthor] = useState('');
  const [faqs, setFaqs] = useState<ManualFaqInput[]>([{ ...EMPTY_FAQ }]);

  const [report, setReport] = useState<ScoreReport | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showDanger, setShowDanger] = useState(false);
  const [confirmSlug, setConfirmSlug] = useState('');

  // Load an existing draft when ?id= is present.
  useEffect(() => {
    if (!existingId) return;
    seoApi
      .getArticle(existingId)
      .then(({ data }) => {
        setVertical(data.vertical);
        setCountry(data.country ?? '');
        setKeyword(data.primary_keyword ?? '');
        setTitle(data.title ?? '');
        setSlug(data.slug ?? '');
        setMetaTitle(data.meta_title ?? '');
        setMetaDescription(data.meta_description ?? '');
        setBody(data.team_edit_md ?? data.author_draft_md ?? '');
        setFromAuthor(data.from_author_story ?? '');
        setFaqs(
          data.faqs.length
            ? data.faqs.map((f) => ({
                question: f.question,
                answer: f.answer ?? '',
                source_url: f.source_url ?? '',
              }))
            : [{ ...EMPTY_FAQ }],
        );
      })
      .catch((err) => setError(apiError(err)));
  }, [existingId]);

  const wordCount = useMemo(
    () => body.split(/\s+/).filter(Boolean).length,
    [body],
  );

  const cleanFaqs = useCallback(
    () =>
      faqs
        .filter((f) => f.question.trim() && f.answer.trim())
        .map((f) => ({
          question: f.question.trim(),
          answer: f.answer.trim(),
          source_url: f.source_url?.trim() || null,
        })),
    [faqs],
  );

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
      const payload = {
        title: title || keyword,
        slug: slug || undefined,
        body_md: body,
        meta_title: metaTitle || null,
        meta_description: metaDescription || null,
        primary_keyword: keyword,
        from_author_story: fromAuthor || null,
        faqs: cleanFaqs(),
      };

      if (articleId) {
        await seoApi.saveDraft(articleId, payload);
        setNotice('Draft saved.');
      } else {
        const { data } = await seoApi.createManual({
          ...payload,
          type: 'content',
          vertical,
          country: country || null,
        });
        setArticleId(data.id);
        setSlug(data.slug ?? '');
        setNotice('Draft created.');
        router.replace(`/dashboard/seo/articles/write/?id=${data.id}`);
      }
    });

  const score = () =>
    run('score', async () => {
      if (!articleId) {
        setError('Save the draft once before scoring it.');
        return;
      }
      await seoApi.saveDraft(articleId, {
        title: title || keyword,
        body_md: body,
        meta_title: metaTitle || null,
        meta_description: metaDescription || null,
        primary_keyword: keyword,
        from_author_story: fromAuthor || null,
        faqs: cleanFaqs(),
      });
      const { data } = await seoApi.score(articleId);
      setReport(data);
    });

  const rankMath = report?.rank_math ?? null;

  const archive = () =>
    run('archive', async () => {
      if (!articleId) return;
      await seoApi.archive(articleId);
      setNotice('Archived. It is out of the pipeline but nothing was destroyed — restore it any time.');
    });

  const destroy = () =>
    run('delete', async () => {
      if (!articleId) return;
      const { data } = await seoApi.remove(articleId, confirmSlug.trim());
      setNotice(
        `Deleted "${data.title ?? data.slug}". Removed ${data.deleted_faqs} FAQ(s), ` +
          `${data.deleted_scores} score(s), ${data.deleted_versions} version(s).`,
      );
      setArticleId(null);
      setConfirmSlug('');
      setShowDanger(false);
      router.push('/dashboard/seo/articles');
    });

  return (
    <Shell
      title="Write an article"
      subtitle="A blank page. No AI generation — you write it, Rank Math checks it."
      actions={
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={save} disabled={busy !== null}>
            {busy === 'save' ? 'Saving…' : articleId ? 'Save draft' : 'Create draft'}
          </button>
          <button className="btn-primary" onClick={score} disabled={busy !== null || !articleId}>
            {busy === 'score' ? 'Scoring…' : 'Save & score'}
          </button>
        </div>
      }
    >
      <ErrorBanner message={error} />
      {notice && (
        <p className="mb-4 text-sm text-success" role="status">
          {notice}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ---------------- editor ---------------- */}
        <div className="lg:col-span-2 space-y-6">
          <Card title="The basics">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="label" htmlFor="keyword">
                  Focus keyword <span className="text-danger">*</span>
                </label>
                <input
                  id="keyword"
                  className="input-field"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="whatsapp automation for clinics"
                />
              </div>

              <div>
                <label className="label" htmlFor="vertical">Vertical</label>
                <select
                  id="vertical"
                  className="input-field"
                  value={vertical}
                  disabled={!!articleId}
                  onChange={(e) => {
                    setVertical(e.target.value as Vertical);
                    setCountry('');
                  }}
                >
                  {Object.entries(VERTICAL_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>

              <div className="sm:col-span-2">
                <label className="label" htmlFor="title">Title</label>
                <input
                  id="title"
                  className="input-field"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="WhatsApp Automation for Clinics: A Practical Guide"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="label" htmlFor="slug">URL slug</label>
                <input
                  id="slug"
                  className="input-field"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="whatsapp-automation-for-clinics"
                />
              </div>
            </div>
          </Card>

          <Card
            title="Body"
            action={
              <span className="text-xs text-muted tabular-nums">
                {wordCount} words · Rank Math wants 600+
              </span>
            }
          >
            <label className="sr-only" htmlFor="body">Article body in Markdown</label>
            <textarea
              id="body"
              className="input-field font-mono text-sm leading-relaxed"
              rows={26}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={'# Your headline\n\nWrite in Markdown. Use ## for sections.\n\nLink internally with [text](/services) and externally with [text](https://example.com).'}
            />
          </Card>

          <Card title="Search appearance">
            <div className="space-y-4">
              <div>
                <label className="label" htmlFor="metaTitle">
                  SEO title · {metaTitle.length}/60
                </label>
                <input
                  id="metaTitle"
                  className="input-field"
                  value={metaTitle}
                  onChange={(e) => setMetaTitle(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="metaDescription">
                  Meta description · {metaDescription.length}/160
                </label>
                <textarea
                  id="metaDescription"
                  className="input-field"
                  rows={3}
                  value={metaDescription}
                  onChange={(e) => setMetaDescription(e.target.value)}
                />
              </div>
            </div>
          </Card>

          <Card
            title="FAQs"
            action={
              <button
                className="btn-secondary text-xs"
                onClick={() => setFaqs([...faqs, { ...EMPTY_FAQ }])}
              >
                Add FAQ
              </button>
            }
          >
            <p className="text-xs text-muted mb-4">
              Five or more, each with the URL where the question was actually asked.
              The house scorer gives 8 points for sourced FAQs and zero for invented ones.
            </p>
            <div className="space-y-4">
              {faqs.map((faq, index) => (
                <div key={index} className="bg-raised border border-line rounded-lg p-3 space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-muted">FAQ {index + 1}</span>
                    {faqs.length > 1 && (
                      <button
                        className="text-xs text-danger"
                        onClick={() => setFaqs(faqs.filter((_, i) => i !== index))}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                  <label className="sr-only" htmlFor={`faq-q-${index}`}>Question {index + 1}</label>
                  <input
                    id={`faq-q-${index}`}
                    className="input-field"
                    placeholder="Question"
                    value={faq.question}
                    onChange={(e) => {
                      const next = [...faqs];
                      next[index] = { ...faq, question: e.target.value };
                      setFaqs(next);
                    }}
                  />
                  <label className="sr-only" htmlFor={`faq-a-${index}`}>Answer {index + 1}</label>
                  <textarea
                    id={`faq-a-${index}`}
                    className="input-field"
                    rows={3}
                    placeholder="Answer — 30 to 80 words is the featured-snippet range"
                    value={faq.answer}
                    onChange={(e) => {
                      const next = [...faqs];
                      next[index] = { ...faq, answer: e.target.value };
                      setFaqs(next);
                    }}
                  />
                  <label className="sr-only" htmlFor={`faq-s-${index}`}>Source URL {index + 1}</label>
                  <input
                    id={`faq-s-${index}`}
                    className="input-field"
                    placeholder="Source URL (Reddit / Quora / People Also Ask)"
                    value={faq.source_url ?? ''}
                    onChange={(e) => {
                      const next = [...faqs];
                      next[index] = { ...faq, source_url: e.target.value };
                      setFaqs(next);
                    }}
                  />
                </div>
              ))}
            </div>
          </Card>

          {articleId && (
            <Card title="Danger zone">
              <p className="text-xs text-muted mb-4">
                Archiving is reversible and keeps the score history. Deleting is not.
              </p>

              <div className="flex flex-wrap gap-2">
                <button className="btn-secondary" onClick={archive} disabled={busy !== null}>
                  {busy === 'archive' ? 'Archiving…' : 'Archive'}
                </button>
                <button
                  className="btn-danger"
                  onClick={() => setShowDanger(!showDanger)}
                  disabled={busy !== null}
                  aria-expanded={showDanger}
                >
                  Delete permanently…
                </button>
              </div>

              {showDanger && (
                <div className="mt-4 pt-4 border-t border-line space-y-3">
                  <p className="text-xs text-slate-300">
                    This removes the article, its FAQs, sources, versions and score
                    history. Calendar slots and cost records are kept. It cannot be
                    undone, and published articles cannot be deleted here at all.
                  </p>
                  <label className="label" htmlFor="confirmSlug">
                    Type the slug <code className="text-warning">{slug}</code> to confirm
                  </label>
                  <input
                    id="confirmSlug"
                    className="input-field"
                    value={confirmSlug}
                    onChange={(e) => setConfirmSlug(e.target.value)}
                    placeholder={slug}
                    autoComplete="off"
                  />
                  <button
                    className="btn-danger"
                    onClick={destroy}
                    disabled={busy !== null || confirmSlug.trim() !== slug}
                  >
                    {busy === 'delete' ? 'Deleting…' : 'I understand — delete it'}
                  </button>
                </div>
              )}
            </Card>
          )}

          <Card title="From the author">
            <p className="text-xs text-muted mb-3">
              A real production story with numbers — what broke, what it cost, what you
              would do differently. Publishing is blocked while this is empty.
            </p>
            <label className="sr-only" htmlFor="fromAuthor">From the author</label>
            <textarea
              id="fromAuthor"
              className="input-field"
              rows={6}
              value={fromAuthor}
              onChange={(e) => setFromAuthor(e.target.value)}
            />
          </Card>
        </div>

        {/* ---------------- scores ---------------- */}
        <div className="space-y-6">
          <Card title="Scores">
            <div className="flex gap-4">
              <ScoreDial label="House" score={report?.total_score ?? null} />
              <ScoreDial
                label="Rank Math"
                score={rankMath?.total_score ?? null}
                grade={rankMath?.grade}
              />
            </div>
            {!report && (
              <p className="text-xs text-muted mt-4">
                Save the draft, then press <strong>Save &amp; score</strong>. The two
                engines measure different things and are meant to disagree.
              </p>
            )}
            {report && report.blocking_issues.length > 0 && (
              <div className="mt-4 pt-4 border-t border-line">
                <p className="card-title text-danger mb-2">Blocking publish</p>
                <ul className="space-y-1 text-xs text-slate-300">
                  {report.blocking_issues.map((issue) => (
                    <li key={issue}>• {issue}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {rankMath && (
            <Card title={`Rank Math checklist · ${rankMath.failed.length} to fix`}>
              <RankMathPanel report={rankMath} />
            </Card>
          )}

          {report && report.comments.length > 0 && (
            <Card title="House scorer — biggest wins">
              <ul className="space-y-3">
                {report.comments.slice(0, 8).map((comment, index) => (
                  <li key={index} className="text-xs">
                    <span className="text-warning tabular-nums">
                      +{comment.impact_points}
                    </span>{' '}
                    <span className="text-slate-300">{comment.suggested_fix}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </Shell>
  );
}
