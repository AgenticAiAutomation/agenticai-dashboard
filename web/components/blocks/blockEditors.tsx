'use client';

/* Per-type block editors. Each takes the block and returns a changed copy via
   onChange. They never touch HTML — every text field is either a RichText
   (runs with marks) or a plain string the server escapes on render. */

import { useRef, useState } from 'react';
import RichText, { type Segment } from './RichText';
import { blocksApi, type Block, type ImageAttrs, type RichText as Runs } from '@/lib/blocks';

interface Props {
  block: Block;
  onChange: (b: Block) => void;
  version: number;
  readOnly: boolean;
  onSplit?: (before: Runs, after: Runs) => void;
  onDeleteEmpty?: () => void;
  onPasteBlocks?: (segs: Segment[]) => void;
  onSlash?: () => void;
  autoFocus?: boolean;
}

const set = (b: Block, attrs: Record<string, any>) => ({ ...b, attrs: { ...(b.attrs || {}), ...attrs } });
const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(' ');

/* ---------- small controls ---------- */
export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted">{hint}</span>}
    </label>
  );
}
const Text = (p: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input {...p} className={cx('input-field py-1.5 text-sm', p.className)} />
);
const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <select {...p} className={cx('input-field py-1.5 text-sm', p.className)} />
);
const Small = ({ children, onClick, danger, label }: { children: React.ReactNode; onClick: () => void; danger?: boolean; label?: string }) => (
  <button type="button" onClick={onClick} aria-label={label}
    className={cx('rounded border px-2 py-0.5 text-[11px]', danger ? 'border-danger/40 text-danger hover:bg-danger/10' : 'border-line text-slate-300 hover:bg-raised')}>
    {children}
  </button>
);

/* ---------- image picker ---------- */
export function ImageFields({ value, onChange, readOnly, compact }: {
  value: ImageAttrs; onChange: (v: ImageAttrs) => void; readOnly: boolean; compact?: boolean;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const upload = async (file: File) => {
    setBusy(true); setErr(null);
    try {
      const { data } = await blocksApi.upload(file);
      onChange({ ...value, src: data.src, width: data.width, height: data.height });
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Upload failed');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid gap-2">
      <div className="flex items-start gap-3">
        <div className="h-20 w-32 flex-none overflow-hidden rounded border border-line bg-raised">
          {value.src ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={value.src.startsWith('/') ? `https://agenticaiautomation.co${value.src}` : value.src} alt="" className="h-full w-full object-cover" />
          ) : <div className="grid h-full place-items-center text-[11px] text-muted">no image</div>}
        </div>
        <div className="flex-1 space-y-1.5">
          <div className="flex gap-2">
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ''; }} />
            <button type="button" className="btn-secondary px-3 py-1 text-xs" disabled={readOnly || busy} onClick={() => fileRef.current?.click()}>
              {busy ? 'Uploading…' : value.src ? 'Replace image' : 'Upload image'}
            </button>
            {value.src && <span className="self-center text-[11px] text-muted">{value.width}×{value.height}</span>}
          </div>
          {err && <p className="text-xs text-danger">{err}</p>}
          <Text placeholder="Alt text — say what is in the picture (required)" value={value.alt} readOnly={readOnly}
            onChange={(e) => onChange({ ...value, alt: e.target.value })} aria-label="Alt text" maxLength={125} />
          <p className="text-[11px] text-muted">{value.alt.length}/125 · not the filename, not “image of”</p>
        </div>
      </div>
      {!compact && (
        <div className="grid grid-cols-2 gap-2">
          <Text placeholder="Caption (optional)" value={value.caption || ''} readOnly={readOnly} aria-label="Caption"
            onChange={(e) => onChange({ ...value, caption: e.target.value || null })} />
          <Text placeholder="Credit (optional)" value={value.credit || ''} readOnly={readOnly} aria-label="Credit"
            onChange={(e) => onChange({ ...value, credit: e.target.value || null })} />
          <Select value={value.layout || 'inset'} disabled={readOnly} aria-label="Layout"
            onChange={(e) => onChange({ ...value, layout: e.target.value as ImageAttrs['layout'] })}>
            <option value="inset">Inset (text width)</option>
            <option value="breakout">Breakout (wider than text)</option>
            <option value="full">Full width</option>
          </Select>
          <Text placeholder="Link (optional)" value={value.link || ''} readOnly={readOnly} aria-label="Link"
            onChange={(e) => onChange({ ...value, link: e.target.value || null })} />
        </div>
      )}
    </div>
  );
}

