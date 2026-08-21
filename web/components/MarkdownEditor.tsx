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

export type LinkTarget = {
  url: string;
  label: string;
  /* "site" = a marketing page, "article" = a published blog post. Both count
     as internal links for scoring; the grouping just helps the writer choose. */
  group: 'site' | 'article';
};

type Props = {
  value: string;
  onChange: (next: string) => void;
  rows?: number;
  id?: string;
  /* Internal pages and published articles the writer can link to. Both scorers
     award points for internal links, and the no-orphan rule needs articles to
     link to each other, so this list is how a writer satisfies both without
     memorising URLs. */
  linkTargets?: LinkTarget[];
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

export default function MarkdownEditor({
  value,
  onChange,
  rows = 26,
  id = 'body',
  linkTargets = [],
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [showLinkPicker, setShowLinkPicker] = useState(false);
  const [externalUrl, setExternalUrl] = useState('https://');
  const [pendingSelection, setPendingSelection] =
    useState<{ start: number; end: number; text: string } | null>(null);

  /* Insert the link using the selection captured when the picker opened —
     clicking into the panel blurs the textarea and loses the live selection. */
  const insertLink = useCallback(
    (url: string) => {
      const el = ref.current;
      const sel = pendingSelection;
      if (!el || !sel) return;

      const text = sel.text || 'link text';
      const snippet = `[${text}](${url})`;
      onChange(value.slice(0, sel.start) + snippet + value.slice(sel.end));

      setShowLinkPicker(false);
      setPendingSelection(null);
      requestAnimationFrame(() => {
        el.focus();
        // Select the anchor text so it can be typed over straight away.
        el.setSelectionRange(sel.start + 1, sel.start + 1 + text.length);
      });
    },
    [pendingSelection, value, onChange],
  );

  const internalTargets = linkTargets.filter((t) => t.group === 'site');
  const articleTargets = linkTargets.filter((t) => t.group === 'article');

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
        // Opening the picker instead of prompting: the writer needs to see the
        // internal pages and published articles, not recall their URLs.
        setPendingSelection({ start, end, text: selected });
        setShowLinkPicker(true);
        return;
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

      {showLinkPicker && (
        <div className="mb-3 p-3 bg-raised border border-line rounded-lg">
          <div className="flex justify-between items-center mb-3">
            <p className="card-title">
              Insert link
              {pendingSelection?.text ? ` around "${pendingSelection.text}"` : ''}
            </p>
            <button
              className="text-xs text-muted hover:text-white"
              onClick={() => { setShowLinkPicker(false); setPendingSelection(null); }}
            >
              Cancel
            </button>
          </div>

          {internalTargets.length > 0 && (
            <>
              <p className="text-xs text-muted mb-1.5">
                Site pages — internal links are worth 3 points in each scorer
              </p>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {internalTargets.map((t) => (
                  <button
                    key={t.url}
                    onClick={() => insertLink(t.url)}
                    title={t.url}
                    className="px-2 py-1 rounded text-xs border border-line
                               bg-surface text-slate-200 hover:bg-line hover:text-white"
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </>
          )}

          <p className="text-xs text-muted mb-1.5">
            Published articles
            {articleTargets.length === 0 && ' — none yet, so link to a site page above'}
          </p>
          {articleTargets.length > 0 && (
            <div className="flex flex-col gap-1 mb-3 max-h-40 overflow-auto">
              {articleTargets.map((t) => (
                <button
                  key={t.url}
                  onClick={() => insertLink(t.url)}
                  title={t.url}
                  className="text-left px-2 py-1 rounded text-xs border border-line
                             bg-surface text-slate-200 hover:bg-line hover:text-white"
                >
                  {t.label}
                </button>
              ))}
            </div>
          )}

          <p className="text-xs text-muted mb-1.5">
            External URL — cite an authoritative source; worth 2 to 3 points
          </p>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="externalUrl">External URL</label>
            <input
              id="externalUrl"
              className="input-field text-xs"
              value={externalUrl}
              onChange={(e) => setExternalUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); insertLink(externalUrl); }
              }}
              placeholder="https://developers.facebook.com/docs/whatsapp"
            />
            <button
              className="btn-secondary text-xs whitespace-nowrap"
              onClick={() => insertLink(externalUrl)}
              disabled={!/^https?:\/\/.+\..+/.test(externalUrl)}
            >
              Insert
            </button>
          </div>
        </div>
      )}

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
