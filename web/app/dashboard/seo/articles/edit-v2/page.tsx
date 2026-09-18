'use client';

/* Block editor (Blog Visual Engine v2). Lives beside the markdown editor
   until cutover; writers keep the old one for the whole build.

   Three columns: blocks, live preview (the exact page the publish step
   writes, in an iframe), and the sidebar (validators with jump-to-block,
   counts, revisions, publish). Autosaves five seconds after the last change
   and on Ctrl+S. */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Shell from '@/components/Shell';
import BlockEditor from '@/components/blocks/BlockEditor';
import { ScorePassing, ScorePath } from '@/components/ScorePath';
import { Card, ErrorBanner, Skeleton } from '@/components/ui';
import {
  blocksApi, newBlock, previewSrcdoc,
  type Block, type BlocksReport, type BlocksResponse, type Revision,
} from '@/lib/blocks';
import { apiError, seoApi, type ScoreReport } from '@/lib/seo';

const AUTOSAVE_MS = 5000;
const PREVIEW_MS = 1500;
const LIMITS: Record<string, number> = { gradient_headline: 2, marker_highlight: 4 };

export default function EditV2Page() {
  return (
    <Suspense fallback={<Shell title="Block editor"><Skeleton /></Shell>}>
      <EditV2 />
    </Suspense>
  );
}

