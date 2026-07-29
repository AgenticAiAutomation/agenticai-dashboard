'use client';

import { useCallback, useEffect, useState } from 'react';
import api from '@/lib/api';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, ScoreBadge, Skeleton } from '@/components/ui';
import { apiError, COUNTRY_LABELS, VERTICAL_LABELS } from '@/lib/seo';

interface ManagedUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  totp_enabled: boolean;
  assigned_verticals: string[] | null;
  assigned_countries: string[] | null;
  last_login_at: string | null;
  created_at: string;
  articles_drafted_this_week: number;
  avg_score: number | null;
}

const ROLES = [
  { value: 'admin', label: 'Admin — full access, including publishing and users' },
  { value: 'seo_lead', label: 'SEO lead — create and edit articles' },
  { value: 'viewer', label: 'Viewer — read only' },
];

export default function UsersPage() {
  const [users, setUsers] = useState<ManagedUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [credential, setCredential] = useState<{ email: string; password: string } | null>(
    null,
  );
  const [form, setForm] = useState({
    email: '',
    full_name: '',
    role: 'seo_lead',
    assigned_verticals: [] as string[],
    assigned_countries: [] as string[],
  });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<ManagedUser[]>('/users');
      setUsers(data);
      setError(null);
    } catch (err) {
      setError(apiError(err, 'You do not have permission to manage users.'));
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      // Omitting `password` makes the API generate a compliant one and return
      // it exactly once.
      const { data } = await api.post('/users', form);
      if (data.generated_password) {
        setCredential({ email: data.email, password: data.generated_password });
      }
      setForm({
        email: '',
        full_name: '',
        role: 'seo_lead',
        assigned_verticals: [],
        assigned_countries: [],
      });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(apiError(err, 'Could not create the user.'));
    } finally {
      setSaving(false);
    }
  };

  const resetPassword = async (user: ManagedUser) => {
    if (
      !confirm(
        `Reset the password for ${user.email}? Their active sessions will be ended.`,
      )
    )
      return;
    try {
      const { data } = await api.post(`/users/${user.id}/reset-password`, {});
      if (data.generated_password) {
        setCredential({ email: data.email, password: data.generated_password });
      }
      await load();
    } catch (err) {
      setError(apiError(err, 'Could not reset the password.'));
    }
  };

  const toggleActive = async (user: ManagedUser) => {
    try {
      await api.patch(`/users/${user.id}`, { is_active: !user.is_active });
      await load();
    } catch (err) {
      setError(apiError(err, 'Could not update the account.'));
    }
  };

  const toggleScope = (field: 'assigned_verticals' | 'assigned_countries', key: string) =>
    setForm((prev) => ({
      ...prev,
      [field]: prev[field].includes(key)
        ? prev[field].filter((v) => v !== key)
        : [...prev[field], key],
    }));

  return (
    <Shell
      title="User management"
      subtitle="Admin only. Every action here is written to the audit log."
      actions={
        <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : 'Add user'}
        </button>
      }
    >
      <ErrorBanner message={error} />

      {credential && (
        <Card title="Password — shown once" className="mb-4 border-primary/50">
          <p className="text-sm text-slate-300">
            Send this to <span className="font-medium text-white">{credential.email}</span>{' '}
            over a channel they already control. It is not recoverable, and they will be
            asked to change it on first login.
          </p>
          <code className="mt-3 block break-all rounded-lg bg-raised p-3 font-mono text-sm text-white">
            {credential.password}
          </code>
          <button className="btn-secondary mt-3" onClick={() => setCredential(null)}>
            I have saved it
          </button>
        </Card>
      )}

      {showForm && (
        <Card title="Create user" className="mb-4">
          <form onSubmit={createUser} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <label className="label">Email</label>
                <input
                  type="email"
                  className="input-field"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  required
                />
              </div>
              <div>
                <label className="label">Full name</label>
                <input
                  className="input-field"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  required
                />
              </div>
              <div>
                <label className="label">Role</label>
                <select
                  className="input-field"
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                >
                  {ROLES.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <fieldset>
                <legend className="label">Assigned verticals (empty means all)</legend>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(VERTICAL_LABELS).map(([key, label]) => (
                    <Chip
                      key={key}
                      label={label}
                      active={form.assigned_verticals.includes(key)}
                      onClick={() => toggleScope('assigned_verticals', key)}
                    />
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend className="label">Assigned countries (empty means all)</legend>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(COUNTRY_LABELS).map(([key, label]) => (
                    <Chip
                      key={key}
                      label={label}
                      active={form.assigned_countries.includes(key)}
                      onClick={() => toggleScope('assigned_countries', key)}
                    />
                  ))}
                </div>
              </fieldset>
            </div>

            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Creating…' : 'Create user and generate password'}
            </button>
          </form>
        </Card>
      )}

      <Card>
        {!users ? (
          <Skeleton className="h-40 w-full" />
        ) : users.length === 0 ? (
          <EmptyState
            title="No users yet"
            description="Create the two seo_lead accounts so the team can start drafting."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Drafted this week</th>
                  <th>Avg score</th>
                  <th>Last login</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <div className="font-medium text-white">{user.full_name}</div>
                      <div className="text-xs text-muted">{user.email}</div>
                    </td>
                    <td>
                      <span className="badge border-line bg-raised text-slate-200">
                        {user.role}
                      </span>
                    </td>
                    <td className="tabular-nums">{user.articles_drafted_this_week}</td>
                    <td>
                      <ScoreBadge score={user.avg_score} />
                    </td>
                    <td className="whitespace-nowrap text-xs text-muted">
                      {user.last_login_at
                        ? new Date(user.last_login_at).toLocaleString()
                        : 'Never'}
                    </td>
                    <td>
                      <div className="flex flex-col gap-1">
                        <span
                          className={`badge ${
                            user.is_active
                              ? 'border-success/40 bg-success/10 text-success'
                              : 'border-danger/40 bg-danger/10 text-danger'
                          }`}
                        >
                          {user.is_active ? 'active' : 'deactivated'}
                        </span>
                        {user.must_change_password && (
                          <span className="badge border-warning/40 bg-warning/10 text-warning">
                            must change password
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="whitespace-nowrap">
                      <button
                        className="text-xs text-primary hover:underline"
                        onClick={() => resetPassword(user)}
                      >
                        Reset password
                      </button>
                      <span className="mx-2 text-line">|</span>
                      <button
                        className="text-xs text-primary hover:underline"
                        onClick={() => toggleActive(user)}
                      >
                        {user.is_active ? 'Deactivate' : 'Reactivate'}
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

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
        active
          ? 'border-primary bg-primary/15 text-white'
          : 'border-line bg-raised text-muted hover:text-slate-200'
      }`}
    >
      {label}
    </button>
  );
}
