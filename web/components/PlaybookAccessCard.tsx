'use client';

import { useEffect, useState } from 'react';
import { Card } from '@/components/ui';
import { PlaybookAccess, apiError, seoApi } from '@/lib/seo';

/**
 * Users page: who gets the Blog Playbook writer. Admins tick logins (or
 * everyone) and save; the API refuses anyone who cannot write articles, and
 * every change is audit-logged. Access set in the server settings shows here
 * as "on (server setting)" and cannot be removed from this card.
 *
 * If the API does not have the route (feature removed), the card hides.
 */
export default function PlaybookAccessCard() {
  const [access, setAccess] = useState<PlaybookAccess | null>(null);
  const [hidden, setHidden] = useState(false);
  const [everyone, setEveryone] = useState(false);
  const [emails, setEmails] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = (data: PlaybookAccess) => {
    setAccess(data);
    setEveryone(data.everyone);
    setEmails(data.emails);
  };

  useEffect(() => {
    seoApi
      .playbookAccess()
      .then(({ data }) => apply(data))
      .catch(() => setHidden(true));
  }, []);

  if (hidden || !access) return null;

  const dirty =
    everyone !== access.everyone ||
    [...emails].sort().join(',') !== [...access.emails].sort().join(',');

  const toggle = (email: string) => {
    const key = email.toLowerCase();
    setEmails((prev) => (prev.includes(key) ? prev.filter((e) => e !== key) : [...prev, key]));
    setNotice(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const { data } = await seoApi.setPlaybookAccess({ everyone, emails });
      apply(data);
      setNotice('Saved. It applies the next time each person opens Write an article.');
    } catch (err) {
      setError(apiError(err, 'Could not save Playbook access.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Blog Playbook access" className="mt-6">
      <p className="mb-4 text-xs text-muted">
        Who sees the Playbook writer on Write an article. The raw editor, scoring
        and publishing are the same for everyone either way.
      </p>

      {access.server_enabled ? (
        <p className="mb-4 text-xs text-warning">
          It is switched on for every SEO login in the server settings, so the ticks
          below make no difference until that is turned off.
        </p>
      ) : (
        <label className="mb-4 flex items-center gap-2 text-sm text-slate-200">
          <input
            type="checkbox"
            checked={everyone}
            onChange={(e) => {
              setEveryone(e.target.checked);
              setNotice(null);
            }}
          />
          Everyone who can write articles
        </label>
      )}

      <ul className="divide-y divide-line">
        {access.users.map((user) => {
          const key = user.email.toLowerCase();
          const locked = user.via_server || everyone || access.server_enabled;
          const on = user.via_server || everyone || access.server_enabled || emails.includes(key);
          return (
            <li key={user.id} className="flex items-center gap-3 py-2">
              <input
                id={`pb-access-${user.id}`}
                type="checkbox"
                checked={on}
                disabled={locked}
                onChange={() => toggle(user.email)}
              />
              <label htmlFor={`pb-access-${user.id}`} className="flex-1 text-sm">
                <span className="text-slate-100">{user.full_name}</span>{' '}
                <span className="text-xs text-muted">{user.email} · {user.role}</span>
              </label>
              {user.via_server && (
                <span className="text-xs text-muted">on (server setting)</span>
              )}
            </li>
          );
        })}
      </ul>

      {error && <p className="mt-3 text-xs text-danger" role="alert">{error}</p>}
      {notice && <p className="mt-3 text-xs text-success" role="status">{notice}</p>}

      <button className="btn-primary mt-4" onClick={save} disabled={saving || !dirty}>
        {saving ? 'Saving…' : 'Save access'}
      </button>
    </Card>
  );
}