/* ---------- editors ---------- */
function Paragraph(p: Props) {
  const lead = p.block.attrs?.variant === 'lead';
  return (
    <div>
      <RichText value={p.block.content} version={p.version} readOnly={p.readOnly} autoFocus={p.autoFocus}
        placeholder="Type, or press / for a block" className={cx('text-[15px] leading-relaxed', lead && 'text-[17px]')}
        onChange={(runs) => p.onChange({ ...p.block, content: runs })}
        onSplit={p.onSplit} onDeleteEmpty={p.onDeleteEmpty} onPasteBlocks={p.onPasteBlocks} onSlash={p.onSlash} />
      <label className="mt-1 inline-flex items-center gap-1.5 text-[11px] text-muted">
        <input type="checkbox" checked={lead} disabled={p.readOnly} onChange={(e) => p.onChange(set(p.block, { variant: e.target.checked ? 'lead' : 'normal' }))} />
        Lead paragraph (larger; one per section)
      </label>
    </div>
  );
}

function Heading(p: Props) {
  const level = p.block.attrs?.level || 2;
  const sizes: Record<number, string> = { 2: 'text-xl font-bold', 3: 'text-lg font-semibold', 4: 'text-base font-semibold' };
  return (
    <div className="flex items-start gap-2">
      <Select value={level} disabled={p.readOnly} aria-label="Heading level" className="w-16 flex-none"
        onChange={(e) => p.onChange(set(p.block, { level: Number(e.target.value), gradient: Number(e.target.value) === 2 ? p.block.attrs?.gradient : false }))}>
        <option value={2}>H2</option><option value={3}>H3</option><option value={4}>H4</option>
      </Select>
      <div className="flex-1">
        <RichText value={p.block.content} version={p.version} readOnly={p.readOnly} singleLine autoFocus={p.autoFocus}
          placeholder="Section heading" className={sizes[level]} onChange={(runs) => p.onChange({ ...p.block, content: runs })}
          onDeleteEmpty={p.onDeleteEmpty} />
        {level === 2 && (
          <label className="mt-1 inline-flex items-center gap-1.5 text-[11px] text-muted">
            <input type="checkbox" checked={!!p.block.attrs?.gradient} disabled={p.readOnly} onChange={(e) => p.onChange(set(p.block, { gradient: e.target.checked }))} />
            Gradient headline (max 2 per article)
          </label>
        )}
      </div>
    </div>
  );
}

function KeyTakeaways(p: Props) {
  const items: Runs[] = p.block.content || [];
  const update = (i: number, runs: Runs) => p.onChange({ ...p.block, content: items.map((x, j) => (j === i ? runs : x)) });
  return (
    <div className="rounded border-l-2 border-warning/60 pl-3">
      <Text value={p.block.attrs?.title || ''} readOnly={p.readOnly} aria-label="Title" className="mb-2 font-mono text-xs uppercase tracking-wider"
        onChange={(e) => p.onChange(set(p.block, { title: e.target.value }))} />
      <ul className="space-y-1.5">
        {items.map((runs, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="mt-1.5 h-1.5 w-1.5 flex-none rounded-full bg-warning" />
            <div className="flex-1"><RichText value={runs} version={p.version} readOnly={p.readOnly} placeholder={`Takeaway ${i + 1}`} onChange={(r) => update(i, r)} /></div>
            {!p.readOnly && items.length > 3 && <Small danger label="Remove takeaway" onClick={() => p.onChange({ ...p.block, content: items.filter((_, j) => j !== i) })}>×</Small>}
          </li>
        ))}
      </ul>
      {!p.readOnly && items.length < 5 && <div className="mt-2"><Small onClick={() => p.onChange({ ...p.block, content: [...items, [{ text: '' }]] })}>+ takeaway</Small></div>}
    </div>
  );
}

function ListBlock(p: Props) {
  const items: { content: Runs; checked?: boolean }[] = p.block.content || [];
  const style = p.block.attrs?.style || 'bullet';
  const update = (i: number, patch: Partial<{ content: Runs; checked: boolean }>) =>
    p.onChange({ ...p.block, content: items.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  return (
    <div>
      <Select value={style} disabled={p.readOnly} aria-label="List style" className="mb-2 w-40"
        onChange={(e) => p.onChange(set(p.block, { style: e.target.value }))}>
        <option value="bullet">Bullets</option><option value="numbered">Numbered</option><option value="checklist">Checklist</option>
      </Select>
      <ol className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-2">
            {style === 'checklist'
              ? <input type="checkbox" className="mt-1.5" checked={!!it.checked} disabled={p.readOnly} onChange={(e) => update(i, { checked: e.target.checked })} aria-label="Done" />
              : <span className="mt-0.5 w-5 flex-none text-right font-mono text-xs text-muted">{style === 'numbered' ? `${i + 1}.` : '•'}</span>}
            <div className="flex-1">
              <RichText value={it.content} version={p.version} readOnly={p.readOnly} placeholder="Item" onChange={(r) => update(i, { content: r })}
                onSplit={(before, after) => p.onChange({ ...p.block, content: [...items.slice(0, i), { ...it, content: before }, { content: after.length ? after : [{ text: '' }], checked: false }, ...items.slice(i + 1)] })}
                onDeleteEmpty={items.length > 1 ? () => p.onChange({ ...p.block, content: items.filter((_, j) => j !== i) }) : undefined} />
            </div>
          </li>
        ))}
      </ol>
      {!p.readOnly && <div className="mt-2"><Small onClick={() => p.onChange({ ...p.block, content: [...items, { content: [{ text: '' }], checked: false }] })}>+ item</Small></div>}
    </div>
  );
}

