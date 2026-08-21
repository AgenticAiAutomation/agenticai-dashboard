'use client';

import { useCallback, useRef, useState } from 'react';

/**
 * Markdown editor with a formatting toolbar and live preview.
 *
 * Deliberately not a WYSIWYG/contenteditable editor. The body is stored as
 * markdown and converted to HTML at publish time, and every scoring check —
 * heading hierarchy, internal vs external links, image alt text — reads that
 * markdown. A rich-text editor that emitted its own HTML would put the score
 * and the published article out of step with each other.
 *
 * The toolbar wraps or prefixes the current selection, so the writer never has
 * to remember the syntax, and keyboard shortcuts match what people expect from
 * a word processor.
 */

type Props = {
  value: string;
  onChange: (next: string) => void;
  rows?: number;
  id?: string;
};

type Action =
  | { kind: 'prefix'; token: string }        // headings, quotes, list items
  | { kind: 'wrap'; before: string; after: string }
  | { kind: 'link' }
  | { kind: 'image' };

const TOOLBAR: { label: string; title: string; action: Action; mono?: boolean }[] = [
  { label: 'H1', title: 'Heading 1 — one per article', action: { kind: 'prefix', token: '# ' } },
  { label: 'H2', title: 'Heading 2 — main sections', action: { kind: 'prefix', token: '## ' } },
  { label: 'H3', title: 'Heading 3 — sub-sections', action: { kind: 'prefix', token: '### ' } },
  { label: 'B', title: 'Bold (Ctrl+B)', action: { kind: 'wrap', before: '**', after: '**' } },
  { label: 'I', title: 'Italic (Ctrl+I)', action: { kind: 'wrap', before: '_', after: '_' } },
  { label: 'Link', title: 'Insert link (Ctrl+K)', action: { kind: 'link' } },
  { label: 'Image', title: 'Insert image with alt text', action: { kind: 'image' } },
  { label: 'List', title: 'Bulleted list', action: { kind: 'prefix', token: '- ' } },
  { label: '1.', title: 'Numbered list', action: { kind: 'prefix', token: '1. ' } },
  { label: 'Quote', title: 'Block quote', action: { kind: 'prefix', token: '> ' } },
  { label: 'Code', title: 'Inline code', action: { kind: 'wrap', before: '`', after: '`' }, mono: true },
];

/* Minimal markdown -> HTML for the preview pane only. The server does the real
   conversion at publish time; this exists so the writer can see structure
   without a round trip, and deliberately escapes HTML first so a draft can
   never inject markup into the dashboard. */
function renderPreview(markdown: string): string {
  const escaped = markdown
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const lines = escaped.split('\n');
  const out: string[] = [];
  let inList: 'ul' | 'ol' | null = null;

  const closeList = () => {
    if (inList) {
      out.push(`</${inList}>`);
      inList = null;
    }
  };

  const inline = (text: string) =>
    text
      .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g,
        '<img src="$2" alt="$1" style="max-width:100%;border-radius:4px" />')
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^_])_([^_]+)_/g, '$1<em>$2</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');

  for (const line of lines) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeList();
      const level = heading[1].length;
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      if (inList !== 'ul') { closeList(); out.push('<ul>'); inList = 'ul'; }
      out.push(`<li>${inline(line.replace(/^[-*]\s+/, ''))}</li>`);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      if (inList !== 'ol') { closeList(); out.push('<ol>'); inList = 'ol'; }
      out.push(`<li>${inline(line.replace(/^\d+\.\s+/, ''))}</li>`);
      continue;
    }
    if (/^>\s?/.test(line)) {
      closeList();
      out.push(`<blockquote>${inline(line.replace(/^>\s?/, ''))}</blockquote>`);
      continue;
    }
    if (!line.trim()) { closeList(); continue; }
    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  return out.join('\n');
}

