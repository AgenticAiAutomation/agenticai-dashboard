/**
 * Blog Playbook — the block model, and the two functions that tie it to the
 * Markdown body the rest of the system already uses.
 *
 *   compose(blocks, title) → markdown      what the writer page saves as body_md
 *   parse(markdown)        → blocks | null best effort, for reopening a body
 *
 * The output is plain Markdown the house scorer, Rank Math and the publisher
 * already read: blockquotes with a bold lead-in instead of HTML <div>s, because
 * strip_markdown() removes `>` and `**` and the scorer then sees clean words.
 * The same conventions are read by api/app/seo/services/skim.py and styled by
 * the site's `playbook_html` filter — change them in all three or none.
 *
 * Safety rule used by the writer page: Playbook mode is only entered when
 * compose(blocks) reproduces the saved body exactly, so switching modes can
 * never silently rewrite an article.
 *
 * No imports and only erasable TypeScript, so `node` can run the tests in
 * web/lib/playbook.test.ts directly.
 */

export type SectionKind = 'text' | 'steps' | 'table' | 'callout' | 'flow' | 'image';
export type CalloutTone = 'tip' | 'warn' | 'pro';
export type CtaKey = 'calendly' | 'whatsapp' | 'wa-funnel' | '';

export interface Callout {
  tone: CalloutTone;
  text: string;
}

export interface PlaybookTable {
  header: string[];
  rows: string[][];
}

export interface PlaybookSection {
  question: string;
  body: string;
  kind: SectionKind;
  steps: string[];
  flow: string[];
  table: PlaybookTable;
  image: { url: string; alt: string; caption: string };
  /* Placed after the section's visual. For kind 'callout' the callouts ARE
     the visual. */
  callouts: Callout[];
}

export interface ExampleMetric {
  label: string;
  value: string;
}

export interface CostRow {
  item: string;
  one_time: string;
  monthly: string;
  time: string;
}

export interface PlaybookBlocks {
  version: 1;
  tldr: string[];
  who: string;
  sections: PlaybookSection[];
  example: {
    heading: string;
    client: string;
    before: string;
    after: string;
    metrics: ExampleMetric[];
  };
  cost: { heading: string; intro: string; rows: CostRow[] };
  cta: CtaKey;
  cta_text: string;
}

export const SECTION_MAX_WORDS = 250;

export const SECTION_KINDS: { value: SectionKind; label: string }[] = [
  { value: 'text', label: 'Text only' },
  { value: 'steps', label: 'Numbered steps' },
  { value: 'table', label: 'Table' },
  { value: 'callout', label: 'Callout' },
  { value: 'flow', label: 'Flow (A → B → C)' },
  { value: 'image', label: 'Image' },
];

export const CALLOUT_LABELS: Record<CalloutTone, string> = {
  tip: 'Tip',
  warn: 'Watch out',
  pro: 'Pro tip',
};

export const CTAS: Record<Exclude<CtaKey, ''>, { label: string; url: string; name: string }> = {
  calendly: {
    name: 'Calendly — book a call',
    label: 'Book a free 30-minute call',
    url: 'https://calendly.com/agenticaiautomation',
  },
  whatsapp: {
    name: 'WhatsApp — message us',
    label: 'Message us on WhatsApp',
    url: 'https://wa.me/917982881739',
  },
  'wa-funnel': {
    name: 'WhatsApp plan funnel',
    label: 'Get your WhatsApp automation plan',
    url: 'https://wa.agenticaiautomation.co',
  },
};

export const COST_HEADER = ['Item', 'One-time', 'Monthly', 'Time'];
export const FROM_AUTHOR_PLACEHOLDER =
  '[FROM AUTHOR: real production story, written by the author]';
const FLOW_ARROW = ' → ';

export function emptySection(): PlaybookSection {
  return {
    question: '',
    body: '',
    kind: 'text',
    steps: [''],
    flow: ['', ''],
    table: { header: ['', ''], rows: [['', '']] },
    image: { url: '', alt: '', caption: '' },
    callouts: [],
  };
}

export function emptyBlocks(): PlaybookBlocks {
  return {
    version: 1,
    tldr: ['', '', ''],
    who: '',
    sections: [emptySection(), emptySection(), emptySection()],
    example: {
      heading: 'What does this look like for a real business?',
      client: '',
      before: '',
      after: '',
      metrics: [
        { label: '', value: '' },
        { label: '', value: '' },
        { label: '', value: '' },
      ],
    },
    cost: {
      heading: 'What does it cost and how long does it take?',
      intro: '',
      rows: [{ item: '', one_time: '', monthly: '', time: '' }],
    },
    cta: 'calendly',
    cta_text: '',
  };
}

