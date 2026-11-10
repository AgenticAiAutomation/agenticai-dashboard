'use client';

import { useRef, useState } from 'react';
import { Card } from '@/components/ui';
import FormatTextarea from '@/components/FormatTextarea';
import { ListEditor, TableEditor } from '@/components/PlaybookBuilder';
import { apiError, seoApi } from '@/lib/seo';
import {
  CALLOUT_LABEL_MAX,
  CTAS,
  CtaKey,
  ITEM_TYPES,
  ItemType,
  PlaybookBlocksV2,
  PlaybookSectionV2,
  RESERVED_LABELS,
  SECTION_MAX_WORDS,
  SectionItem,
  countCallouts,
  countWords,
  emptyItem,
  emptySectionV2,
  playbookProblems,
  sectionMarkdownV2,
} from '@/lib/playbook';

/**
 * Blog Playbook v2 writer (BLOG_PLAYBOOK_V2). Same contract as the v1
 * builder: it edits blocks only and the page composes them (composeV2) into
 * the one Markdown body that is scored and published.
 */

const SITE_ORIGIN = 'https://agenticaiautomation.co';
const INLINE_PREFIX = '/static/blog/inline/';
const OPTIONAL_NOTE = 'Optional — skipping it won’t cost points';

type Props = {
  value: PlaybookBlocksV2;
  onChange: (next: PlaybookBlocksV2) => void;
  /* Needed to upload images; null until the draft is first saved. */
  articleId: string | null;
  /* Saves the draft (creating the article), so images can be uploaded. */
  onSaveDraft?: () => void;
};

type Patch<T extends SectionItem> = (patch: Partial<T>) => void;

const INLINE_W = 1536;
const INLINE_H = 1024;

/**
 * The file to upload for a section image: exactly 1536 × 1024, as WebP.
 * A JPG/PNG of the right size is converted in the browser; a wrong size is
 * refused with its real dimensions. The server checks both again.
 */
async function toInlineWebp(file: File): Promise<File> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error(`“${file.name}” is not an image this browser can read.`);
  }
  const { width, height } = bitmap;
  if (width !== INLINE_W || height !== INLINE_H) {
    bitmap.close();
    throw new Error(
      `“${file.name}” is ${width} × ${height} px. Section images must be exactly ` +
        `${INLINE_W} × ${INLINE_H} px — resize or crop it and upload again.`,
    );
  }
  if (file.type === 'image/webp') {
    bitmap.close();
    return file;
  }
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/webp', 0.9));
  if (!blob || blob.type !== 'image/webp') {
    throw new Error('This browser cannot convert to WebP. Save the image as WebP and upload it again.');
  }
  return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.webp', { type: 'image/webp' });
}

