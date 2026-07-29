'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, Skeleton } from '@/components/ui';
import {
  apiError,
  APPROVED_MATRIX,
  ArticleType,
  Country,
  COUNTRY_LABELS,
  PullRequest,
  seoApi,
  Vertical,
  VERTICAL_LABELS,
} from '@/lib/seo';

const PLATFORMS = ['reddit', 'quora', 'paa', 'answerthepublic'] as const;

export default function InboxPage() {
  const router = useRouter();
  const [items, setItems] = useState<PullRequest[] | null>(null);
  const [platform, setPlatform] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [converting, setConverting] = useState<PullRequest | null>(null);

  const load = useCallback(async () => {
    setItems(null);
    try {
      const response = await seoApi.listPullRequests({
        platform: platform || undefined,
        converted: 'false',
      });
      setItems(response.data);
      setError(null);
    } catch (err) {
      setError(apiError(err, 'Could not load the inbox.'));
      setItems([]);
    }
  }, [platform]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Shell
      title="Inbox"
      subtitle="Captured questions waiting to become articles. The scrape cron adds 5-10 a day."
      actions={
        <select
          className="input-field w-48"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          aria-label="Filter by platform"
        >
          <option value="">All platforms</option>
          {PLATFORMS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      }
    >
      <ErrorBanner message={error} />

      {converting && (
        <ConvertPanel
          pullRequest={converting}
          onClose={() => setConverting(null)}
          onDone={(articleId) => {
            setConverting(null);
            router.push(`/dashboard/seo/articles/edit/?id=${articleId}`);
          }}
        />
      )}

      <Card>
        {!items ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            title="The inbox is empty"
            description="Run the Reddit/Quora/PAA scrape cron, or capture a question by hand with POST /api/seo/pull-requests."
          />
        ) : (
          <ul className="divide-y divide-line/60">
            {items.map((item) => (
              <li key={item.id} className="flex items-start gap-4 py-3">
                <span className="badge mt-0.5 shrink-0 border-line bg-raised text-muted">
                  {item.source_platform}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-100">{item.question_captured}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted">
                    {item.suggested_vertical && (
                      <span>{VERTICAL_LABELS[item.suggested_vertical]}</span>
                    )}
                    {item.source_url && (
                      <a
                        href={item.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-primary hover:underline"
                      >
                        source
                      </a>
                    )}
                    {item.captured_at && (
                      <span>{new Date(item.captured_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
                <button className="btn-secondary shrink-0" onClick={() => setConverting(item)}>
                  Convert
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Shell>
  );
}

function ConvertPanel({
  pullRequest,
  onClose,
  onDone,
}: {
  pullRequest: PullRequest;
  onClose: () => void;
  onDone: (articleId: string) => void;
}) {
  const [type, setType] = useState<ArticleType>('content');
  const [vertical, setVertical] = useState<Vertical>(
    pullRequest.suggested_vertical ?? 'agentic_ai',
  );
  const [country, setCountry] = useState<Country | ''>(pullRequest.suggested_country ?? '');
  const [keyword, setKeyword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const allowed = APPROVED_MATRIX[vertical];

  // Switching vertical can invalidate the selected country — clear it rather
  // than letting the request fail server-side.
  useEffect(() => {
    if (country && !allowed.includes(country)) setCountry('');
  }, [vertical, country, allowed]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const { data } = await seoApi.convertPullRequest(pullRequest.id, {
        type,
        vertical,
        country: type === 'onpage' ? country || null : null,
        primary_keyword: keyword,
      });
      onDone(data.article_id);
    } catch (err) {
      setError(apiError(err, 'Could not convert this question.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Convert to article" className="mb-6 border-primary/50">
      <p className="mb-4 text-sm text-slate-300">{pullRequest.question_captured}</p>
      <ErrorBanner message={error} />
      <form onSubmit={submit} className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div>
          <label className="label">Article type</label>
          <select
            className="input-field"
            value={type}
            onChange={(e) => setType(e.target.value as ArticleType)}
          >
            <option value="content">Content</option>
            <option value="onpage">Onpage</option>
          </select>
        </div>
        <div>
          <label className="label">Vertical</label>
          <select
            className="input-field"
            value={vertical}
            onChange={(e) => setVertical(e.target.value as Vertical)}
          >
            {Object.entries(VERTICAL_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Country</label>
          <select
            className="input-field"
            value={country}
            disabled={type === 'content'}
            onChange={(e) => setCountry(e.target.value as Country | '')}
            required={type === 'onpage'}
          >
            <option value="">
              {type === 'content' ? 'Not applicable' : 'Select a country'}
            </option>
            {allowed.map((c) => (
              <option key={c} value={c}>
                {COUNTRY_LABELS[c]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Primary keyword</label>
          <input
            className="input-field"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            required
          />
        </div>
        <div className="flex gap-2 md:col-span-4">
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Converting…' : 'Create draft'}
          </button>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Card>
  );
}