export function countWords(text: string): number {
  return (text.match(/[A-Za-z0-9']+/g) || []).length;
}

/* ------------------------------------------------------------------ compose */

/* One line of text: a block's fields are single-line by design. */
function oneLine(value: string): string {
  return (value || '').replace(/\s+/g, ' ').trim();
}

function cell(value: string): string {
  return oneLine(value).replace(/\|/g, '\\|');
}

function tableMd(header: string[], rows: string[][]): string {
  const width = header.length;
  const lines = [
    `| ${header.map(cell).join(' | ')} |`,
    `|${header.map(() => '---').join('|')}|`,
  ];
  for (const row of rows) {
    const padded = Array.from({ length: width }, (_, i) => cell(row[i] ?? ''));
    lines.push(`| ${padded.join(' | ')} |`);
  }
  return lines.join('\n');
}

/* Paragraph text: trailing spaces off, at most one blank line in a row. */
function bodyText(value: string): string {
  return (value || '')
    .split('\n')
    .map((line) => line.replace(/\s+$/, ''))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function rowHasContent(row: string[]): boolean {
  return row.some((c) => oneLine(c) !== '');
}

/* The section's own words — what the 250-word limit and skim score count. */
export function sectionMarkdown(section: PlaybookSection): string {
  const parts: string[] = [];
  const body = bodyText(section.body);
  if (body) parts.push(body);

  if (section.kind === 'steps') {
    const steps = section.steps.map(oneLine).filter(Boolean);
    if (steps.length) parts.push(steps.map((s, i) => `${i + 1}. ${s}`).join('\n'));
  } else if (section.kind === 'table') {
    const header = section.table.header.map(oneLine);
    const rows = section.table.rows.filter(rowHasContent);
    if (header.some(Boolean) && rows.length) parts.push(tableMd(header, rows));
  } else if (section.kind === 'flow') {
    const steps = section.flow.map((s) => oneLine(s).replace(/→/g, '->')).filter(Boolean);
    if (steps.length) parts.push(`> **Flow:** ${steps.join(FLOW_ARROW)}`);
  } else if (section.kind === 'image') {
    const url = oneLine(section.image.url);
    if (url) {
      const alt = oneLine(section.image.alt).replace(/[[\]]/g, '');
      const caption = oneLine(section.image.caption).replace(/\*/g, '');
      parts.push(`![${alt}](${url})` + (caption ? `\n*${caption}*` : ''));
    }
  }

  for (const callout of section.callouts) {
    const text = oneLine(callout.text);
    if (text) parts.push(`> **${CALLOUT_LABELS[callout.tone]}:** ${text}`);
  }
  return parts.join('\n\n');
}

export function compose(blocks: PlaybookBlocks, title: string): string {
  const parts: string[] = [];
  const h1 = oneLine(title);
  if (h1) parts.push(`# ${h1}`);

  // Always emitted, even empty: the TL;DR line is how the publisher and the
  // site recognise a Playbook post.
  const bullets = blocks.tldr.map(oneLine).filter(Boolean);
  parts.push(
    ['> **TL;DR**', ...(bullets.length ? ['>'] : []), ...bullets.map((b) => `> - ${b}`)]
      .join('\n'),
  );

  const who = oneLine(blocks.who);
  if (who) parts.push(`> **Who this is for:** ${who}`);

  for (const section of blocks.sections) {
    const question = oneLine(section.question);
    const content = sectionMarkdown(section);
    if (!question && !content) continue;
    parts.push(`## ${question || 'Untitled section'}`);
    if (content) parts.push(content);
  }

  const ex = blocks.example;
  const metrics = ex.metrics.filter((m) => oneLine(m.label) || oneLine(m.value));
  if (oneLine(ex.client) || oneLine(ex.before) || oneLine(ex.after) || metrics.length) {
    parts.push(`## ${oneLine(ex.heading) || 'A real example'}`);
    const lines = [`> **Real example:** ${oneLine(ex.client)}`.trimEnd()];
    if (oneLine(ex.before)) lines.push('>', `> **Before:** ${oneLine(ex.before)}`);
    if (oneLine(ex.after)) lines.push('>', `> **After:** ${oneLine(ex.after)}`);
    if (metrics.length) {
      lines.push('>');
      for (const m of metrics) {
        lines.push(`> - **${oneLine(m.label).replace(/\*/g, '')}:** ${oneLine(m.value)}`);
      }
    }
    parts.push(lines.join('\n'));
  }

  const costRows = blocks.cost.rows
    .map((r) => [r.item, r.one_time, r.monthly, r.time])
    .filter(rowHasContent);
  if (costRows.length) {
    parts.push(`## ${oneLine(blocks.cost.heading) || 'What does it cost?'}`);
    const intro = bodyText(blocks.cost.intro);
    if (intro) parts.push(intro);
    parts.push(tableMd(COST_HEADER, costRows));
  }

  parts.push(FROM_AUTHOR_PLACEHOLDER);

  if (blocks.cta) {
    const cta = CTAS[blocks.cta];
    const lead = oneLine(blocks.cta_text);
    parts.push(`> **Next step:** ${lead ? `${lead} ` : ''}[${cta.label}](${cta.url})`);
  }

  return parts.join('\n\n') + '\n';
}

/* -------------------------------------------------------------------- parse */

const RE_CALLOUT = /^> \*\*(Tip|Watch out|Pro tip):\*\* (.*)$/;
const RE_FLOW = /^> \*\*Flow:\*\* (.*)$/;
const RE_IMAGE = /^!\[([^\]]*)\]\(([^)\s]+)\)$/;
const RE_STEP = /^(\d+)\. (.*)$/;
const RE_METRIC = /^> - \*\*([^*]*):\*\* ?(.*)$/;

function splitRow(line: string): string[] {
  const inner = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  // Split on pipes that are not escaped as \| (cell() escapes them).
  const cells: string[] = [];
  let current = '';
  for (let k = 0; k < inner.length; k += 1) {
    if (inner[k] === '\\' && inner[k + 1] === '|') {
      current += '|';
      k += 1;
    } else if (inner[k] === '|') {
      cells.push(current.trim());
      current = '';
    } else {
      current += inner[k];
    }
  }
  cells.push(current.trim());
  return cells;
}

function parseTable(chunk: string): PlaybookTable | null {
  const lines = chunk.split('\n');
  if (lines.length < 3 || !lines.every((l) => l.startsWith('|'))) return null;
  if (!/^\|(?:\s*:?-{3,}:?\s*\|)+$/.test(lines[1].replace(/\s/g, ''))) return null;
  return { header: splitRow(lines[0]), rows: lines.slice(2).map(splitRow) };
}

function isBodyChunk(chunk: string): boolean {
  return !/^(#|>|\||!\[|\d+\. |[-*+] )/.test(chunk) &&
    !chunk.startsWith('[FROM AUTHOR');
}

const CALLOUT_TONES: Record<string, CalloutTone> = {
  Tip: 'tip',
  'Watch out': 'warn',
  'Pro tip': 'pro',
};

/**
 * Best effort. Returns null for anything that does not follow the composer's
 * conventions exactly — the writer page then stays in the raw editor. The
 * page also checks compose(parse(md)) === md before switching modes.
 */
export function parse(markdown: string): { title: string; blocks: PlaybookBlocks } | null {
  const chunks = (markdown || '')
    .replace(/\r\n/g, '\n')
    .split(/\n{2,}/)
    .map((c) => c.trim())
    .filter(Boolean);
  const blocks = emptyBlocks();
  blocks.sections = [];
  blocks.example.metrics = [];
  blocks.cost.rows = [];
  blocks.cta = '';
  let i = 0;

  let title = '';
  if (chunks[i]?.startsWith('# ')) {
    title = chunks[i].slice(2).trim();
    i += 1;
  }

  // TL;DR — required; it is what makes this a Playbook post.
  const tldr = chunks[i]?.split('\n');
  if (!tldr || tldr[0] !== '> **TL;DR**') return null;
  const bullets: string[] = [];
  for (const line of tldr.slice(1)) {
    if (line === '>') continue;
    if (!line.startsWith('> - ')) return null;
    bullets.push(line.slice(4).trim());
  }
  blocks.tldr = [...bullets, '', '', ''].slice(0, Math.max(3, bullets.length));
  i += 1;

  if (chunks[i]?.startsWith('> **Who this is for:** ') && !chunks[i].includes('\n')) {
    blocks.who = chunks[i].slice('> **Who this is for:** '.length).trim();
    i += 1;
  }

  while (i < chunks.length && chunks[i].startsWith('## ')) {
    const heading = chunks[i].slice(3).trim();
    const next = chunks[i + 1] ?? '';

    // The real example section.
    if (next.startsWith('> **Real example:**')) {
      blocks.example.heading = heading;
      for (const line of next.split('\n')) {
        let m: RegExpMatchArray | null;
        if (line === '>') continue;
        if (line.startsWith('> **Real example:**')) {
          blocks.example.client = line.slice('> **Real example:**'.length).trim();
        } else if (line.startsWith('> **Before:** ')) {
          blocks.example.before = line.slice('> **Before:** '.length).trim();
        } else if (line.startsWith('> **After:** ')) {
          blocks.example.after = line.slice('> **After:** '.length).trim();
        } else if ((m = line.match(RE_METRIC))) {
          blocks.example.metrics.push({ label: m[1].trim(), value: m[2].trim() });
        } else {
          return null;
        }
      }
      i += 2;
      continue;
    }

    // The cost section: optional intro, then the four-column cost table, and
    // nothing but the author placeholder or CTA after it.
    const costAt = [i + 1, i + 2].find((k) => {
      const t = chunks[k] ? parseTable(chunks[k]) : null;
      return t !== null && t.header.join('|') === COST_HEADER.join('|');
    });
    if (costAt !== undefined && (chunks[costAt + 1] ?? '').startsWith('[FROM AUTHOR')) {
      if (costAt === i + 2) {
        if (!isBodyChunk(chunks[i + 1])) return null;
        blocks.cost.intro = chunks[i + 1];
      }
      blocks.cost.heading = heading;
      const table = parseTable(chunks[costAt])!;
      blocks.cost.rows = table.rows.map((r) => ({
        item: r[0] ?? '',
        one_time: r[1] ?? '',
        monthly: r[2] ?? '',
        time: r[3] ?? '',
      }));
      i = costAt + 1;
      continue;
    }

    // An ordinary question section.
    const section = emptySection();
    section.question = heading === 'Untitled section' ? '' : heading;
    i += 1;
    const body: string[] = [];
    while (i < chunks.length && isBodyChunk(chunks[i])) {
      body.push(chunks[i]);
      i += 1;
    }
    section.body = body.join('\n\n');

    const chunk = chunks[i] ?? '';
    const lines = chunk.split('\n');
    let m: RegExpMatchArray | null;
    let table: PlaybookTable | null;
    if (chunk && lines.every((l) => RE_STEP.test(l))) {
      section.kind = 'steps';
      section.steps = lines.map((l) => l.replace(RE_STEP, '$2').trim());
      i += 1;
    } else if (chunk && (table = parseTable(chunk))) {
      section.kind = 'table';
      section.table = table;
      i += 1;
    } else if (lines.length === 1 && (m = chunk.match(RE_FLOW))) {
      section.kind = 'flow';
      section.flow = m[1].split(FLOW_ARROW).map((s) => s.trim());
      i += 1;
    } else if ((m = lines[0].match(RE_IMAGE)) && lines.length <= 2) {
      const caption = lines[1] ?? '';
      if (caption && !/^\*[^*]+\*$/.test(caption)) return null;
      section.kind = 'image';
      section.image = { alt: m[1], url: m[2], caption: caption.slice(1, -1) };
      i += 1;
    }

    while (i < chunks.length && (m = chunks[i].match(RE_CALLOUT)) && !chunks[i].includes('\n')) {
      section.callouts.push({ tone: CALLOUT_TONES[m[1]], text: m[2].trim() });
      i += 1;
    }
    if (section.kind === 'text' && section.callouts.length) section.kind = 'callout';
    blocks.sections.push(section);
  }

  if (chunks[i] !== FROM_AUTHOR_PLACEHOLDER) return null;
  i += 1;

  if (i < chunks.length) {
    const m = chunks[i].match(/^> \*\*Next step:\*\* (?:(.*) )?\[([^\]]+)\]\(([^)\s]+)\)$/);
    if (!m) return null;
    const key = (Object.keys(CTAS) as Exclude<CtaKey, ''>[]).find(
      (k) => CTAS[k].url === m[3] && CTAS[k].label === m[2],
    );
    if (!key) return null;
    blocks.cta = key;
    blocks.cta_text = (m[1] ?? '').trim();
    i += 1;
  }
  if (i !== chunks.length) return null;

  // Keep the editor's empty rows so the form is never missing its inputs.
  if (!blocks.example.metrics.length) blocks.example.metrics = emptyBlocks().example.metrics;
  if (!blocks.cost.rows.length) blocks.cost.rows = emptyBlocks().cost.rows;
  if (!blocks.sections.length) blocks.sections = [emptySection()];
  return { title, blocks };
}

/* ---------------------------------------------------------------- normalise */

function str(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function strList(value: unknown, min: number): string[] {
  const list = Array.isArray(value) ? value.map(str) : [];
  while (list.length < min) list.push('');
  return list;
}

/**
 * Coerce stored or AI-generated blocks into the exact shape the builder
 * edits. Anything missing gets the empty default, so a half-formed document
 * can never crash the page. Returns null for something that is not a block
 * document at all.
 */
export function normaliseBlocks(raw: unknown): PlaybookBlocks | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const r = raw as Record<string, any>;
  const base = emptyBlocks();
  const kinds = SECTION_KINDS.map((k) => k.value);
  const tones = Object.keys(CALLOUT_LABELS);

  const sections = Array.isArray(r.sections)
    ? r.sections.filter((s: unknown) => s && typeof s === 'object').map((s: any) => {
        const header = strList(s.table?.header, 2);
        return {
          question: str(s.question),
          body: str(s.body),
          kind: (kinds.indexOf(s.kind) >= 0 ? s.kind : 'text') as SectionKind,
          steps: strList(s.steps, 1),
          flow: strList(s.flow, 2),
          table: {
            header,
            rows: Array.isArray(s.table?.rows) && s.table.rows.length
              ? s.table.rows.map((row: unknown) => {
                  const cells = strList(row, header.length);
                  return cells.slice(0, header.length);
                })
              : [header.map(() => '')],
          },
          image: { url: str(s.image?.url), alt: str(s.image?.alt), caption: str(s.image?.caption) },
          callouts: Array.isArray(s.callouts)
            ? s.callouts.map((c: any) => ({
                tone: (tones.indexOf(c?.tone) >= 0 ? c.tone : 'tip') as CalloutTone,
                text: str(c?.text),
              }))
            : [],
        };
      })
    : [];

  const ex = r.example && typeof r.example === 'object' ? r.example : {};
  const metrics = Array.isArray(ex.metrics)
    ? ex.metrics.map((m: any) => ({ label: str(m?.label), value: str(m?.value) }))
    : [];
  while (metrics.length < 3) metrics.push({ label: '', value: '' });

  const cost = r.cost && typeof r.cost === 'object' ? r.cost : {};
  const rows = Array.isArray(cost.rows)
    ? cost.rows.map((row: any) => ({
        item: str(row?.item),
        one_time: str(row?.one_time),
        monthly: str(row?.monthly),
        time: str(row?.time),
      }))
    : [];

  return {
    version: 1,
    tldr: strList(r.tldr, 3),
    who: str(r.who),
    sections: sections.length ? sections : base.sections,
    example: {
      heading: str(ex.heading) || base.example.heading,
      client: str(ex.client),
      before: str(ex.before),
      after: str(ex.after),
      metrics,
    },
    cost: {
      heading: str(cost.heading) || base.cost.heading,
      intro: str(cost.intro),
      rows: rows.length ? rows : base.cost.rows,
    },
    cta: (r.cta === '' || r.cta in CTAS ? r.cta : 'calendly') as CtaKey,
    cta_text: str(r.cta_text),
  };
}

/**
 * Decide how an existing body opens. Returns the blocks to show in Playbook
 * mode, or null for the raw editor. Never returns blocks whose composition
 * differs from the body — that is the "never silently rewrite" guarantee.
 */
export function blocksForBody(
  body: string,
  title: string,
  saved: unknown,
): PlaybookBlocks | null {
  try {
    const stored = normaliseBlocks(saved);
    if (stored && compose(stored, title) === body) return stored;
    const parsed = parse(body);
    if (parsed && compose(parsed.blocks, title) === body) return parsed.blocks;
  } catch {
    /* Anything unexpected means the raw editor, which is always safe. */
  }
  return null;
}
