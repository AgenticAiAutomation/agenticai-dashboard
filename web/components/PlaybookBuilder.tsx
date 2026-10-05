'use client';

import { Card } from '@/components/ui';
import {
  CALLOUT_LABELS,
  COST_HEADER,
  CTAS,
  Callout,
  CalloutTone,
  CtaKey,
  PlaybookBlocks,
  PlaybookSection,
  SECTION_KINDS,
  SECTION_MAX_WORDS,
  SectionKind,
  countWords,
  emptySection,
  sectionMarkdown,
} from '@/lib/playbook';

/**
 * The Blog Playbook writer: the answer-first format as a form.
 *
 * It edits blocks only. The page composes them into the same Markdown body
 * the raw editor writes (lib/playbook.ts), so scoring, Rank Math and
 * publishing see an ordinary article. Title, slug, meta, FAQs, From the
 * author and the image stay in the page's existing fields — not duplicated
 * here.
 */

type Props = {
  value: PlaybookBlocks;
  onChange: (next: PlaybookBlocks) => void;
};

function ListEditor({
  items,
  onChange,
  placeholder,
  addLabel,
  numbered = false,
  min = 1,
  idPrefix,
}: {
  items: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  addLabel: string;
  numbered?: boolean;
  min?: number;
  idPrefix: string;
}) {
  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-2">
          <span className="w-5 shrink-0 text-right text-xs tabular-nums text-muted">
            {numbered ? `${index + 1}.` : '→'}
          </span>
          <label className="sr-only" htmlFor={`${idPrefix}-${index}`}>
            {placeholder} {index + 1}
          </label>
          <input
            id={`${idPrefix}-${index}`}
            className="input-field"
            value={item}
            placeholder={placeholder}
            onChange={(e) => {
              const next = [...items];
              next[index] = e.target.value;
              onChange(next);
            }}
          />
          {items.length > min && (
            <button
              className="shrink-0 text-xs text-danger"
              onClick={() => onChange(items.filter((_, i) => i !== index))}
            >
              Remove
            </button>
          )}
        </div>
      ))}
      <button className="btn-secondary text-xs" onClick={() => onChange([...items, ''])}>
        {addLabel}
      </button>
    </div>
  );
}

