'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, ScoreBadge, Skeleton } from '@/components/ui';
import { apiError, seoApi, TeamMember } from '@/lib/seo';

export default function TeamPage() {
  const [team, setTeam] = useState<TeamMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    seoApi
      .teamStats()
      .then((response) => setTeam(response.data))
      .catch((err) => {
        setError(apiError(err, 'Could not load the scoreboard.'));
        setTeam([]);
      });
  }, []);

  return (
    <Shell
      title="Team scoreboard"
      subtitle="Throughput and quality per SEO team member, this week."
    >
      <ErrorBanner message={error} />

      {!team ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : team.length === 0 ? (
        <Card>
          <EmptyState
            title="No SEO team members yet"
            description="Create accounts with the seo_lead role and their work will appear here automatically."
            action={
              <Link href="/settings/users" className="btn-primary">
                Manage users
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {team.map((member) => (
            <Card key={member.user_id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate text-base font-semibold text-white">
                    {member.full_name}
                  </h2>
                  <p className="truncate text-xs text-muted">{member.email}</p>
                </div>
                <span className="badge shrink-0 border-line bg-raised text-muted">
                  {member.role}
                </span>
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-4">
                <Stat label="Articles this week" value={member.articles_this_week} />
                <Stat label="Published all-time" value={member.articles_published} />
                <Stat label="Backlinks earned" value={member.backlinks_earned} />
                <div>
                  <dt className="text-label uppercase text-muted">Avg score</dt>
                  <dd className="mt-1">
                    <ScoreBadge score={member.avg_score} />
                  </dd>
                </div>
              </dl>

              <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-xs">
                <span className="text-muted">
                  Streak <span className="tabular-nums text-slate-200">
                    {member.streak_days}d
                  </span>
                </span>
                <span className="text-muted">
                  {member.last_login_at
                    ? `Last seen ${new Date(member.last_login_at).toLocaleDateString()}`
                    : 'Never logged in'}
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}
    </Shell>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-label uppercase text-muted">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-white">{value}</dd>
    </div>
  );
}