function Steps(p: Props) {
  const steps: { title: Runs; body: Runs; image?: ImageAttrs | null }[] = p.block.content || [];
  const update = (i: number, patch: any) => p.onChange({ ...p.block, content: steps.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  return (
    <div>
      <div className="mb-2 grid grid-cols-2 gap-2">
        <Text placeholder="Title (optional)" value={p.block.attrs?.title || ''} readOnly={p.readOnly} aria-label="Steps title" onChange={(e) => p.onChange(set(p.block, { title: e.target.value || null }))} />
        <Text placeholder="Total time, e.g. PT45M (optional)" value={p.block.attrs?.total_time || ''} readOnly={p.readOnly} aria-label="Total time" onChange={(e) => p.onChange(set(p.block, { total_time: e.target.value || null }))} />
      </div>
      <ol className="space-y-3">
        {steps.map((s, i) => (
          <li key={i} className="grid grid-cols-[auto_1fr] gap-3 rounded border border-line p-2">
            <span className="text-2xl font-bold text-primary">{i + 1}</span>
            <div className="space-y-1.5">
              <RichText value={s.title} version={p.version} readOnly={p.readOnly} singleLine placeholder="Step title" className="font-semibold" onChange={(r) => update(i, { title: r })} />
              <RichText value={s.body} version={p.version} readOnly={p.readOnly} placeholder="What to do (optional)" className="text-sm" onChange={(r) => update(i, { body: r })} />
              {s.image
                ? <div className="pt-1"><ImageFields value={s.image} readOnly={p.readOnly} compact onChange={(v) => update(i, { image: v })} />{!p.readOnly && <div className="mt-1"><Small onClick={() => update(i, { image: null })}>remove image</Small></div>}</div>
                : !p.readOnly && <Small onClick={() => update(i, { image: { src: '', alt: '', width: 1600, height: 900, layout: 'inset' } })}>+ image</Small>}
              {!p.readOnly && steps.length > 2 && <div><Small danger onClick={() => p.onChange({ ...p.block, content: steps.filter((_, j) => j !== i) })}>remove step</Small></div>}
            </div>
          </li>
        ))}
      </ol>
      {!p.readOnly && <div className="mt-2"><Small onClick={() => p.onChange({ ...p.block, content: [...steps, { title: [{ text: '' }], body: [] }] })}>+ step</Small></div>}
      <p className="mt-1 text-[11px] text-muted">3 or more steps produce HowTo structured data.</p>
    </div>
  );
}

function Image(p: Props) {
  return <ImageFields value={p.block.attrs as ImageAttrs} readOnly={p.readOnly} onChange={(v) => p.onChange({ ...p.block, attrs: v })} />;
}

function Gallery(p: Props) {
  const imgs: ImageAttrs[] = p.block.content || [];
  return (
    <div className="space-y-3">
      {imgs.map((im, i) => (
        <div key={i} className="rounded border border-line p-2">
          <ImageFields value={im} readOnly={p.readOnly} compact onChange={(v) => p.onChange({ ...p.block, content: imgs.map((x, j) => (j === i ? v : x)) })} />
          {!p.readOnly && imgs.length > 2 && <div className="mt-1"><Small danger onClick={() => p.onChange({ ...p.block, content: imgs.filter((_, j) => j !== i) })}>remove</Small></div>}
        </div>
      ))}
      <div className="flex gap-2">
        {!p.readOnly && imgs.length < 4 && <Small onClick={() => p.onChange({ ...p.block, content: [...imgs, { src: '', alt: '', width: 1600, height: 900 }] })}>+ image</Small>}
        <Text placeholder="Gallery caption (optional)" value={p.block.attrs?.caption || ''} readOnly={p.readOnly} aria-label="Caption" onChange={(e) => p.onChange(set(p.block, { caption: e.target.value || null }))} />
      </div>
    </div>
  );
}

function Compare(p: Props) {
  const a = p.block.attrs || {};
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {(['before', 'after'] as const).map((k) => (
        <div key={k} className="rounded border border-line p-2">
          <Text value={a[`label_${k}`] || ''} readOnly={p.readOnly} aria-label={`${k} label`} className="mb-2 w-40" onChange={(e) => p.onChange(set(p.block, { [`label_${k}`]: e.target.value }))} />
          <ImageFields value={a[k]} readOnly={p.readOnly} compact onChange={(v) => p.onChange(set(p.block, { [k]: v }))} />
        </div>
      ))}
      <Text placeholder="Caption (optional)" value={a.caption || ''} readOnly={p.readOnly} aria-label="Caption" className="md:col-span-2" onChange={(e) => p.onChange(set(p.block, { caption: e.target.value || null }))} />
    </div>
  );
}

function Video(p: Props) {
  const a = p.block.attrs || {};
  const s = (patch: any) => p.onChange(set(p.block, patch));
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <Select value={a.kind} disabled={p.readOnly} aria-label="Video source" onChange={(e) => s({ kind: e.target.value })}>
        <option value="youtube">YouTube</option><option value="file">Self-hosted clip (mp4/webm)</option>
      </Select>
      {a.kind === 'youtube'
        ? <Text placeholder="YouTube video id (11 characters)" value={a.youtube_id || ''} readOnly={p.readOnly} aria-label="YouTube id" onChange={(e) => s({ youtube_id: e.target.value.trim().replace(/^.*[?&]v=|^.*youtu\.be\//, '').slice(0, 11) })} />
        : <Text placeholder="/static/blog/uploads/clip.mp4" value={a.src || ''} readOnly={p.readOnly} aria-label="Clip URL" onChange={(e) => s({ src: e.target.value })} />}
      <Text placeholder="Title (required)" value={a.title || ''} readOnly={p.readOnly} aria-label="Title" onChange={(e) => s({ title: e.target.value })} />
      <Text placeholder="Upload date YYYY-MM-DD" value={a.upload_date || ''} readOnly={p.readOnly} aria-label="Upload date" onChange={(e) => s({ upload_date: e.target.value })} />
      <Text placeholder="Description (required)" value={a.description || ''} readOnly={p.readOnly} aria-label="Description" className="md:col-span-2" onChange={(e) => s({ description: e.target.value })} />
      <Text placeholder="Duration, e.g. PT1M32S" value={a.duration || ''} readOnly={p.readOnly} aria-label="Duration" onChange={(e) => s({ duration: e.target.value })} />
      <Text placeholder="Caption (optional)" value={a.caption || ''} readOnly={p.readOnly} aria-label="Caption" onChange={(e) => s({ caption: e.target.value || null })} />
      <div className="md:col-span-2">
        <span className="label">Poster image (required — shown before play)</span>
        <ImageFields value={{ src: a.poster || '', alt: a.title || 'poster', width: a.width || 1280, height: a.height || 720 }} readOnly={p.readOnly} compact
          onChange={(v) => s({ poster: v.src, width: v.width, height: v.height })} />
      </div>
      {a.kind === 'file' && <label className="inline-flex items-center gap-1.5 text-xs text-muted"><input type="checkbox" checked={!!a.loop} disabled={p.readOnly} onChange={(e) => s({ loop: e.target.checked })} /> Silent looping clip (autoplays when visible)</label>}
    </div>
  );
}

function Table(p: Props) {
  const rows: Runs[][] = p.block.content || [[]];
  const a = p.block.attrs || {};
  const cols = rows[0]?.length || 0;
  const setCell = (r: number, c: number, runs: Runs) => p.onChange({ ...p.block, content: rows.map((row, i) => (i === r ? row.map((cell, j) => (j === c ? runs : cell)) : row)) });
  const addRow = () => p.onChange({ ...p.block, content: [...rows, Array.from({ length: cols }, () => [{ text: '' }])] });
  const addCol = () => p.onChange({ ...p.block, attrs: { ...a, align: [...(a.align || Array(cols).fill('left')), 'left'] }, content: rows.map((row) => [...row, [{ text: '' }]]) });
  const delRow = (r: number) => p.onChange({ ...p.block, content: rows.filter((_, i) => i !== r) });
  const delCol = (c: number) => p.onChange({ ...p.block, attrs: { ...a, align: (a.align || []).filter((_: any, j: number) => j !== c) }, content: rows.map((row) => row.filter((_, j) => j !== c)) });
  const align: string[] = a.align?.length === cols ? a.align : Array(cols).fill('left');
  return (
    <div className="space-y-2">
      <Text placeholder="Caption (required — what the table shows)" value={a.caption || ''} readOnly={p.readOnly} aria-label="Caption" onChange={(e) => p.onChange(set(p.block, { caption: e.target.value }))} />
      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full text-sm">
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className={r === 0 && a.has_header ? 'bg-raised font-semibold' : ''}>
                {row.map((cell, c) => (
                  <td key={c} className="min-w-[110px] border-b border-line p-1 align-top">
                    <RichText value={cell} version={p.version} readOnly={p.readOnly} singleLine placeholder={r === 0 ? 'Header' : ''} className="text-sm" onChange={(runs) => setCell(r, c, runs)} />
                  </td>
                ))}
                {!p.readOnly && <td className="w-8 p-1 text-center">{rows.length > 2 && <Small danger label="Delete row" onClick={() => delRow(r)}>×</Small>}</td>}
              </tr>
            ))}
            {!p.readOnly && (
              <tr>
                {Array.from({ length: cols }).map((_, c) => (
                  <td key={c} className="p-1">
                    <div className="flex gap-1">
                      <Select value={align[c]} aria-label={`Column ${c + 1} alignment`} className="py-0.5 text-[11px]"
                        onChange={(e) => p.onChange(set(p.block, { align: align.map((x, j) => (j === c ? e.target.value : x)) }))}>
                        <option value="left">left</option><option value="right">right</option><option value="center">center</option>
                      </Select>
                      {cols > 1 && <Small danger label="Delete column" onClick={() => delCol(c)}>×</Small>}
                    </div>
                  </td>
                ))}
                <td />
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!p.readOnly && (
        <div className="flex flex-wrap gap-2 text-[11px]">
          <Small onClick={addRow}>+ row</Small><Small onClick={addCol}>+ column</Small>
          <label className="inline-flex items-center gap-1 text-muted"><input type="checkbox" checked={!!a.has_header} onChange={(e) => p.onChange(set(p.block, { has_header: e.target.checked }))} /> first row is a header</label>
          <label className="inline-flex items-center gap-1 text-muted"><input type="checkbox" checked={!!a.sortable} onChange={(e) => p.onChange(set(p.block, { sortable: e.target.checked }))} /> sortable</label>
          <Select value={a.mobile || 'scroll'} aria-label="On phones" className="w-auto py-0.5 text-[11px]" onChange={(e) => p.onChange(set(p.block, { mobile: e.target.value }))}>
            <option value="scroll">phones: scroll sideways</option><option value="stack">phones: stack rows</option>
          </Select>
          <Select value={a.layout || 'inset'} aria-label="Layout" className="w-auto py-0.5 text-[11px]" onChange={(e) => p.onChange(set(p.block, { layout: e.target.value }))}>
            <option value="inset">inset</option><option value="breakout">breakout</option>
          </Select>
        </div>
      )}
    </div>
  );
}

function Callout(p: Props) {
  const kind = p.block.attrs?.kind || 'info';
  const colors: Record<string, string> = { info: 'border-muted', tip: 'border-success', warning: 'border-warning', result: 'border-warning' };
  return (
    <div className={cx('rounded border-l-2 pl-3', colors[kind])}>
      <div className="mb-1.5 flex gap-2">
        <Select value={kind} disabled={p.readOnly} aria-label="Callout kind" className="w-32" onChange={(e) => p.onChange(set(p.block, { kind: e.target.value }))}>
          <option value="info">Note</option><option value="tip">Tip</option><option value="warning">Warning</option><option value="result">Result</option>
        </Select>
        <Text placeholder="Title (optional)" value={p.block.attrs?.title || ''} readOnly={p.readOnly} aria-label="Title" onChange={(e) => p.onChange(set(p.block, { title: e.target.value || null }))} />
      </div>
      <RichText value={p.block.content} version={p.version} readOnly={p.readOnly} placeholder="Callout text" onChange={(r) => p.onChange({ ...p.block, content: r })} onDeleteEmpty={p.onDeleteEmpty} />
    </div>
  );
}

function Quote(p: Props) {
  const a = p.block.attrs || {};
  return (
    <div className="border-l-2 border-primary pl-3">
      <RichText value={p.block.content} version={p.version} readOnly={p.readOnly} placeholder="The quote" className="text-lg font-medium" onChange={(r) => p.onChange({ ...p.block, content: r })} onDeleteEmpty={p.onDeleteEmpty} />
      <div className="mt-2 grid grid-cols-3 gap-2">
        <Text placeholder="Who said it (required)" value={a.attribution || ''} readOnly={p.readOnly} aria-label="Attribution" onChange={(e) => p.onChange(set(p.block, { attribution: e.target.value }))} />
        <Text placeholder="Role" value={a.role || ''} readOnly={p.readOnly} aria-label="Role" onChange={(e) => p.onChange(set(p.block, { role: e.target.value || null }))} />
        <Text placeholder="Company" value={a.company || ''} readOnly={p.readOnly} aria-label="Company" onChange={(e) => p.onChange(set(p.block, { company: e.target.value || null }))} />
      </div>
    </div>
  );
}

function Code(p: Props) {
  return (
    <div>
      <div className="mb-1.5 flex gap-2">
        <Text placeholder="language (python, json…)" value={p.block.attrs?.language || 'text'} readOnly={p.readOnly} aria-label="Language" className="w-40 font-mono" onChange={(e) => p.onChange(set(p.block, { language: e.target.value.toLowerCase() }))} />
        <Text placeholder="Caption (optional)" value={p.block.attrs?.caption || ''} readOnly={p.readOnly} aria-label="Caption" onChange={(e) => p.onChange(set(p.block, { caption: e.target.value || null }))} />
      </div>
      <textarea value={p.block.content || ''} readOnly={p.readOnly} aria-label="Code" spellCheck={false} rows={Math.min(20, Math.max(4, (p.block.content || '').split('\n').length + 1))}
        className="input-field w-full font-mono text-xs leading-relaxed" onChange={(e) => p.onChange({ ...p.block, content: e.target.value })} />
    </div>
  );
}

function StatBand(p: Props) {
  const stats: any[] = p.block.content || [];
  const update = (i: number, patch: any) => p.onChange({ ...p.block, content: stats.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  return (
    <div>
      <div className="grid gap-2 md:grid-cols-2">
        {stats.map((s, i) => (
          <div key={i} className="grid grid-cols-[3rem_1fr_3rem] gap-1 rounded border border-line p-2">
            <Text placeholder="₹" value={s.prefix || ''} readOnly={p.readOnly} aria-label="Prefix" onChange={(e) => update(i, { prefix: e.target.value })} />
            <Text placeholder="Number as shown, e.g. 1,240" value={s.value || ''} readOnly={p.readOnly} aria-label="Value" className="text-lg font-bold" onChange={(e) => { const num = parseFloat(e.target.value.replace(/[^0-9.]/g, '')); update(i, { value: e.target.value, numeric: Number.isFinite(num) ? num : null }); }} />
            <Text placeholder="%" value={s.suffix || ''} readOnly={p.readOnly} aria-label="Suffix" onChange={(e) => update(i, { suffix: e.target.value })} />
            <Text placeholder="What it measures" value={s.label || ''} readOnly={p.readOnly} aria-label="Label" className="col-span-3" onChange={(e) => update(i, { label: e.target.value })} />
            {!p.readOnly && stats.length > 2 && <div className="col-span-3"><Small danger onClick={() => p.onChange({ ...p.block, content: stats.filter((_, j) => j !== i) })}>remove</Small></div>}
          </div>
        ))}
      </div>
      {!p.readOnly && stats.length < 4 && <div className="mt-2"><Small onClick={() => p.onChange({ ...p.block, content: [...stats, { value: '', label: '', numeric: null, prefix: '', suffix: '' }] })}>+ number</Small></div>}
    </div>
  );
}

function Chart(p: Props) {
  const a = p.block.attrs || { labels: [], series: [] };
  const s = (patch: any) => p.onChange(set(p.block, patch));
  const labels: string[] = a.labels || [];
  const series: { name: string; values: number[] }[] = a.series || [];
  const setLabel = (i: number, v: string) => s({ labels: labels.map((x, j) => (j === i ? v : x)) });
  const setVal = (si: number, i: number, v: string) => s({ series: series.map((sr, j) => (j === si ? { ...sr, values: sr.values.map((x, k) => (k === i ? (parseFloat(v) || 0) : x)) } : sr)) });
  const addCat = () => s({ labels: [...labels, `Item ${labels.length + 1}`], series: series.map((sr) => ({ ...sr, values: [...sr.values, 0] })) });
  const delCat = (i: number) => s({ labels: labels.filter((_, j) => j !== i), series: series.map((sr) => ({ ...sr, values: sr.values.filter((_, j) => j !== i) })) });
  const addSeries = () => s({ series: [...series, { name: `Series ${series.length + 1}`, values: labels.map(() => 0) }] });
  return (
    <div className="space-y-2">
      <div className="grid gap-2 md:grid-cols-3">
        <Select value={a.kind} disabled={p.readOnly} aria-label="Chart type" onChange={(e) => s({ kind: e.target.value, series: e.target.value === 'donut' ? series.slice(0, 1) : series })}>
          <option value="bar">Bar</option><option value="line">Line</option><option value="donut">Donut</option>
        </Select>
        <Text placeholder="Title (required)" value={a.title || ''} readOnly={p.readOnly} aria-label="Title" onChange={(e) => s({ title: e.target.value })} />
        <Text placeholder="Unit (%, h, ₹)" value={a.unit || ''} readOnly={p.readOnly} aria-label="Unit" onChange={(e) => s({ unit: e.target.value })} />
      </div>
      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full text-sm">
          <thead><tr className="bg-raised"><th className="p-1 text-left text-[11px] text-muted">category</th>{series.map((sr, si) => (
            <th key={si} className="p-1"><Text value={sr.name} readOnly={p.readOnly} aria-label="Series name" className="py-0.5 text-xs" onChange={(e) => s({ series: series.map((x, j) => (j === si ? { ...x, name: e.target.value } : x)) })} /></th>))}<th /></tr></thead>
          <tbody>
            {labels.map((lab, i) => (
              <tr key={i}>
                <td className="p-1"><Text value={lab} readOnly={p.readOnly} aria-label="Category" className="py-0.5 text-xs" onChange={(e) => setLabel(i, e.target.value)} /></td>
                {series.map((sr, si) => <td key={si} className="p-1"><Text type="number" value={sr.values[i] ?? 0} readOnly={p.readOnly} aria-label="Value" className="py-0.5 text-right text-xs" onChange={(e) => setVal(si, i, e.target.value)} /></td>)}
                <td className="p-1">{!p.readOnly && labels.length > 2 && <Small danger label="Remove category" onClick={() => delCat(i)}>×</Small>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!p.readOnly && (
        <div className="flex flex-wrap gap-2">
          <Small onClick={addCat}>+ category</Small>
          {a.kind !== 'donut' && series.length < 4 && <Small onClick={addSeries}>+ series</Small>}
          <Text placeholder="Source (optional)" value={a.source || ''} aria-label="Source" className="flex-1" onChange={(e) => s({ source: e.target.value || null })} />
          <Select value={a.layout || 'inset'} aria-label="Layout" className="w-auto" onChange={(e) => s({ layout: e.target.value })}><option value="inset">inset</option><option value="breakout">breakout</option></Select>
        </div>
      )}
    </div>
  );
}

function Flow(p: Props) {
  const nodes: any[] = p.block.content || [];
  const update = (i: number, patch: any) => p.onChange({ ...p.block, content: nodes.map((n, j) => (j === i ? { ...n, ...patch } : n)) });
  return (
    <div>
      <Text placeholder="Title (optional)" value={p.block.attrs?.title || ''} readOnly={p.readOnly} aria-label="Title" className="mb-2" onChange={(e) => p.onChange(set(p.block, { title: e.target.value || null }))} />
      <div className="flex flex-wrap items-center gap-2">
        {nodes.map((n, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-40 rounded border border-line p-1.5">
              <Text value={n.label} readOnly={p.readOnly} aria-label="Step label" className="py-0.5 text-xs font-semibold" onChange={(e) => update(i, { label: e.target.value })} />
              <Text placeholder="sub-label" value={n.sub || ''} readOnly={p.readOnly} aria-label="Sub label" className="mt-1 py-0.5 text-[11px]" onChange={(e) => update(i, { sub: e.target.value || null })} />
              <div className="mt-1 flex gap-1">
                <Select value={n.kind} disabled={p.readOnly} aria-label="Kind" className="py-0.5 text-[11px]" onChange={(e) => update(i, { kind: e.target.value })}>
                  <option value="system">system</option><option value="bot">bot</option><option value="human">human</option><option value="decision">decision</option><option value="result">result</option>
                </Select>
                {!p.readOnly && nodes.length > 2 && <Small danger label="Remove step" onClick={() => p.onChange({ ...p.block, content: nodes.filter((_, j) => j !== i) })}>×</Small>}
              </div>
            </div>
            {i < nodes.length - 1 && <span className="text-muted">→</span>}
          </div>
        ))}
        {!p.readOnly && nodes.length < 7 && <Small onClick={() => p.onChange({ ...p.block, content: [...nodes, { label: 'Step', sub: null, kind: 'system' }] })}>+ step</Small>}
      </div>
    </div>
  );
}

function Faq(p: Props) {
  const items: { question: string; answer: Runs }[] = p.block.content || [];
  const update = (i: number, patch: any) => p.onChange({ ...p.block, content: items.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  return (
    <div>
      <Text value={p.block.attrs?.title || ''} readOnly={p.readOnly} aria-label="FAQ title" className="mb-2 font-semibold" onChange={(e) => p.onChange(set(p.block, { title: e.target.value }))} />
      <div className="space-y-2">
        {items.map((it, i) => (
          <div key={i} className="rounded border border-line p-2">
            <Text placeholder="Question" value={it.question} readOnly={p.readOnly} aria-label="Question" className="mb-1 font-semibold" onChange={(e) => update(i, { question: e.target.value })} />
            <RichText value={it.answer} version={p.version} readOnly={p.readOnly} placeholder="Answer — 30 to 80 words lands in featured snippets" className="text-sm" onChange={(r) => update(i, { answer: r })} />
            <div className="mt-1 flex items-center justify-between text-[11px] text-muted">
              <span>{it.answer.map((r) => r.text).join('').trim().split(/\s+/).filter(Boolean).length} words</span>
              {!p.readOnly && items.length > 1 && <Small danger onClick={() => p.onChange({ ...p.block, content: items.filter((_, j) => j !== i) })}>remove</Small>}
            </div>
          </div>
        ))}
      </div>
      {!p.readOnly && <div className="mt-2"><Small onClick={() => p.onChange({ ...p.block, content: [...items, { question: '', answer: [{ text: '' }] }] })}>+ question</Small></div>}
    </div>
  );
}

function Cta(p: Props) {
  const a = p.block.attrs || {};
  const s = (patch: any) => p.onChange(set(p.block, patch));
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <Text placeholder="Heading" value={a.heading || ''} readOnly={p.readOnly} aria-label="Heading" className="md:col-span-2 font-semibold" onChange={(e) => s({ heading: e.target.value })} />
      <Text placeholder="Supporting line (optional)" value={a.text || ''} readOnly={p.readOnly} aria-label="Text" className="md:col-span-2" onChange={(e) => s({ text: e.target.value || null })} />
      <Text placeholder="Button label" value={a.button_label || ''} readOnly={p.readOnly} aria-label="Button label" onChange={(e) => s({ button_label: e.target.value })} />
      <Text placeholder="Link" value={a.href || ''} readOnly={p.readOnly} aria-label="Link" onChange={(e) => s({ href: e.target.value })} />
      <Select value={a.kind || 'service'} disabled={p.readOnly} aria-label="Kind" onChange={(e) => s({ kind: e.target.value })}><option value="service">Service page</option><option value="calendly">Calendly</option><option value="contact">Contact</option></Select>
    </div>
  );
}

function Divider(p: Props) {
  return (
    <div className="flex items-center gap-3">
      <hr className="flex-1 border-line" />
      <Select value={p.block.attrs?.style || 'line'} disabled={p.readOnly} aria-label="Divider style" className="w-28" onChange={(e) => p.onChange(set(p.block, { style: e.target.value }))}>
        <option value="line">line</option><option value="dots">dots</option><option value="glyph">glyph</option>
      </Select>
      <hr className="flex-1 border-line" />
    </div>
  );
}

function Embed(p: Props) {
  const a = p.block.attrs || {};
  const s = (patch: any) => p.onChange(set(p.block, patch));
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <Select value={a.provider} disabled={p.readOnly} aria-label="Provider" onChange={(e) => s({ provider: e.target.value })}><option value="linkedin">LinkedIn</option><option value="x">X</option></Select>
      <Text placeholder="Post URL" value={a.url || ''} readOnly={p.readOnly} aria-label="URL" onChange={(e) => s({ url: e.target.value })} />
      <Text placeholder="Title (optional)" value={a.title || ''} readOnly={p.readOnly} aria-label="Title" onChange={(e) => s({ title: e.target.value || null })} />
      <Text placeholder="Preview text (optional)" value={a.preview_text || ''} readOnly={p.readOnly} aria-label="Preview text" onChange={(e) => s({ preview_text: e.target.value || null })} />
      <p className="text-[11px] text-muted md:col-span-2">Rendered as a link card — no third-party script loads on the page.</p>
    </div>
  );
}

function Legacy(p: Props) {
  return (
    <div>
      <p className="mb-1 text-[11px] text-warning">Migrated HTML. Split it into real blocks when you can; it is sanitised on render.</p>
      <textarea value={p.block.attrs?.html || ''} readOnly={p.readOnly} aria-label="Legacy HTML" rows={8} className="input-field w-full font-mono text-xs" onChange={(e) => p.onChange(set(p.block, { html: e.target.value }))} />
    </div>
  );
}

export const EDITORS: Record<string, (p: Props) => JSX.Element> = {
  paragraph: Paragraph, heading: Heading, key_takeaways: KeyTakeaways, list: ListBlock, steps: Steps,
  image: Image, gallery: Gallery, compare_slider: Compare, video: Video, table: Table, callout: Callout,
  quote: Quote, code: Code, stat_band: StatBand, chart: Chart, process_flow: Flow, faq: Faq, cta: Cta,
  divider: Divider, embed: Embed, legacy_html: Legacy,
};
