'use client';

/* Inline rich text: a contenteditable whose DOM is serialised to runs with
   marks. HTML never leaves this component; the server only ever sees
   {text, marks}. Paste from Word / Google Docs / another site is walked the
   same way, so font-weight:700 becomes a bold mark and every style, class and
   span wrapper is dropped.

   The contenteditable is uncontrolled while focused (React re-rendering the
   DOM under a caret loses the caret). Props drive it only when the block is
   replaced from outside — a revision restore — via `version`. */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { EmphasisToken, HighlightToken, Mark, MarkType, RichText } from '@/lib/blocks';

const HIGHLIGHTS: HighlightToken[] = ['amber', 'mint', 'sky', 'rose'];
const EMPHASES: EmphasisToken[] = ['brand', 'accent', 'positive', 'warning'];
const HL_COLOR: Record<HighlightToken, string> = { amber: '#ffd400', mint: '#7ff0b8', sky: '#8ed0ff', rose: '#ffb3c1' };
const EM_COLOR: Record<EmphasisToken, string> = { brand: '#ff7d33', accent: '#ffd400', positive: '#2fd07f', warning: '#ffa23a' };

/* ---------- runs -> DOM ---------- */
function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
const ORDER: MarkType[] = ['link', 'highlight', 'emphasis', 'code', 'bold', 'italic', 'underline', 'strike', 'sup', 'sub'];

function open(m: Mark): string {
  switch (m.type) {
    case 'link': return `<a href="${esc(m.attrs?.href || '')}" data-rel="${esc(m.attrs?.rel || '')}">`;
    case 'highlight': return `<mark data-token="${esc(m.attrs?.token || 'amber')}" style="background:${HL_COLOR[(m.attrs?.token as HighlightToken) || 'amber']};color:#170800;padding:0 .2em;border-radius:2px">`;
    case 'emphasis': return `<span data-em="${esc(m.attrs?.token || 'brand')}" style="color:${EM_COLOR[(m.attrs?.token as EmphasisToken) || 'brand']}">`;
    case 'bold': return '<strong>';
    case 'italic': return '<em>';
    case 'underline': return '<u>';
    case 'strike': return '<s>';
    case 'code': return '<code>';
    case 'sup': return '<sup>';
    case 'sub': return '<sub>';
  }
}
function close(m: Mark): string {
  return { link: '</a>', highlight: '</mark>', emphasis: '</span>', bold: '</strong>', italic: '</em>',
    underline: '</u>', strike: '</s>', code: '</code>', sup: '</sup>', sub: '</sub>' }[m.type];
}

export function runsToHtml(runs: RichText): string {
  return runs.map((r) => {
    const marks = [...(r.marks || [])].sort((a, b) => ORDER.indexOf(a.type) - ORDER.indexOf(b.type));
    return marks.map(open).join('') + esc(r.text).replace(/\n/g, '<br>') + [...marks].reverse().map(close).join('');
  }).join('');
}