function EditV2() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get('id') || '';

  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [doc, setDoc] = useState<BlocksResponse | null>(null);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [meta, setMeta] = useState({ title: '', slug: '', meta_title: '', meta_description: '', primary_keyword: '' });
  const [version, setVersion] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [report, setReport] = useState<BlocksReport | null>(null);
  const [revision, setRevision] = useState(0);
  const [revisions, setRevisions] = useState<Revision[] | null>(null);
  const [preview, setPreview] = useState<string>('');
  const [previewMode, setPreviewMode] = useState<'desktop' | 'mobile' | 'off'>('desktop');
  const [focusBlockId, setFocusBlockId] = useState<string | null>(null);
  const [score, setScore] = useState<ScoreReport | null>(null);
  const [scoring, setScoring] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishIssues, setPublishIssues] = useState<string[] | null>(null);
  const [overrideReason, setOverrideReason] = useState('');
  const [publishMsg, setPublishMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const saveTimer = useRef<number | null>(null);
  const previewTimer = useRef<number | null>(null);
  const latest = useRef({ blocks, meta });
  latest.current = { blocks, meta };

  /* ---- load ---- */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data: status } = await blocksApi.status();
        if (cancelled) return;
        setEnabled(status.enabled);
        if (!status.enabled || !id) return;
        const { data } = await blocksApi.get(id);
        if (cancelled) return;
        setDoc(data);
        setBlocks(data.blocks.length ? data.blocks : [newBlock('key_takeaways'), newBlock('paragraph')]);
        setMeta({ title: data.title || '', slug: data.slug || '', meta_title: data.meta_title || '', meta_description: data.meta_description || '', primary_keyword: data.primary_keyword || '' });
        setReport(data.report);
        setRevision(data.revision_number);
        setVersion((v) => v + 1);
      } catch (e) {
        if (!cancelled) setError(apiError(e));
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  const readOnly = !doc?.can_edit;

  /* ---- save ---- */
  const save = useCallback(async (note?: string) => {
    if (!id || readOnly) return;
    const { blocks: b, meta: m } = latest.current;
    setSaveState('saving'); setSaveError(null);
    try {
      const { data } = await blocksApi.save(id, { blocks: b, ...m, note });
      setReport(data.report);
      setRevision(data.revision_number);
      setDirty(false);
      setSaveState('saved');
      if (data.changed) setRevisions(null); // refetch lazily
    } catch (e: any) {
      setSaveState('error');
      const d = e?.response?.data?.detail;
      if (d?.error === 'invalid_block') {
        setSaveError(`Block ${d.block_id || ''}: ${d.message}`);
        if (d.block_id) setFocusBlockId(d.block_id);
      } else {
        setSaveError(apiError(e));
      }
    }
  }, [id, readOnly]);

  const touch = useCallback(() => {
    setDirty(true);
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => save(), AUTOSAVE_MS);
    if (previewTimer.current) window.clearTimeout(previewTimer.current);
    previewTimer.current = window.setTimeout(refreshPreview, PREVIEW_MS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [save]);

  const onBlocks = (b: Block[]) => { setBlocks(b); touch(); };
  const onMeta = (patch: Partial<typeof meta>) => { setMeta((m) => ({ ...m, ...patch })); touch(); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); } };
    const onLeave = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('keydown', onKey); window.addEventListener('beforeunload', onLeave);
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('beforeunload', onLeave); };
  }, [save, dirty]);

  /* ---- preview ---- */
  const refreshPreview = useCallback(async () => {
    if (!id || previewMode === 'off') return;
    const { blocks: b, meta: m } = latest.current;
    try {
      const { data } = await blocksApi.preview(id, { blocks: b, ...m });
      setPreview(previewSrcdoc(data.html));
      setReport(data.report);
    } catch { /* a preview failure is not worth a banner; the save will report it */ }
  }, [id, previewMode]);

  useEffect(() => { if (doc) refreshPreview(); }, [doc, previewMode, refreshPreview]);

  /* ---- revisions ---- */
  const loadRevisions = async () => { try { const { data } = await blocksApi.revisions(id); setRevisions(data); } catch (e) { setError(apiError(e)); } };
  const restore = async (n: number) => {
    if (!confirm(`Restore revision ${n}? The current content is kept as a new revision.`)) return;
    try {
      const { data } = await blocksApi.restore(id, n);
      const { data: fresh } = await blocksApi.get(id);
      setBlocks(fresh.blocks); setMeta({ title: fresh.title || '', slug: fresh.slug || '', meta_title: fresh.meta_title || '', meta_description: fresh.meta_description || '', primary_keyword: fresh.primary_keyword || '' });
      setReport(data.report); setRevision(data.revision_number); setDirty(false); setVersion((v) => v + 1); setRevisions(null);
      refreshPreview();
    } catch (e) { setError(apiError(e)); }
  };

  /* ---- score (existing 27-parameter engine on the markdown projection) ---- */
  const runScore = async () => {
    setScoring(true);
    try { await save(); const { data } = await seoApi.score(id); setScore(data); } catch (e) { setError(apiError(e)); } finally { setScoring(false); }
  };

  /* ---- publish ---- */
  const publish = async (reason?: string) => {
    setPublishing(true); setPublishMsg(null); setPublishIssues(null);
    try {
      await save();
      const { data } = await blocksApi.publish(id, reason);
      setPublishMsg(data.message + (data.overridden.length ? ` Overrode: ${data.overridden.join('; ')}` : ''));
      setOverrideReason('');
      const { data: fresh } = await blocksApi.get(id); setDoc(fresh);
    } catch (e: any) {
      const d = e?.response?.data?.detail;
      if (d?.error === 'validators_blocking') setPublishIssues(d.issues);
      else setPublishMsg(d?.message || apiError(e));
    } finally { setPublishing(false); }
  };

  const effects = report?.effects || {};
  const blockingCount = report?.blocking ?? 0;

  if (enabled === false) {
    return (
      <Shell title="Block editor" subtitle="Not enabled on this server.">
        <Card><p className="text-sm text-muted">BLOG_ENGINE_V2 is off on the API. The markdown editor is unaffected: <Link className="text-primary" href={`/dashboard/seo/articles/write/?id=${id}`}>open it here</Link>.</p></Card>
      </Shell>
    );
  }
  if (!doc) return <Shell title="Block editor"><ErrorBanner message={error} /><Skeleton /></Shell>;

  return (
    <Shell
      title={meta.title || 'Untitled article'}
      subtitle={`Block editor · ${doc.status.replace(/_/g, ' ')} · revision ${revision}${readOnly ? ' · read only' : ''}`}
      actions={
        <div className="flex items-center gap-2">
          <span className={`text-xs ${saveState === 'error' ? 'text-danger' : dirty ? 'text-warning' : 'text-muted'}`} aria-live="polite">
            {saveState === 'saving' ? 'Saving…' : saveState === 'error' ? 'Not saved' : dirty ? 'Unsaved changes' : saveState === 'saved' ? 'Saved' : ''}
          </span>
          {!readOnly && <button type="button" className="btn-secondary" onClick={() => save()} disabled={saveState === 'saving'}>Save</button>}
          <Link href={`/dashboard/seo/articles/write/?id=${id}`} className="btn-secondary">Markdown editor</Link>
          <Link href="/dashboard/seo/articles" className="btn-secondary">Articles</Link>
        </div>
      }
    >
      <ErrorBanner message={error} />
      {saveError && <p className="mb-3 rounded border border-danger/40 bg-danger/10 p-2 text-xs text-danger">{saveError}</p>}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_300px]">
        {/* ---------------- editor column ---------------- */}
        <div className="space-y-4">
          <Card title="Article">
            <div className="grid gap-2">
              <input className="input-field text-lg font-semibold" placeholder="Title (this is the H1)" value={meta.title} readOnly={readOnly} aria-label="Title" onChange={(e) => onMeta({ title: e.target.value })} />
              <div className="grid gap-2 sm:grid-cols-2">
                <div>
                  <input className="input-field font-mono text-xs" placeholder="url-slug" value={meta.slug} readOnly={readOnly || doc.status === 'published'} aria-label="Slug" onChange={(e) => onMeta({ slug: e.target.value })} />
                  {doc.status === 'published' && <p className="mt-1 text-[11px] text-muted">URL is locked while published.</p>}
                </div>
                <input className="input-field text-sm" placeholder="Primary keyword" value={meta.primary_keyword} readOnly={readOnly} aria-label="Primary keyword" onChange={(e) => onMeta({ primary_keyword: e.target.value })} />
              </div>
              <input className="input-field text-sm" placeholder="Meta title (≤60 characters)" value={meta.meta_title} readOnly={readOnly} aria-label="Meta title" onChange={(e) => onMeta({ meta_title: e.target.value })} />
              <div>
                <textarea className="input-field text-sm" rows={2} placeholder="Meta description (140–160 characters)" value={meta.meta_description} readOnly={readOnly} aria-label="Meta description" onChange={(e) => onMeta({ meta_description: e.target.value })} />
                <p className={`mt-1 text-[11px] ${meta.meta_description.length >= 140 && meta.meta_description.length <= 160 ? 'text-success' : 'text-muted'}`}>{meta.meta_description.length}/160 · meta title {meta.meta_title.length}/60</p>
              </div>
            </div>
          </Card>

          <BlockEditor blocks={blocks} onChange={onBlocks} readOnly={readOnly} version={version}
            violations={report?.violations || []} focusBlockId={focusBlockId} onFocusHandled={() => setFocusBlockId(null)} />
        </div>

        {/* ---------------- preview column ---------------- */}
        <div className="space-y-2 xl:sticky xl:top-4 xl:self-start">
          <div className="flex items-center justify-between">
            <p className="card-title">Preview · exact public page</p>
            <div className="flex gap-1" role="group" aria-label="Preview width">
              {(['desktop', 'mobile', 'off'] as const).map((m) => (
                <button key={m} type="button" onClick={() => setPreviewMode(m)} aria-pressed={previewMode === m}
                  className={`rounded border px-2 py-0.5 text-[11px] ${previewMode === m ? 'border-primary text-primary' : 'border-line text-muted'}`}>{m}</button>
              ))}
            </div>
          </div>
          {previewMode !== 'off' && (
            <div className="overflow-hidden rounded-lg border border-line bg-black" style={{ height: 'calc(100vh - 140px)' }}>
              <iframe title="Article preview" srcDoc={preview} sandbox="allow-same-origin"
                className="mx-auto block h-full bg-[#0a0908]" style={{ width: previewMode === 'mobile' ? 375 : '100%' }} />
            </div>
          )}
        </div>

        {/* ---------------- sidebar ---------------- */}
        <div className="space-y-4">
          <Card title="Publish">
            {doc.can_publish ? (
              <>
                <button type="button" className="btn-primary w-full" disabled={publishing || readOnly} onClick={() => publish()}>
                  {publishing ? 'Publishing…' : doc.status === 'published' ? 'Republish' : 'Publish'}
                </button>
                {publishIssues && (
                  <div className="mt-3 rounded border border-danger/40 bg-danger/10 p-2 text-xs">
                    <p className="mb-1 font-semibold text-danger">{publishIssues.length} validator(s) block publishing:</p>
                    <ul className="mb-2 space-y-0.5 text-danger">{publishIssues.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                    <textarea className="input-field text-xs" rows={2} placeholder="Override reason (logged to the audit trail; at least 10 characters)" value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} aria-label="Override reason" />
                    <button type="button" className="btn-secondary mt-2 w-full text-xs" disabled={overrideReason.trim().length < 10 || publishing} onClick={() => publish(overrideReason.trim())}>Publish anyway (override)</button>
                  </div>
                )}
              </>
            ) : <p className="text-xs text-muted">Publishing is an admin action. Save and let Jai know it is ready.</p>}
            {publishMsg && <p className="mt-2 text-xs text-slate-300">{publishMsg}</p>}
            {doc.status === 'published' && doc.slug && <a className="mt-2 block text-xs text-primary" href={`https://agenticaiautomation.co/blog/${doc.slug}`} target="_blank" rel="noopener">View live ↗</a>}
          </Card>

          <Card title={`Checks · ${blockingCount ? `${blockingCount} blocking` : 'none blocking'}`}>
            {report ? (
              <>
                <dl className="mb-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <Stat n={report.word_count} l="words" />
                  <Stat n={report.visuals} l="visuals" ok={report.word_count < 400 || report.visuals >= Math.floor(report.word_count / 400)} />
                  <Stat n={report.reading_minutes} l="min read" />
                </dl>
                <ul className="mb-3 space-y-1 text-[11px]">
                  {Object.entries(LIMITS).map(([k, lim]) => (
                    <li key={k} className={`flex justify-between ${(effects[k] || 0) > lim ? 'text-warning' : 'text-muted'}`}><span>{k.replace('_', ' ')}</span><span>{effects[k] || 0} / {lim}</span></li>
                  ))}
                  <li className="flex justify-between text-muted"><span>lead paragraphs</span><span>{effects.lead_paragraph || 0}</span></li>
                  <li className="flex justify-between text-muted"><span>breakouts</span><span>{effects.breakout || 0}</span></li>
                </ul>
                {report.violations.length ? (
                  <ul className="space-y-1.5">
                    {report.violations.map((v, i) => (
                      <li key={i} className="text-xs">
                        <button type="button" disabled={!v.block_id} onClick={() => v.block_id && setFocusBlockId(v.block_id)}
                          className={`text-left ${v.level === 'block' ? 'text-danger' : 'text-warning'} ${v.block_id ? 'hover:underline' : 'cursor-default'}`}>
                          {v.level === 'block' ? '⛔' : '⚠'} {v.message}{v.block_id ? ' ↗' : ''}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-xs text-success">Every check passes.</p>}
              </>
            ) : <p className="text-xs text-muted">Save to see the checks.</p>}
          </Card>

          <Card title="SEO score">
            <button type="button" className="btn-secondary w-full text-xs" disabled={scoring || readOnly} onClick={runScore}>{scoring ? 'Scoring…' : 'Save & score (27 checks + Rank Math)'}</button>
            {score && (
              <div className="mt-3 space-y-3">
                <p className="text-sm"><span className="text-2xl font-semibold tabular-nums">{score.total_score}</span><span className="text-muted"> / 100 · publish needs 80</span></p>
                {score.path_to_threshold && <ScorePath path={score.path_to_threshold} />}
                <ScorePassing passing={score.passing} rankMathTests={score.rank_math?.tests} />
              </div>
            )}
          </Card>

          <Card title={`Revisions · ${revision}`}>
            {revisions === null
              ? <button type="button" className="btn-secondary w-full text-xs" onClick={loadRevisions}>Show history</button>
              : revisions.length ? (
                <ul className="max-h-64 space-y-1 overflow-y-auto text-xs">
                  {revisions.map((r) => (
                    <li key={r.revision_number} className="flex items-center justify-between gap-2 border-b border-line py-1">
                      <span className="text-slate-300">#{r.revision_number} <span className="text-muted">{r.created_at ? new Date(r.created_at).toLocaleString() : ''} · {r.created_by || '—'}{r.note ? ` · ${r.note}` : ''}</span></span>
                      {!readOnly && r.revision_number !== revision && <button type="button" className="text-primary hover:underline" onClick={() => restore(r.revision_number)}>restore</button>}
                    </li>
                  ))}
                </ul>
              ) : <p className="text-xs text-muted">No revisions yet.</p>}
          </Card>

          {report?.headings?.length ? (
            <Card title="Outline">
              <ol className="space-y-0.5 text-xs">
                {report.headings.map(([lvl, text], i) => <li key={i} className="text-slate-300" style={{ paddingLeft: (lvl - 2) * 12 }}>H{lvl} {text}</li>)}
              </ol>
            </Card>
          ) : null}
        </div>
      </div>
    </Shell>
  );
}

function Stat({ n, l, ok }: { n: number; l: string; ok?: boolean }) {
  return (
    <div className="rounded bg-raised p-2">
      <dt className="text-[10px] uppercase tracking-wide text-muted">{l}</dt>
      <dd className={`text-lg font-semibold tabular-nums ${ok === false ? 'text-warning' : 'text-slate-100'}`}>{n}</dd>
    </div>
  );
}