export default function MarkdownEditor({ value, onChange, rows = 26, id = 'body' }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [showPreview, setShowPreview] = useState(false);

  const apply = useCallback(
    (action: Action) => {
      const el = ref.current;
      if (!el) return;

      const start = el.selectionStart;
      const end = el.selectionEnd;
      const selected = value.slice(start, end);
      let next = value;
      let caretStart = start;
      let caretEnd = end;

      if (action.kind === 'prefix') {
        // Operate on whole lines: find the start of the line the cursor is on.
        const lineStart = value.lastIndexOf('\n', start - 1) + 1;
        const lineEnd = value.indexOf('\n', end);
        const sliceEnd = lineEnd === -1 ? value.length : lineEnd;
        const block = value.slice(lineStart, sliceEnd);

        // Toggle: strip an existing marker of any heading/list type first so
        // clicking H2 on an H1 line replaces it rather than stacking markers.
        const stripped = block
          .split('\n')
          .map((l) => l.replace(/^(#{1,6}\s+|[-*]\s+|\d+\.\s+|>\s?)/, ''))
          .join('\n');
        const alreadyApplied = block
          .split('\n')
          .every((l) => l.startsWith(action.token));
        const updated = alreadyApplied
          ? stripped
          : stripped.split('\n').map((l) => action.token + l).join('\n');

        next = value.slice(0, lineStart) + updated + value.slice(sliceEnd);
        caretStart = lineStart;
        caretEnd = lineStart + updated.length;
      } else if (action.kind === 'wrap') {
        const { before, after } = action;
        const already =
          value.slice(start - before.length, start) === before &&
          value.slice(end, end + after.length) === after;
        if (already) {
          next =
            value.slice(0, start - before.length) +
            selected +
            value.slice(end + after.length);
          caretStart = start - before.length;
          caretEnd = caretStart + selected.length;
        } else {
          next = value.slice(0, start) + before + selected + after + value.slice(end);
          caretStart = start + before.length;
          caretEnd = caretStart + selected.length;
        }
      } else if (action.kind === 'link') {
        const url = window.prompt(
          'Link URL — use /services for an internal page, https://… for external',
          'https://',
        );
        if (!url) return;
        const text = selected || 'link text';
        const snippet = `[${text}](${url})`;
        next = value.slice(0, start) + snippet + value.slice(end);
        // Select the link text so it can be typed over immediately.
        caretStart = start + 1;
        caretEnd = caretStart + text.length;
      } else {
        const url = window.prompt('Image URL', 'https://');
        if (!url) return;
        const alt = window.prompt(
          'Alt text — describe the image. Required: images without alt text lose points.',
          selected || '',
        );
        if (alt === null) return;
        const snippet = `![${alt}](${url})`;
        next = value.slice(0, start) + snippet + value.slice(end);
        caretStart = start + snippet.length;
        caretEnd = caretStart;
      }

      onChange(next);
      requestAnimationFrame(() => {
        el.focus();
        el.setSelectionRange(caretStart, caretEnd);
      });
    },
    [value, onChange],
  );

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    const key = event.key.toLowerCase();
    const shortcuts: Record<string, Action> = {
      b: { kind: 'wrap', before: '**', after: '**' },
      i: { kind: 'wrap', before: '_', after: '_' },
      k: { kind: 'link' },
    };
    if (shortcuts[key]) {
      event.preventDefault();
      apply(shortcuts[key]);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-1 mb-2 pb-2 border-b border-line">
        {TOOLBAR.map((item) => (
          <button
            key={item.label}
            type="button"
            title={item.title}
            aria-label={item.title}
            onClick={() => apply(item.action)}
            className={`px-2 py-1 rounded text-xs border border-line bg-raised
                        text-slate-200 hover:bg-line hover:text-white transition-colors
                        ${item.mono ? 'font-mono' : ''}
                        ${item.label === 'B' ? 'font-bold' : ''}
                        ${item.label === 'I' ? 'italic' : ''}`}
          >
            {item.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setShowPreview(!showPreview)}
          aria-pressed={showPreview}
          className="ml-auto px-2 py-1 rounded text-xs border border-line
                     bg-raised text-slate-200 hover:bg-line hover:text-white"
        >
          {showPreview ? 'Edit' : 'Preview'}
        </button>
      </div>

      {showPreview ? (
        <div
          className="input-field prose-preview overflow-auto"
          style={{ minHeight: `${rows * 1.5}rem` }}
          dangerouslySetInnerHTML={{ __html: renderPreview(value) }}
        />
      ) : (
        <textarea
          id={id}
          ref={ref}
          className="input-field font-mono text-sm leading-relaxed"
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            '# Your headline\n\n' +
            'Select text and press H2 for a section, or Ctrl+K to add a link.\n\n' +
            '## A section\n\n' +
            'Internal link: [our services](/services)\n' +
            'External link: [the docs](https://example.com)'
          }
        />
      )}
    </div>
  );
}