function TableEditor({
  header,
  rows,
  onChange,
  fixedHeader = false,
  idPrefix,
}: {
  header: string[];
  rows: string[][];
  onChange: (header: string[], rows: string[][]) => void;
  fixedHeader?: boolean;
  idPrefix: string;
}) {
  const width = header.length;
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              {header.map((cell, c) => (
                <th key={c} className="text-left font-normal">
                  {fixedHeader ? (
                    <span className="text-muted">{cell}</span>
                  ) : (
                    <>
                      <label className="sr-only" htmlFor={`${idPrefix}-h${c}`}>
                        Column {c + 1} heading
                      </label>
                      <input
                        id={`${idPrefix}-h${c}`}
                        className="input-field font-semibold"
                        value={cell}
                        placeholder={`Column ${c + 1}`}
                        onChange={(e) => {
                          const next = [...header];
                          next[c] = e.target.value;
                          onChange(next, rows);
                        }}
                      />
                    </>
                  )}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r}>
                {Array.from({ length: width }, (_, c) => (
                  <td key={c}>
                    <label className="sr-only" htmlFor={`${idPrefix}-r${r}c${c}`}>
                      Row {r + 1}, {header[c] || `column ${c + 1}`}
                    </label>
                    <input
                      id={`${idPrefix}-r${r}c${c}`}
                      className="input-field"
                      value={row[c] ?? ''}
                      onChange={(e) => {
                        const nextRows = rows.map((x) => [...x]);
                        nextRows[r][c] = e.target.value;
                        onChange(header, nextRows);
                      }}
                    />
                  </td>
                ))}
                <td className="w-12">
                  {rows.length > 1 && (
                    <button
                      className="text-xs text-danger"
                      onClick={() => onChange(header, rows.filter((_, i) => i !== r))}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          className="btn-secondary text-xs"
          onClick={() => onChange(header, [...rows, Array.from({ length: width }, () => '')])}
        >
          Add row
        </button>
        {!fixedHeader && (
          <>
            <button
              className="btn-secondary text-xs"
              onClick={() => onChange([...header, ''], rows.map((r) => [...r, '']))}
              disabled={width >= 5}
            >
              Add column
            </button>
            {width > 2 && (
              <button
                className="btn-secondary text-xs"
                onClick={() =>
                  onChange(header.slice(0, -1), rows.map((r) => r.slice(0, width - 1)))
                }
              >
                Remove last column
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function CalloutEditor({
  callouts,
  onChange,
  idPrefix,
}: {
  callouts: Callout[];
  onChange: (next: Callout[]) => void;
  idPrefix: string;
}) {
  return (
    <div className="space-y-2">
      {callouts.map((callout, index) => (
        <div key={index} className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <label className="sr-only" htmlFor={`${idPrefix}-tone-${index}`}>
            Callout {index + 1} type
          </label>
          <select
            id={`${idPrefix}-tone-${index}`}
            className="input-field sm:w-36"
            value={callout.tone}
            onChange={(e) => {
              const next = [...callouts];
              next[index] = { ...callout, tone: e.target.value as CalloutTone };
              onChange(next);
            }}
          >
            {(Object.keys(CALLOUT_LABELS) as CalloutTone[]).map((tone) => (
              <option key={tone} value={tone}>{CALLOUT_LABELS[tone]}</option>
            ))}
          </select>
          <label className="sr-only" htmlFor={`${idPrefix}-text-${index}`}>
            Callout {index + 1} text
          </label>
          <input
            id={`${idPrefix}-text-${index}`}
            className="input-field"
            value={callout.text}
            placeholder="One or two sentences"
            onChange={(e) => {
              const next = [...callouts];
              next[index] = { ...callout, text: e.target.value };
              onChange(next);
            }}
          />
          <button
            className="shrink-0 text-xs text-danger sm:pt-2"
            onClick={() => onChange(callouts.filter((_, i) => i !== index))}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        className="btn-secondary text-xs"
        onClick={() => onChange([...callouts, { tone: 'tip', text: '' }])}
      >
        Add callout
      </button>
    </div>
  );
}

function SectionEditor({
  section,
  index,
  total,
  onChange,
  onMove,
  onRemove,
}: {
  section: PlaybookSection;
  index: number;
  total: number;
  onChange: (next: PlaybookSection) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}) {
  const words = countWords(sectionMarkdown(section));
  const over = words > SECTION_MAX_WORDS;
  const id = `pb-s${index}`;
  const set = (patch: Partial<PlaybookSection>) => onChange({ ...section, ...patch });

  return (
    <div className="space-y-3 rounded-lg border border-line bg-raised p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted">Section {index + 1}</span>
        <div className="flex items-center gap-3 text-xs">
          <span
            className={`tabular-nums ${over ? 'font-semibold text-danger' : 'text-muted'}`}
            aria-live="polite"
          >
            {words}/{SECTION_MAX_WORDS} words{over ? ' — split this section' : ''}
          </span>
          <button className="text-muted disabled:opacity-40" onClick={() => onMove(-1)}
                  disabled={index === 0} aria-label={`Move section ${index + 1} up`}>
            ↑
          </button>
          <button className="text-muted disabled:opacity-40" onClick={() => onMove(1)}
                  disabled={index === total - 1} aria-label={`Move section ${index + 1} down`}>
            ↓
          </button>
          {total > 1 && (
            <button className="text-danger" onClick={onRemove}>Remove</button>
          )}
        </div>
      </div>

      <div>
        <label className="label" htmlFor={`${id}-q`}>Question (H2)</label>
        <input
          id={`${id}-q`}
          className="input-field"
          value={section.question}
          placeholder="How does WhatsApp automation work in a clinic?"
          onChange={(e) => set({ question: e.target.value })}
        />
      </div>

      <div>
        <label className="label" htmlFor={`${id}-b`}>
          Answer — lead with the direct answer
        </label>
        <textarea
          id={`${id}-b`}
          className="input-field"
          rows={5}
          value={section.body}
          onChange={(e) => set({ body: e.target.value })}
        />
        <p className="mt-1 text-xs text-muted">
          Markdown links work here. Leave a blank line between paragraphs.
        </p>
      </div>

      <div>
        <label className="label" htmlFor={`${id}-k`}>Visual element</label>
        <select
          id={`${id}-k`}
          className="input-field sm:w-60"
          value={section.kind}
          onChange={(e) => {
            const kind = e.target.value as SectionKind;
            // A callout section needs a callout to show.
            const callouts = kind === 'callout' && !section.callouts.length
              ? [{ tone: 'tip' as CalloutTone, text: '' }]
              : section.callouts;
            set({ kind, callouts });
          }}
        >
          {SECTION_KINDS.map((k) => (
            <option key={k.value} value={k.value}>{k.label}</option>
          ))}
        </select>
        {section.kind === 'text' && (
          <p className="mt-1 text-xs text-warning">
            Every section should carry one visual element — steps, a table, a callout,
            a flow or an image.
          </p>
        )}
      </div>

      {section.kind === 'steps' && (
        <ListEditor
          idPrefix={`${id}-steps`}
          items={section.steps}
          numbered
          placeholder="Step"
          addLabel="Add step"
          onChange={(steps) => set({ steps })}
        />
      )}

      {section.kind === 'flow' && (
        <ListEditor
          idPrefix={`${id}-flow`}
          items={section.flow}
          min={2}
          placeholder="Stage"
          addLabel="Add stage"
          onChange={(flow) => set({ flow })}
        />
      )}

      {section.kind === 'table' && (
        <TableEditor
          idPrefix={`${id}-table`}
          header={section.table.header}
          rows={section.table.rows}
          onChange={(header, rows) => set({ table: { header, rows } })}
        />
      )}

      {section.kind === 'image' && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="label" htmlFor={`${id}-img-url`}>Image URL</label>
            <input
              id={`${id}-img-url`}
              className="input-field"
              value={section.image.url}
              placeholder="https://agenticaiautomation.co/static/…"
              onChange={(e) => set({ image: { ...section.image, url: e.target.value } })}
            />
          </div>
          <div>
            <label className="label" htmlFor={`${id}-img-alt`}>Alt text</label>
            <input
              id={`${id}-img-alt`}
              className="input-field"
              value={section.image.alt}
              onChange={(e) => set({ image: { ...section.image, alt: e.target.value } })}
            />
          </div>
          <div>
            <label className="label" htmlFor={`${id}-img-cap`}>Caption (optional)</label>
            <input
              id={`${id}-img-cap`}
              className="input-field"
              value={section.image.caption}
              onChange={(e) => set({ image: { ...section.image, caption: e.target.value } })}
            />
          </div>
        </div>
      )}

      <div>
        <p className="label">
          Callouts{section.kind === 'callout' ? ' — the first one is this section’s visual' : ''}
        </p>
        <CalloutEditor
          idPrefix={`${id}-co`}
          callouts={section.callouts}
          onChange={(callouts) => set({ callouts })}
        />
      </div>
    </div>
  );
}

export default function PlaybookBuilder({ value, onChange }: Props) {
  const set = (patch: Partial<PlaybookBlocks>) => onChange({ ...value, ...patch });
  const setSection = (index: number, next: PlaybookSection) => {
    const sections = [...value.sections];
    sections[index] = next;
    set({ sections });
  };
  const exampleEmpty =
    !value.example.client.trim() && !value.example.before.trim() &&
    !value.example.after.trim();

  return (
    <div className="space-y-6">
      <Card title="TL;DR and audience">
        <div className="space-y-3">
          {value.tldr.map((bullet, index) => (
            <div key={index}>
              <label className="label" htmlFor={`pb-tldr-${index}`}>
                TL;DR bullet {index + 1}
                {index === 0 ? ' — include the focus keyword' : ''}
              </label>
              <input
                id={`pb-tldr-${index}`}
                className="input-field"
                value={bullet}
                onChange={(e) => {
                  const tldr = [...value.tldr];
                  tldr[index] = e.target.value;
                  set({ tldr });
                }}
              />
            </div>
          ))}
          <div>
            <label className="label" htmlFor="pb-who">Who this is for (one line)</label>
            <input
              id="pb-who"
              className="input-field"
              value={value.who}
              placeholder="clinic owners handling 30+ appointments a day."
              onChange={(e) => set({ who: e.target.value })}
            />
          </div>
        </div>
      </Card>

      <Card
        title={`Question sections · ${value.sections.length}`}
        action={
          <button
            className="btn-secondary text-xs"
            onClick={() => set({ sections: [...value.sections, emptySection()] })}
          >
            Add section
          </button>
        }
      >
        <p className="mb-4 text-xs text-muted">
          At least three. Each one answers a real question in {SECTION_MAX_WORDS} words or
          fewer and carries one visual element.
        </p>
        <div className="space-y-4">
          {value.sections.map((section, index) => (
            <SectionEditor
              key={index}
              section={section}
              index={index}
              total={value.sections.length}
              onChange={(next) => setSection(index, next)}
              onMove={(delta) => {
                const sections = [...value.sections];
                const target = index + delta;
                [sections[index], sections[target]] = [sections[target], sections[index]];
                set({ sections });
              }}
              onRemove={() =>
                set({ sections: value.sections.filter((_, i) => i !== index) })
              }
            />
          ))}
        </div>
      </Card>

      <Card title="Real example">
        <p className="mb-4 text-xs text-muted">
          A real client, never an invented one. Two or three real numbers.
        </p>
        {exampleEmpty && (
          <p className="mb-3 text-xs text-warning">
            Empty — the section is left out of the article until it is filled.
          </p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="label" htmlFor="pb-ex-heading">Section heading (H2)</label>
            <input
              id="pb-ex-heading"
              className="input-field"
              value={value.example.heading}
              onChange={(e) => set({ example: { ...value.example, heading: e.target.value } })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label" htmlFor="pb-ex-client">Client type</label>
            <input
              id="pb-ex-client"
              className="input-field"
              value={value.example.client}
              placeholder="a 3-doctor dental clinic in Pune"
              onChange={(e) => set({ example: { ...value.example, client: e.target.value } })}
            />
          </div>
          <div>
            <label className="label" htmlFor="pb-ex-before">Before</label>
            <textarea
              id="pb-ex-before"
              className="input-field"
              rows={2}
              value={value.example.before}
              onChange={(e) => set({ example: { ...value.example, before: e.target.value } })}
            />
          </div>
          <div>
            <label className="label" htmlFor="pb-ex-after">After</label>
            <textarea
              id="pb-ex-after"
              className="input-field"
              rows={2}
              value={value.example.after}
              onChange={(e) => set({ example: { ...value.example, after: e.target.value } })}
            />
          </div>
          {value.example.metrics.map((metric, index) => (
            <div key={index} className="grid grid-cols-2 gap-2 sm:col-span-2">
              <div>
                <label className="label" htmlFor={`pb-ex-m${index}-l`}>Metric {index + 1}</label>
                <input
                  id={`pb-ex-m${index}-l`}
                  className="input-field"
                  value={metric.label}
                  placeholder="No-shows"
                  onChange={(e) => {
                    const metrics = [...value.example.metrics];
                    metrics[index] = { ...metric, label: e.target.value };
                    set({ example: { ...value.example, metrics } });
                  }}
                />
              </div>
              <div>
                <label className="label" htmlFor={`pb-ex-m${index}-v`}>Value</label>
                <input
                  id={`pb-ex-m${index}-v`}
                  className="input-field"
                  value={metric.value}
                  placeholder="18% to 7% in 14 days"
                  onChange={(e) => {
                    const metrics = [...value.example.metrics];
                    metrics[index] = { ...metric, value: e.target.value };
                    set({ example: { ...value.example, metrics } });
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Cost & time table">
        <div className="space-y-3">
          <div>
            <label className="label" htmlFor="pb-cost-heading">Section heading (H2)</label>
            <input
              id="pb-cost-heading"
              className="input-field"
              value={value.cost.heading}
              onChange={(e) => set({ cost: { ...value.cost, heading: e.target.value } })}
            />
          </div>
          <div>
            <label className="label" htmlFor="pb-cost-intro">Intro line (optional)</label>
            <input
              id="pb-cost-intro"
              className="input-field"
              value={value.cost.intro}
              placeholder="Typical prices for one clinic in India, excluding GST."
              onChange={(e) => set({ cost: { ...value.cost, intro: e.target.value } })}
            />
          </div>
          <TableEditor
            idPrefix="pb-cost"
            fixedHeader
            header={COST_HEADER}
            rows={value.cost.rows.map((r) => [r.item, r.one_time, r.monthly, r.time])}
            onChange={(_, rows) =>
              set({
                cost: {
                  ...value.cost,
                  rows: rows.map((r) => ({
                    item: r[0] ?? '',
                    one_time: r[1] ?? '',
                    monthly: r[2] ?? '',
                    time: r[3] ?? '',
                  })),
                },
              })
            }
          />
        </div>
      </Card>

      <Card title="Call to action">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="pb-cta">Where it sends the reader</label>
            <select
              id="pb-cta"
              className="input-field"
              value={value.cta}
              onChange={(e) => set({ cta: e.target.value as CtaKey })}
            >
              {(Object.keys(CTAS) as Exclude<CtaKey, ''>[]).map((key) => (
                <option key={key} value={key}>{CTAS[key].name}</option>
              ))}
              <option value="">No CTA</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="pb-cta-text">Lead-in (optional)</label>
            <input
              id="pb-cta-text"
              className="input-field"
              value={value.cta_text}
              placeholder="Want to see it on your own booking flow?"
              onChange={(e) => set({ cta_text: e.target.value })}
            />
          </div>
        </div>
        {value.cta && (
          <p className="mt-2 text-xs text-muted">
            Link text: “{CTAS[value.cta].label}” → {CTAS[value.cta].url}
          </p>
        )}
      </Card>
    </div>
  );
}