/* ---------- DOM -> runs ---------- */
function marksFor(el: HTMLElement, inherited: Mark[]): Mark[] {
  const out = [...inherited];
  const tag = el.tagName.toLowerCase();
  const style = el.getAttribute('style') || '';
  const weight = el.style?.fontWeight || (style.match(/font-weight:\s*(\w+)/)?.[1] ?? '');
  const add = (m: Mark) => { if (!out.some((x) => x.type === m.type)) out.push(m); };
  if (tag === 'strong' || tag === 'b' || weight === 'bold' || (parseInt(weight, 10) || 0) >= 600) add({ type: 'bold' });
  if (tag === 'em' || tag === 'i' || /font-style:\s*italic/.test(style)) add({ type: 'italic' });
  if (tag === 'u' || /text-decoration[^;]*underline/.test(style)) add({ type: 'underline' });
  if (tag === 's' || tag === 'strike' || tag === 'del' || /line-through/.test(style)) add({ type: 'strike' });
  if (tag === 'code') add({ type: 'code' });
  if (tag === 'sup') add({ type: 'sup' });
  if (tag === 'sub') add({ type: 'sub' });
  if (tag === 'mark') add({ type: 'highlight', attrs: { token: el.getAttribute('data-token') || 'amber' } });
  if (tag === 'span' && el.getAttribute('data-em')) add({ type: 'emphasis', attrs: { token: el.getAttribute('data-em') as string } });
  if (tag === 'a') {
    const href = el.getAttribute('href') || '';
    if (/^(https?:\/\/|\/|#|mailto:)/.test(href)) {
      const attrs: Record<string, string> = { href };
      const rel = el.getAttribute('data-rel') || '';
      if (rel) attrs.rel = rel;
      add({ type: 'link', attrs });
    }
  }
  return out;
}

const BLOCK_TAGS = new Set(['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'blockquote', 'pre']);

/* A block-level piece of pasted content: its runs and where it came from,
   so a pasted <li> can become a list item and an <h2> a heading. */
export interface Segment { runs: RichText; tag: string; ordered?: boolean }

/* Serialise a node tree into block-level segments, so a paste of three
   paragraphs yields three entries. */
export function domToSegments(root: Node): Segment[] {
  const segments: Segment[] = [{ runs: [], tag: 'p' }];
  const listStack: boolean[] = [];   // true = ordered
  const push = (text: string, marks: Mark[]) => {
    if (!text) return;
    const seg = segments[segments.length - 1].runs;
    const last = seg[seg.length - 1];
    const same = last && JSON.stringify(last.marks || []) === JSON.stringify(marks);
    if (same) last.text += text;
    else seg.push(marks.length ? { text, marks } : { text });
  };
  const open = (tag: string) => {
    const cur = segments[segments.length - 1];
    if (cur.runs.length) segments.push({ runs: [], tag });
    else cur.tag = tag;
    if (tag === 'li') segments[segments.length - 1].ordered = listStack[listStack.length - 1] ?? false;
  };
  const walk = (node: Node, marks: Mark[]) => {
    if (node.nodeType === Node.TEXT_NODE) {
      push((node.textContent || '').replace(/\u00a0/g, ' '), marks);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node as HTMLElement;
    const tag = el.tagName.toLowerCase();
    if (tag === 'br') { push('\n', marks); return; }
    if (tag === 'script' || tag === 'style' || tag === 'meta' || tag === 'img') return;
    if (tag === 'ul' || tag === 'ol') listStack.push(tag === 'ol');
    const isBlock = BLOCK_TAGS.has(tag);
    if (isBlock) open(tag);
    const m = marksFor(el, marks);
    el.childNodes.forEach((c) => walk(c, m));
    if (isBlock && segments[segments.length - 1].runs.length) segments.push({ runs: [], tag: 'p' });
    if (tag === 'ul' || tag === 'ol') listStack.pop();
  };
  walk(root, []);
  return segments
    .map((s) => ({ ...s, runs: s.runs.map((r) => ({ ...r, text: r.text.replace(/[ \t]+/g, ' ') })).filter((r) => r.text) }))
    .filter((s) => s.runs.length && s.runs.some((r) => r.text.trim()))
    .map((s) => {
      s.runs[0].text = s.runs[0].text.replace(/^\s+/, '');
      s.runs[s.runs.length - 1].text = s.runs[s.runs.length - 1].text.replace(/\s+$/, '');
      return s;
    });
}

export function domToRuns(root: Node): RichText[] {
  return domToSegments(root).map((s) => s.runs);
}

/* ---------- component ---------- */
export interface RichTextProps {
  value: RichText;
  onChange: (runs: RichText) => void;
  /* Bump to force the DOM to resync from `value` (restore, undo). */
  version?: number;
  placeholder?: string;
  className?: string;
  singleLine?: boolean;
  readOnly?: boolean;
  /* Enter with a non-empty block: split at the caret. */
  onSplit?: (before: RichText, after: RichText) => void;
  /* Backspace at the start of an empty block. */
  onDeleteEmpty?: () => void;
  /* Pasted content that spans several blocks. */
  onPasteBlocks?: (segments: Segment[]) => void;
  /* "/" typed into an empty block. */
  onSlash?: () => void;
  autoFocus?: boolean;
}

export default function RichText({
  value, onChange, version = 0, placeholder, className = '', singleLine = false,
  readOnly = false, onSplit, onDeleteEmpty, onPasteBlocks, onSlash, autoFocus,
}: RichTextProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [toolbar, setToolbar] = useState<{ x: number; y: number } | null>(null);
  const [linkDraft, setLinkDraft] = useState<string | null>(null);
  const [empty, setEmpty] = useState(!plain(value));

  // Sync DOM from props only when the block identity/version changes.
  useEffect(() => {
    if (!ref.current) return;
    ref.current.innerHTML = runsToHtml(value);
    setEmpty(!plain(value));
    if (autoFocus) ref.current.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const emit = useCallback(() => {
    if (!ref.current) return;
    const segs = domToRuns(ref.current);
    const runs = segs.length ? segs.flatMap((s, i) => (i ? [{ text: '\n' }, ...s] : s)) : [];
    setEmpty(!plain(runs));
    onChange(runs);
  }, [onChange]);

  const selectionInside = () => {
    const sel = window.getSelection();
    return !!(sel && sel.rangeCount && ref.current && ref.current.contains(sel.anchorNode));
  };

  const showToolbar = () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !selectionInside()) { setToolbar(null); return; }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const host = ref.current!.getBoundingClientRect();
    setToolbar({ x: rect.left - host.left + rect.width / 2, y: rect.top - host.top - 40 });
  };

  const wrapSelection = (tag: string, attrs: Record<string, string> = {}) => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !selectionInside()) return;
    const range = sel.getRangeAt(0);
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    try {
      range.surroundContents(el);
    } catch {
      el.appendChild(range.extractContents());
      range.insertNode(el);
    }
    sel.removeAllRanges();
    emit();
    setToolbar(null);
  };

  const toggle = (cmd: 'bold' | 'italic' | 'underline' | 'strikeThrough') => {
    if (!selectionInside()) return;
    document.execCommand(cmd);
    emit();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (readOnly) return;
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey) {
      const k = e.key.toLowerCase();
      if (k === 'b') { e.preventDefault(); toggle('bold'); return; }
      if (k === 'i') { e.preventDefault(); toggle('italic'); return; }
      if (k === 'u') { e.preventDefault(); toggle('underline'); return; }
      if (k === 'k') { e.preventDefault(); setLinkDraft('https://'); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      if (singleLine) { e.preventDefault(); return; }
      if (onSplit) {
        e.preventDefault();
        const sel = window.getSelection();
        if (!sel || !ref.current) return;
        const r = sel.getRangeAt(0);
        const before = document.createRange();
        before.setStart(ref.current, 0); before.setEnd(r.startContainer, r.startOffset);
        const after = document.createRange();
        after.setStart(r.endContainer, r.endOffset); after.setEnd(ref.current, ref.current.childNodes.length);
        const b = document.createElement('div'); b.appendChild(before.cloneContents());
        const a = document.createElement('div'); a.appendChild(after.cloneContents());
        const bs = domToRuns(b).flat(); const as = domToRuns(a).flat();
        onSplit(bs, as);
      }
      return;
    }
    if (e.key === 'Backspace' && onDeleteEmpty && ref.current && !plain(domToRuns(ref.current).flat())) {
      e.preventDefault();
      onDeleteEmpty();
      return;
    }
    if (e.key === '/' && onSlash && ref.current && !plain(domToRuns(ref.current).flat())) {
      e.preventDefault();
      onSlash();
    }
  };

  const onPaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    if (readOnly) return;
    e.preventDefault();
    const html = e.clipboardData.getData('text/html');
    const text = e.clipboardData.getData('text/plain');
    let segments: Segment[] = [];
    if (html) {
      const doc = new DOMParser().parseFromString(html, 'text/html');
      segments = domToSegments(doc.body);
    } else if (text) {
      segments = text.split(/\n{2,}/).map((p) => ({ runs: [{ text: p.replace(/\n/g, ' ').trim() }], tag: 'p' })).filter((s) => s.runs[0].text);
    }
    if (!segments.length) return;
    if ((segments.length > 1 || segments[0].tag !== 'p') && onPasteBlocks && !singleLine) {
      onPasteBlocks(segments);
      return;
    }
    // Single segment: insert at the caret as marked-up HTML (already sanitised
    // by the walk), then re-serialise.
    const frag = runsToHtml(segments.flatMap((s) => s.runs));
    document.execCommand('insertHTML', false, frag);
    emit();
  };

  const applyLink = () => {
    if (linkDraft && /^(https?:\/\/|\/|#|mailto:)/.test(linkDraft)) {
      wrapSelection('a', { href: linkDraft });
    }
    setLinkDraft(null);
  };

  return (
    <div className="relative">
      {toolbar && !readOnly && (
        <div
          role="toolbar" aria-label="Text formatting"
          className="absolute z-20 flex items-center gap-0.5 rounded-md border border-line bg-surface p-1 shadow-lg"
          style={{ left: Math.max(0, toolbar.x - 140), top: toolbar.y }}
          onMouseDown={(e) => e.preventDefault()}
        >
          <TB label="Bold" onClick={() => toggle('bold')}><b>B</b></TB>
          <TB label="Italic" onClick={() => toggle('italic')}><i>I</i></TB>
          <TB label="Underline" onClick={() => toggle('underline')}><u>U</u></TB>
          <TB label="Strikethrough" onClick={() => toggle('strikeThrough')}><s>S</s></TB>
          <TB label="Code" onClick={() => wrapSelection('code')}><span className="font-mono text-[11px]">{'<>'}</span></TB>
          <TB label="Link" onClick={() => setLinkDraft('https://')}>🔗</TB>
          <span className="mx-1 h-4 w-px bg-line" />
          {HIGHLIGHTS.map((t) => (
            <TB key={t} label={`Highlight ${t}`} onClick={() => wrapSelection('mark', { 'data-token': t, style: `background:${HL_COLOR[t]};color:#170800;padding:0 .2em;border-radius:2px` })}>
              <span className="inline-block h-3.5 w-3.5 rounded-sm" style={{ background: HL_COLOR[t] }} />
            </TB>
          ))}
          <span className="mx-1 h-4 w-px bg-line" />
          {EMPHASES.map((t) => (
            <TB key={t} label={`Emphasis ${t}`} onClick={() => wrapSelection('span', { 'data-em': t, style: `color:${EM_COLOR[t]}` })}>
              <span className="text-[13px] font-bold" style={{ color: EM_COLOR[t] }}>A</span>
            </TB>
          ))}
        </div>
      )}
      {linkDraft !== null && (
        <div className="absolute z-30 left-0 top-0 flex gap-1 rounded-md border border-line bg-surface p-1 shadow-lg" onMouseDown={(e) => e.preventDefault()}>
          <input
            autoFocus value={linkDraft} onChange={(e) => setLinkDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') applyLink(); if (e.key === 'Escape') setLinkDraft(null); }}
            className="input-field w-72 py-1 text-xs" placeholder="https://… or /services" aria-label="Link URL"
          />
          <button type="button" className="btn-primary px-2 py-1 text-xs" onClick={applyLink}>Link</button>
        </div>
      )}
      <div
        ref={ref}
        contentEditable={!readOnly}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline={!singleLine}
        aria-label={placeholder}
        data-placeholder={placeholder}
        className={`rt min-h-[1.6em] outline-none ${empty ? 'rt-empty' : ''} ${className}`}
        onInput={emit}
        onBlur={() => { emit(); setTimeout(() => setToolbar(null), 150); }}
        onMouseUp={showToolbar}
        onKeyUp={(e) => { if (e.shiftKey || e.key.startsWith('Arrow')) showToolbar(); }}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
      />
    </div>
  );
}

function TB({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick}
      className="grid h-7 min-w-7 place-items-center rounded px-1.5 text-xs text-slate-200 hover:bg-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
      {children}
    </button>
  );
}

function plain(runs: RichText): string {
  return runs.map((r) => r.text).join('').trim();
}
