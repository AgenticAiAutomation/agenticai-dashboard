'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import Shell from '@/components/Shell';
import {
  Card,
  CardSkeleton,
  EmptyState,
  ErrorBanner,
  KpiCard,
  ProjectionCard,
  ScoreBadge,
  Skeleton,
} from '@/components/ui';
import { apiError, DashboardHome, seoApi } from '@/lib/seo';

const AXIS = { stroke: '#64748B', fontSize: 11 };
const GRID = '#243044';

const TOOLTIP_STYLE = {
  backgroundColor: '#111827',
  border: '1px solid #243044',
  borderRadius: 8,
  fontSize: 12,
  color: '#E2E8F0',
};

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

const relative = (iso: string) => {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
};

export default function DashboardPage() {
  const [data, setData] = useState<DashboardHome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const response = await seoApi.dashboardHome();
      setData(response.data);
      setError(null);
    } catch (err) {
      setError(apiError(err, 'Could not load the dashboard.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Shell
      title="Dashboard"
      subtitle="Publishing velocity, authority growth, and what the team is doing right now."
      actions={
        <Link href="/dashboard/seo/articles/new" className="btn-primary">
          New article
        </Link>
      }
    >
      <ErrorBanner message={error} />

      {data && !data.go_live_approved && (
        <div className="mb-6 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          <strong className="font-semibold">Publishing is in draft-only mode.</strong>{' '}
          {data.go_live_message}
        </div>
      )}

      {/* Row 1 — KPI cards */}
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} lines={1} />)
          : data?.kpis.map((kpi) => (
              <KpiCard
                key={kpi.key}
                label={kpi.label}
                value={kpi.value}
                unit={kpi.unit}
                delta={kpi.delta}
                deltaLabel={kpi.delta_label}
                direction={kpi.direction}
                target={kpi.target}
                percentOfTarget={kpi.percent_of_target}
                healthy={kpi.healthy}
              />
            ))}
      </div>

      {/* Row 2 — target-reach projections */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {loading
          ? Array.from({ length: 3 }).map((_, i) => <CardSkeleton key={i} lines={2} />)
          : data?.projections.map((projection) => (
              <ProjectionCard
                key={projection.label}
                label={projection.label}
                currentValue={projection.current_value}
                targetValue={projection.target_value}
                projectedDate={projection.projected_date}
                confidenceDays={projection.confidence_days}
                status={projection.status}
                message={projection.message}
              />
            ))}
      </div>

      {/* Row 3 — charts */}
      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card
          title="30-day publish velocity"
          action={
            data ? (
              <span className="text-xs text-muted">
                weekly avg {data.publish_velocity_weekly_avg}
              </span>
            ) : null
          }
        >
          {loading ? (
            <Skeleton className="h-56 w-full" />
          ) : !data?.publish_velocity.length ? (
            <EmptyState
              title="No publishing history yet"
              description="This chart fills in as articles go live."
            />
          ) : (
            <ResponsiveContainer width="100%" height={224}>
              <BarChart data={data.publish_velocity}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} tickLine={false} />
                <YAxis allowDecimals={false} {...AXIS} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  labelFormatter={(v) => shortDate(String(v))}
                  formatter={(v: number) => [v, 'articles']}
                />
                <ReferenceLine
                  y={data.publish_velocity_weekly_avg / 7}
                  stroke="#2563EB"
                  strokeDasharray="4 4"
                />
                <Bar dataKey="value" fill="#2563EB" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="90-day Search Console: clicks and impressions">
          {loading ? (
            <Skeleton className="h-56 w-full" />
          ) : !data?.gsc_series.length ? (
            <EmptyState
              title="No Search Console data yet"
              description="Wire the GSC service account and run the daily audit cron to populate this."
            />
          ) : (
            <ResponsiveContainer width="100%" height={224}>
              <LineChart data={data.gsc_series}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} {...AXIS} tickLine={false} />
                <YAxis yAxisId="clicks" {...AXIS} tickLine={false} axisLine={false} />
                <YAxis
                  yAxisId="impressions"
                  orientation="right"
                  {...AXIS}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  labelFormatter={(v) => shortDate(String(v))}
                />
                <Line
                  yAxisId="clicks"
                  type="monotone"
                  dataKey="value"
                  name="Clicks"
                  stroke="#2563EB"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="impressions"
                  type="monotone"
                  dataKey="secondary"
                  name="Impressions"
                  stroke="#94A3B8"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Row 4 — team + recommendations */}
      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card
          title="Team scoreboard"
          action={
            <Link href="/dashboard/seo/team" className="text-xs text-primary hover:underline">
              Full scoreboard
            </Link>
          }
        >
          {loading ? (
            <Skeleton className="h-40 w-full" />
          ) : !data?.team.length ? (
            <EmptyState
              title="No SEO team members yet"
              description="Create seo_lead accounts under Users so their work shows up here."
              action={
                <Link href="/settings/users" className="btn-secondary">
                  Manage users
                </Link>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Member</th>
                    <th>This week</th>
                    <th>Published</th>
                    <th>Avg score</th>
                    <th>Streak</th>
                  </tr>
                </thead>
                <tbody>
                  {data.team.map((member) => (
                    <tr key={member.user_id}>
                      <td>
                        <div className="font-medium text-white">{member.full_name}</div>
                        <div className="text-xs text-muted">{member.role}</div>
                      </td>
                      <td className="tabular-nums">{member.articles_this_week}</td>
                      <td className="tabular-nums">{member.articles_published}</td>
                      <td>
                        <ScoreBadge score={member.avg_score} />
                      </td>
                      <td className="tabular-nums">{member.streak_days}d</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          title="Top recommendations"
          action={
            <Link
              href="/dashboard/seo/recommendations"
              className="text-xs text-primary hover:underline"
            >
              All recommendations
            </Link>
          }
        >
          {loading ? (
            <Skeleton className="h-40 w-full" />
          ) : !data?.recommendations.length ? (
            <EmptyState
              title="Nothing needs attention"
              description="The daily audit cron writes recommendations here when it finds an issue."
            />
          ) : (
            <ul className="space-y-3">
              {data.recommendations.map((rec) => (
                <li key={rec.id} className="rounded-lg border border-line bg-raised p-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-medium text-white">{rec.title}</p>
                    <span
                      className={`badge shrink-0 ${
                        rec.priority === 'high'
                          ? 'border-danger/40 bg-danger/10 text-danger'
                          : rec.priority === 'medium'
                          ? 'border-warning/40 bg-warning/10 text-warning'
                          : 'border-line bg-surface text-muted'
                      }`}
                    >
                      {rec.priority}
                    </span>
                  </div>
                  {rec.action_required && (
                    <p className="mt-1.5 text-xs text-muted">{rec.action_required}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Row 5 — activity feed */}
      <Card title="Recent activity">
        {loading ? (
          <Skeleton className="h-32 w-full" />
        ) : !data?.activity.length ? (
          <EmptyState
            title="No activity recorded yet"
            description="Every login, edit, and publish is written to the audit log and appears here."
          />
        ) : (
          <ul className="divide-y divide-line/60">
            {data.activity.map((entry) => (
              <li key={entry.id} className="flex items-baseline gap-3 py-2 text-sm">
                <span className="w-20 shrink-0 text-xs tabular-nums text-muted">
                  {relative(entry.created_at)}
                </span>
                <span className="w-56 shrink-0 truncate text-slate-300">
                  {entry.user_email ?? 'system'}
                </span>
                <span className="font-mono text-xs text-primary">{entry.action}</span>
                {entry.detail && (
                  <span className="truncate text-xs text-muted">{entry.detail}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Shell>
  );
}