function ItemEditor({
  item,
  id,
  set,
  articleId,
  onSaveDraft,
}: {
  item: SectionItem;
  id: string;
  set: Patch<any>;
  articleId: string | null;
  onSaveDraft?: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  switch (item.type) {
    case 'text':
      return <FormatTextarea id={`${id}-text`} value={item.text} onChange={(text) => set({ text })} />;

    case 'steps':
      return (
        <ListEditor idPrefix={`${id}-steps`} items={item.steps} numbered placeholder="Step"
                    addLabel="Add step" onChange={(steps) => set({ steps })} />
      );

    case 'flow':
      return (
        <ListEditor idPrefix={`${id}-flow`} items={item.flow} min={2} placeholder="Stage"
                    addLabel="Add stage" onChange={(flow) => set({ flow })} />
      );

    case 'table':
      return (
        <div className="space-y-2">
          <TableEditor idPrefix={`${id}-table`} header={item.header} rows={item.rows}
                       onChange={(header, rows) => set({ header, rows })} />
          <label className="label" htmlFor={`${id}-cap`}>Caption (optional)</label>
          <input id={`${id}-cap`} className="input-field" value={item.caption}
                 onChange={(e) => set({ caption: e.target.value })} />
          <label className="label" htmlFor={`${id}-below`}>Text below table (optional)</label>
          <FormatTextarea id={`${id}-below`} rows={2} value={item.below_text}
                          onChange={(below_text) => set({ below_text })} />
        </div>
      );

    case 'cost_table':
      return (
        <div className="space-y-2">
          <p className="text-xs text-muted">Rename, add or remove columns (at least two).</p>
          <TableEditor idPrefix={`${id}-cost`} header={item.columns} rows={item.rows}
                       removableColumns
                       onChange={(columns, rows) => set({ columns, rows })} />
          <label className="label" htmlFor={`${id}-below`}>Text below table (optional)</label>
          <FormatTextarea id={`${id}-below`} rows={2} value={item.below_text}
                          onChange={(below_text) => set({ below_text })} />
        </div>
      );

    case 'image': {
      const previous = item.url;
      const upload = async (file: File) => {
        if (!articleId) return;
        setBusy(true);
        setError(null);
        let ready: File;
        try {
          ready = await toInlineWebp(file);
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
          setBusy(false);
          return;
        }
        try {
          const { data } = await seoApi.uploadInlineImage(articleId, ready);
          set({ url: data.url });
          // Replacing: the old file goes (kept server-side while the post is live).
          if (previous.startsWith(INLINE_PREFIX)) {
            seoApi.deleteInlineImage(articleId, previous).catch(() => {});
          }
        } catch (err) {
          setError(apiError(err));
        } finally {
          setBusy(false);
        }
      };
      return (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-2 sm:col-span-2">
            {item.url && (
              /* Served by the website, not the dashboard. */
              /* eslint-disable-next-line @next/next/no-img-element */
              <img src={item.url.startsWith('/') ? SITE_ORIGIN + item.url : item.url}
                   alt={item.alt || 'Uploaded section image'} width={1536} height={1024}
                   className="h-auto w-full rounded border border-line" />
            )}
            {/* The native picker stays hidden; the button below opens it, so the
                control is a real, visible button in every theme. */}
            {/* Any image is selectable (a WebP-only filter showed writers an
                empty folder); toInlineWebp checks the size and converts. */}
            <input ref={fileRef} id={`${id}-file`} type="file" accept="image/*"
                   className="sr-only" tabIndex={-1} aria-hidden="true"
                   onChange={(e) => {
                     const file = e.target.files?.[0];
                     if (file) upload(file);
                     e.target.value = '';
                   }} />
            <div className="flex flex-wrap items-center gap-3">
              {articleId ? (
                <button type="button" className="btn-primary text-sm" disabled={busy}
                        onClick={() => fileRef.current?.click()}>
                  {busy ? 'Uploading…' : item.url ? 'Replace image' : 'Upload image'}
                </button>
              ) : (
                <button type="button" className="btn-primary text-sm" onClick={onSaveDraft}
                        disabled={!onSaveDraft}>
                  Save draft to enable image upload
                </button>
              )}
              <span className="text-xs text-muted">
                Exactly 1536 × 1024 px. JPG or PNG is converted to WebP for you.
                {!articleId && ' A new article must be saved once before images can be uploaded.'}
              </span>
            </div>
            {error && <p className="text-xs text-danger" role="alert">{error}</p>}
          </div>
          <div>
            <label className="label" htmlFor={`${id}-alt`}>Alt text (required)</label>
            <input id={`${id}-alt`} className="input-field" value={item.alt}
                   onChange={(e) => set({ alt: e.target.value })} />
          </div>
          <div>
            <label className="label" htmlFor={`${id}-cap`}>Caption (optional)</label>
            <input id={`${id}-cap`} className="input-field" value={item.caption}
                   onChange={(e) => set({ caption: e.target.value })} />
          </div>
        </div>
      );
    }

    case 'real_example':
      return (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <p className="text-xs text-muted sm:col-span-2">
            A real client, never an invented one. Two or three real numbers.
          </p>
          <div className="sm:col-span-2">
            <label className="label" htmlFor={`${id}-client`}>Client type</label>
            <input id={`${id}-client`} className="input-field" value={item.client}
                   placeholder="a 3-doctor dental clinic in Pune"
                   onChange={(e) => set({ client: e.target.value })} />
          </div>
          <div>
            <label className="label" htmlFor={`${id}-before`}>Before</label>
            <textarea id={`${id}-before`} className="input-field" rows={2} value={item.before}
                      onChange={(e) => set({ before: e.target.value })} />
          </div>
          <div>
            <label className="label" htmlFor={`${id}-after`}>After</label>
            <textarea id={`${id}-after`} className="input-field" rows={2} value={item.after}
                      onChange={(e) => set({ after: e.target.value })} />
          </div>
          {item.metrics.map((metric, m) => (
            <div key={m} className="grid grid-cols-2 gap-2 sm:col-span-2">
              <div>
                <label className="label" htmlFor={`${id}-m${m}-l`}>Metric {m + 1}</label>
                <input id={`${id}-m${m}-l`} className="input-field" value={metric.label}
                       placeholder="No-shows"
                       onChange={(e) => {
                         const metrics = [...item.metrics];
                         metrics[m] = { ...metric, label: e.target.value };
                         set({ metrics });
                       }} />
              </div>
              <div>
                <label className="label" htmlFor={`${id}-m${m}-v`}>Value</label>
                <input id={`${id}-m${m}-v`} className="input-field" value={metric.value}
                       placeholder="18% to 7% in 14 days"
                       onChange={(e) => {
                         const metrics = [...item.metrics];
                         metrics[m] = { ...metric, value: e.target.value };
                         set({ metrics });
                       }} />
              </div>
            </div>
          ))}
          <div className="flex gap-2 sm:col-span-2">
            {item.metrics.length < 3 && (
              <button type="button" className="btn-secondary text-xs"
                      onClick={() => set({ metrics: [...item.metrics, { label: '', value: '' }] })}>
                Add metric
              </button>
            )}
            {item.metrics.length > 2 && (
              <button type="button" className="text-xs text-danger"
                      onClick={() => set({ metrics: item.metrics.slice(0, -1) })}>
                Remove last metric
              </button>
            )}
          </div>
          <div className="sm:col-span-2">
            <label className="label" htmlFor={`${id}-desc`}>Description (optional)</label>
            <FormatTextarea id={`${id}-desc`} rows={2} value={item.description}
                            onChange={(description) => set({ description })} />
          </div>
        </div>
      );

    case 'callout':
      return (
        <div className="space-y-2">
          <label className="label" htmlFor={`${id}-label`}>
            Label (required, {CALLOUT_LABEL_MAX} characters max)
          </label>
          <input id={`${id}-label`} className="input-field sm:w-72" value={item.label}
                 maxLength={CALLOUT_LABEL_MAX} placeholder="Clinic tip"
                 onChange={(e) => set({ label: e.target.value })} />
          <p className="text-xs text-muted">Not allowed: {RESERVED_LABELS.join(', ')}.</p>
          <label className="label" htmlFor={`${id}-co-text`}>Text</label>
          <FormatTextarea id={`${id}-co-text`} rows={2} value={item.text}
                          onChange={(text) => set({ text })} />
        </div>
      );
  }
}

function SectionEditorV2({
  section,
  index,
  total,
  hasCallout,
  articleId,
  onSaveDraft,
  onChange,
  onMove,
  onRemove,
}: {
  section: PlaybookSectionV2;
  index: number;
  total: number;
  hasCallout: boolean;
  articleId: string | null;
  onSaveDraft?: () => void;
  onChange: (next: PlaybookSectionV2) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}) {
  const [adding, setAdding] = useState<ItemType>('text');
  const words = countWords(sectionMarkdownV2(section));
  const over = words > SECTION_MAX_WORDS;
  const id = `pb2-s${index}`;
  const setItems = (items: SectionItem[]) => onChange({ ...section, items });
  const visual = section.items.some((it) => it.type !== 'text');

  const removeItem = (i: number) => {
    const item = section.items[i];
    // The stored file goes with the item (kept server-side while live).
    if (item.type === 'image' && articleId && item.url.startsWith(INLINE_PREFIX)) {
      seoApi.deleteInlineImage(articleId, item.url).catch(() => {});
    }
    setItems(section.items.filter((_, k) => k !== i));
  };

  return (
    <div className="space-y-3 rounded-lg border border-line bg-raised p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted">Section {index + 1}</span>
        <div className="flex items-center gap-3 text-xs">
          <span className={`tabular-nums ${over ? 'font-semibold text-danger' : 'text-muted'}`}
                aria-live="polite">
            {words}/{SECTION_MAX_WORDS} words{over ? ' — split this section' : ''}
          </span>
          <button className="text-muted disabled:opacity-40" onClick={() => onMove(-1)}
                  disabled={index === 0} aria-label={`Move section ${index + 1} up`}>↑</button>
          <button className="text-muted disabled:opacity-40" onClick={() => onMove(1)}
                  disabled={index === total - 1} aria-label={`Move section ${index + 1} down`}>↓</button>
          {total > 1 && <button className="text-danger" onClick={onRemove}>Remove</button>}
        </div>
      </div>

      <div>
        <label className="label" htmlFor={`${id}-q`}>Question (H2)</label>
        <input id={`${id}-q`} className="input-field" value={section.question}
               placeholder="How does WhatsApp automation work in a clinic?"
               onChange={(e) => onChange({ ...section, question: e.target.value })} />
      </div>

      <div>
        <label className="label" htmlFor={`${id}-b`}>Answer — lead with the direct answer</label>
        <FormatTextarea id={`${id}-b`} rows={5} value={section.body}
                        onChange={(body) => onChange({ ...section, body })} />
        <p className="mt-1 text-xs text-muted">Leave a blank line between paragraphs.</p>
      </div>

      {section.items.map((item, i) => {
        const meta = ITEM_TYPES.find((t) => t.value === item.type)!;
        return (
          <div key={i} className="space-y-2 rounded border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="font-semibold">
                {meta.label}
                {meta.optional && <span className="ml-2 font-normal text-muted">{OPTIONAL_NOTE}</span>}
              </span>
              <span className="flex gap-3">
                <button className="text-muted disabled:opacity-40" disabled={i === 0}
                        aria-label={`Move ${meta.label} up`}
                        onClick={() => {
                          const items = [...section.items];
                          [items[i - 1], items[i]] = [items[i], items[i - 1]];
                          setItems(items);
                        }}>↑</button>
                <button className="text-muted disabled:opacity-40"
                        disabled={i === section.items.length - 1}
                        aria-label={`Move ${meta.label} down`}
                        onClick={() => {
                          const items = [...section.items];
                          [items[i], items[i + 1]] = [items[i + 1], items[i]];
                          setItems(items);
                        }}>↓</button>
                <button className="text-danger" onClick={() => removeItem(i)}>Remove</button>
              </span>
            </div>
            <ItemEditor
              item={item}
              id={`${id}-i${i}`}
              articleId={articleId}
              onSaveDraft={onSaveDraft}
              set={(patch) => {
                const items = [...section.items];
                items[i] = { ...item, ...patch } as SectionItem;
                setItems(items);
              }}
            />
          </div>
        );
      })}

      {!visual && (
        <p className="text-xs text-warning">
          Every section should carry at least one visual element — steps, a table, a callout,
          a flow, an image or a real example.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor={`${id}-add`}>Item to add</label>
        <select id={`${id}-add`} className="input-field sm:w-64" value={adding}
                onChange={(e) => setAdding(e.target.value as ItemType)}>
          {ITEM_TYPES.map((t) => (
            <option key={t.value} value={t.value} disabled={t.value === 'callout' && hasCallout}>
              {t.label}{t.optional ? ' (optional)' : ''}
            </option>
          ))}
        </select>
        <button className="btn-secondary text-xs"
                disabled={adding === 'callout' && hasCallout}
                onClick={() => setItems([...section.items, emptyItem(adding)])}>
          {adding === 'callout' ? 'Add callout' : 'Add item'}
        </button>
        {adding === 'callout' && hasCallout && (
          <span className="text-xs text-muted">One callout per article — it already has one.</span>
        )}
      </div>
    </div>
  );
}

export default function PlaybookBuilderV2({ value, onChange, articleId, onSaveDraft }: Props) {
  const set = (patch: Partial<PlaybookBlocksV2>) => onChange({ ...value, ...patch });
  const hasCallout = countCallouts(value) > 0;
  const problems = playbookProblems(value);

  return (
    <div className="space-y-6">
      <Card title="TL;DR and audience">
        <div className="space-y-3">
          {value.tldr.map((bullet, index) => (
            <div key={index}>
              <label className="label" htmlFor={`pb2-tldr-${index}`}>
                TL;DR bullet {index + 1}{index === 0 ? ' — include the focus keyword' : ''}
              </label>
              <input id={`pb2-tldr-${index}`} className="input-field" value={bullet}
                     onChange={(e) => {
                       const tldr = [...value.tldr];
                       tldr[index] = e.target.value;
                       set({ tldr });
                     }} />
            </div>
          ))}
          <div>
            <label className="label" htmlFor="pb2-who">Who this is for (one line)</label>
            <input id="pb2-who" className="input-field" value={value.who}
                   placeholder="clinic owners handling 30+ appointments a day."
                   onChange={(e) => set({ who: e.target.value })} />
          </div>
        </div>
      </Card>

      <Card
        title={`Question sections · ${value.sections.length}`}
        action={
          <button className="btn-secondary text-xs"
                  onClick={() => set({ sections: [...value.sections, emptySectionV2()] })}>
            Add section
          </button>
        }
      >
        <p className="mb-4 text-xs text-muted">
          At least three. Each one answers a real question in {SECTION_MAX_WORDS} words or
          fewer and carries at least one visual each. Exactly one callout in the whole article.
        </p>
        <div className="space-y-4">
          {value.sections.map((section, index) => (
            <SectionEditorV2
              key={index}
              section={section}
              index={index}
              total={value.sections.length}
              hasCallout={hasCallout}
              articleId={articleId}
              onSaveDraft={onSaveDraft}
              onChange={(next) => {
                const sections = [...value.sections];
                sections[index] = next;
                set({ sections });
              }}
              onMove={(delta) => {
                const sections = [...value.sections];
                const target = index + delta;
                [sections[index], sections[target]] = [sections[target], sections[index]];
                set({ sections });
              }}
              onRemove={() => set({ sections: value.sections.filter((_, i) => i !== index) })}
            />
          ))}
        </div>
      </Card>

      <Card title="Call to action">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="pb2-cta">Where it sends the reader</label>
            <select id="pb2-cta" className="input-field" value={value.cta}
                    onChange={(e) => set({ cta: e.target.value as CtaKey })}>
              {(Object.keys(CTAS) as Exclude<CtaKey, ''>[]).map((key) => (
                <option key={key} value={key}>{CTAS[key].name}</option>
              ))}
              <option value="">No CTA</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="pb2-cta-text">Lead-in (optional)</label>
            <input id="pb2-cta-text" className="input-field" value={value.cta_text}
                   placeholder="Want to see it on your own booking flow?"
                   onChange={(e) => set({ cta_text: e.target.value })} />
          </div>
        </div>
      </Card>

      {problems.length > 0 && (
        <Card title="Fix before submitting">
          <ul className="space-y-1 text-xs text-warning" role="status">
            {problems.map((p) => <li key={p}>• {p}</li>)}
          </ul>
        </Card>
      )}
    </div>
  );
}
