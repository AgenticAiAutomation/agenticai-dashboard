'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import { apiError } from '@/lib/seo';
import { ErrorBanner } from '@/components/ui';

const RULES = [
  'At least 12 characters',
  'An uppercase letter',
  'A lowercase letter',
  'A number',
  'A symbol',
];

export default function ChangePasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirm) {
      setError('The two new-password fields do not match.');
      return;
    }
    setSaving(true);
    try {
      await api.post('/users/me/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      router.push('/dashboard');
    } catch (err) {
      setError(apiError(err, 'Could not change the password.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-md rounded-xl border border-line bg-surface p-8">
        <h1 className="text-xl font-bold text-white">Set a new password</h1>
        <p className="mt-1 text-sm text-muted">
          Your account was created with a generated password. Choose your own before
          continuing.
        </p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <ErrorBanner message={error} />
          <div>
            <label className="label" htmlFor="current">
              Current password
            </label>
            <input
              id="current"
              type="password"
              autoComplete="current-password"
              className="input-field"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="new">
              New password
            </label>
            <input
              id="new"
              type="password"
              autoComplete="new-password"
              className="input-field"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="confirm">
              Confirm new password
            </label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              className="input-field"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          </div>

          <ul className="space-y-1 text-xs text-muted">
            {RULES.map((rule) => (
              <li key={rule}>• {rule}</li>
            ))}
          </ul>

          <button type="submit" className="btn-primary w-full" disabled={saving}>
            {saving ? 'Saving…' : 'Save password'}
          </button>
        </form>
      </div>
    </div>
  );
}
