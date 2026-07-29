'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import Shell from '@/components/Shell';
import { Card, EmptyState, ErrorBanner, Skeleton } from '@/components/ui';
import {
  apiError,
  CalendarRow,
  COUNTRY_LABELS,
  seoApi,
  VERTICAL_LABELS,
} from '@/lib/seo';

const WEEKS = Array.from({ length: 12 }, (_, i) => i + 1);

export default function CalendarPage() {
  const [rows, setRows] = useState<CalendarRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [importErrors, setImportErrors] = useState<Record<string, unknown>[]>([]);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setRows(null);
    try {
      const { data } = await seoApi.calendar();
      setRows(data);
      setError(null);
    } catch (err) {
      setError(apiError(err, 'Could not load the calendar.'));
      setRows([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byWeek = useMemo(() => {
    const map = new Map<number | 'unscheduled', CalendarRow[]>();
    (rows ?? []).forEach((row) => {
      const key = row.week_number ?? 'unscheduled';
      map.set(key, [...(map.get(key) ?? []), row]);
    });
    return map;
  }, [rows]);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    setImportErrors([]);
    try {
      const { data } = await seoApi.importCalendar(file, false);
      setNotice(`Imported ${data.imported} rows; skipped ${data.skipped}.`);
      setImportErrors(data.errors ?? []);
      await load();
    } catch (err) {
      setError(apiError(err, 'CSV import failed.'));
    } finally {
      setBusy(false);
    }
  };

  const unscheduled = byWeek.get('unscheduled') ?? [];

  return (
    <Shell
      title="Editorial calendar"
      subtitle="12-week plan. Import the 60-row CSV to populate it."
      actions={
        <>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload(file);
              e.target.value = '';
            }}
          />
          <button
            className="btn-primary"
            onClick={() => fileInput.current?.click()}
            disabled={busy}
          >
            {busy ? 'Importing…' : 'Import CSV'}
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

      {importErrors.length > 0 && (
        <Card title={`${importErrors.length} rows were skipped`} className="mb-4">
          <ul className="space-y-2 text-xs">
            {importErrors.slice(0, 20).map((row, index) => (
              <li key={index} className="rounded-lg bg-raised p-2">
                <span className="font-medium text-warning">Line {String(row.line)}</span>
                <span className="ml-2 text-slate-300">
                  {(row.problems as string[]).join('; ')}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {!rows ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            title="The calendar is empty"
            description="Import a CSV with columns: week, type, vertical, country, title, keyword, kd, volume, intent. Onpage rows need an approved country; content rows must leave it blank."
            action={
              <button className="btn-primary" onClick={() => fileInput.current?.click()}>
                Import CSV
              </button>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {WEEKS.map((week) => {
              const items = byWeek.get(week) ?? [];
              return (
                <div key={week} className="rounded-xl border border-line bg-surface">
                  <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
                    <h2 className="text-sm font-semibold text-white">Week {week}</h2>
                    <span className="text-xs tabular-nums text-muted">{items.length}</span>
                  </header>
                  <div className="space-y-2 p-3">
                    {items.length === 0 ? (
                      <p className="py-4 text-center text-xs text-muted">Nothing planned</p>
                    ) : (
                      items.map((item) => <CalendarCard key={item.id} row={item} />)
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {unscheduled.length > 0 && (
            <Card title="Unscheduled" className="mt-4">
              <div className="grid grid-cols-1 gap-2 md:grid-cols-3 xl:grid-cols-4">
                {unscheduled.map((item) => (
                  <CalendarCard key={item.id} row={item} />
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </Shell>
  );
}

function CalendarCard({ row }: { row: CalendarRow }) {
  return (
    <div className="rounded-lg border border-line bg-raised p-3">
      <div className="flex items-start justify-between gap-2">
        <span
          className={`badge shrink-0 ${
            row.article_type === 'onpage'
              ? 'border-primary/40 bg-primary/10 text-primary'
              : 'border-line bg-surface text-muted'
          }`}
        >
          {row.article_type}
        </span>
        {row.article_id && (
          <Link
            href={`/dashboard/seo/articles/edit/?id=${row.article_id}`}
            className="shrink-0 text-xs text-primary hover:underline"
          >
            open
          </Link>
        )}
      </div>
      <p className="mt-2 text-sm font-medium leading-snug text-white">
        {row.title ?? row.primary_keyword ?? '(untitled)'}
      </p>
      <p className="mt-1 text-xs text-muted">
        {VERTICAL_LABELS[row.vertical]}
        {row.country ? ` · ${COUNTRY_LABELS[row.country]}` : ''}
      </p>
      {(row.kd !== null || row.volume !== null) && (
        <p className="mt-1.5 text-xs tabular-nums text-muted">
          {row.kd !== null && <>KD {row.kd}</>}
          {row.kd !== null && row.volume !== null && ' · '}
          {row.volume !== null && <>{row.volume.toLocaleString()}/mo</>}
        </p>
      )}
    </div>
  );
}
