'use client';

import { useCallback, useEffect, useState } from 'react';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, Skeleton } from '@/components/ui';
import { apiError, seoApi } from '@/lib/seo';

interface Backlink {
  id: string;
  source_url: string;
  source_domain: string | null;
  target_url: string;
  anchor_text: string | null;
  referring_dr: number | null;
  status: 'new' | 'verified' | 'lost';
  discovered_at: string | null;
}

const STATUS_TONE: Record<string, string> = {
  new: 'border-primary/40 bg-primary/10 text-primary',
  verified: 'border-success/40 bg-success/10 text-success',
  lost: 'border-danger/40 bg-danger/10 text-danger',
};

export default function BacklinksPage() {
  const [links, setLinks] = useState<Backlink[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    source_url: '',
    target_url: '',
    anchor_text: '',
    referring_dr: '',
  });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await seoApi.backlinks();
      setLinks(data);
      setError(null);
    } catch (err) {
      setError(apiError(err, 'Could not load backlinks.'));
      setLinks([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await seoApi.addBacklink({
        source_url: form.source_url,
        target_url: form.target_url,
        anchor_text: form.anchor_text || null,
        referring_dr: form.referring_dr ? Number(form.referring_dr) : null,
      });
      setForm({ source_url: '', target_url: '', anchor_text: '', referring_dr: '' });
      await load();
    } catch (err) {
      setError(apiError(err, 'Could not add the backlink.'));
    } finally {
      setSaving(false);
    }
  };

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <Shell
      title="Backlinks"
      subtitle="Manual entries plus anything the Ubersuggest paste and HARO parser find. Target: 3 per week."
    >
      <ErrorBanner message={error} />

      <Card title="Add a backlink" className="mb-4">
        <form onSubmit={submit} className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div className="md:col-span-2">
            <label className="label">Source URL</label>
            <input
              className="input-field"
              value={form.source_url}
              onChange={set('source_url')}
              placeholder="https://example.com/post"
              required
            />
          </div>
          <div className="md:col-span-2">
            <label className="label">Target URL</label>
            <input
              className="input-field"
              value={form.target_url}
              onChange={set('target_url')}
              placeholder="https://agenticaiautomation.co/blog/…"
              required
            />
          </div>
          <div>
            <label className="label">Referring DR</label>
            <input
              className="input-field"
              type="number"
              min={0}
              max={100}
              value={form.referring_dr}
              onChange={set('referring_dr')}
            />
          </div>
          <div className="md:col-span-4">
            <label className="label">Anchor text</label>
            <input
              className="input-field"
              value={form.anchor_text}
              onChange={set('anchor_text')}
            />
          </div>
          <div className="flex items-end">
            <button type="submit" className="btn-primary w-full" disabled={saving}>
              {saving ? 'Adding…' : 'Add'}
            </button>
          </div>
        </form>
      </Card>

      <Card>
        {!links ? (
          <Skeleton className="h-40 w-full" />
        ) : links.length === 0 ? (
          <EmptyState
            title="No backlinks tracked yet"
            description="Add the first one above, or log HARO placements as they land."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source domain</th>
                  <th>Anchor</th>
                  <th>Target</th>
                  <th>DR</th>
                  <th>Status</th>
                  <th>Discovered</th>
                </tr>
              </thead>
              <tbody>
                {links.map((link) => (
                  <tr key={link.id}>
                    <td>
                      <a
                        href={link.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-primary hover:underline"
                      >
                        {link.source_domain ?? link.source_url}
                      </a>
                    </td>
                    <td className="max-w-xs truncate">{link.anchor_text ?? '—'}</td>
                    <td className="max-w-xs truncate text-xs text-muted">
                      {link.target_url}
                    </td>
                    <td className="tabular-nums">{link.referring_dr ?? '—'}</td>
                    <td>
                      <span className={`badge ${STATUS_TONE[link.status]}`}>
                        {link.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap text-xs text-muted">
                      {link.discovered_at
                        ? new Date(link.discovered_at).toLocaleDateString()
                        : '—'}
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
