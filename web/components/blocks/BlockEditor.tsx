'use client';

/* The block list. Owns ordering and insertion; each block's fields are
   delegated to blockEditors.tsx.

   Keyboard-first: "/" in an empty paragraph opens the insert menu, Enter
   splits a paragraph, Backspace on an empty block removes it, and the drag
   handle is a real button — Alt+↑/↓ moves the block, so reordering never
   requires a mouse. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { EDITORS } from './blockEditors';
import type { Segment } from './RichText';
import {
  BLOCK_TYPES, CONVERTIBLE, convertBlock, newBlock, plainText,
  type Block, type BlockType, type RichText, type Violation,
} from '@/lib/blocks';

interface Props {
  blocks: Block[];
  onChange: (blocks: Block[]) => void;
  readOnly?: boolean;
  /* Bump when blocks were replaced from outside (restore) so editors resync. */
  version: number;
  violations?: Violation[];
  focusBlockId?: string | null;
  onFocusHandled?: () => void;
}

const LABEL: Record<string, string> = Object.fromEntries(BLOCK_TYPES.map((b) => [b.type, b.label]));
LABEL.legacy_html = 'Legacy HTML';

export default function BlockEditor({ blocks, onChange, readOnly = false, version, violations = [], focusBlockId, onFocusHandled }: Props) {
  const [menuAt, setMenuAt] = useState<number | null>(null);   // insert-after index; -1 = replace empty at index+1
  const [autoFocusId, setAutoFocusId] = useState<string | null>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    if (!focusBlockId) return;
    const el = rowRefs.current[focusBlockId];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('ring-2', 'ring-warning');
      setTimeout(() => el.classList.remove('ring-2', 'ring-warning'), 1600);
    }
    onFocusHandled?.();
  }, [focusBlockId, onFocusHandled]);

  const replaceAt = useCallback((i: number, b: Block) => onChange(blocks.map((x, j) => (j === i ? b : x))), [blocks, onChange]);
  const insertAt = useCallback((i: number, ...items: Block[]) => {
    onChange([...blocks.slice(0, i), ...items, ...blocks.slice(i)]);
    setAutoFocusId(items[0]?.id ?? null);
  }, [blocks, onChange]);
  const removeAt = useCallback((i: number) => {
    const next = blocks.filter((_, j) => j !== i);
    onChange(next.length ? next : [newBlock('paragraph')]);
    const prev = blocks[i - 1];
    if (prev) setAutoFocusId(prev.id);
  }, [blocks, onChange]);
  const move = useCallback((from: number, to: number) => {
    if (to < 0 || to >= blocks.length || from === to) return;
    const next = [...blocks];
    const [b] = next.splice(from, 1);
    next.splice(to, 0, b);
    onChange(next);
  }, [blocks, onChange]);
  const duplicate = (i: number) => {
    const copy = JSON.parse(JSON.stringify(blocks[i])) as Block;
    copy.id = newBlock('paragraph').id;
    insertAt(i + 1, copy);
  };

  const pickType = (type: BlockType) => {
    if (menuAt === null) return;
    const i = menuAt;
    // Opened from "/" in an empty paragraph: replace that paragraph.
    if (i >= 0 && blocks[i] && blocks[i].type === 'paragraph' && !plainText(blocks[i].content)) {
      const b = newBlock(type);
      replaceAt(i, b);
      setAutoFocusId(b.id);
    } else {
      insertAt(i + 1, newBlock(type));
    }
    setMenuAt(null);
  };

  const byBlock: Record<string, Violation[]> = {};
  for (const v of violations) if (v.block_id) (byBlock[v.block_id] ||= []).push(v);

  return (
    <div className="space-y-2" role="list" aria-label="Article blocks">
      {blocks.map((block, i) => {
        const Editor = EDITORS[block.type];
        const vs = byBlock[block.id] || [];
        const hasBlock = vs.some((v) => v.level === 'block');
        return (
          <div key={block.id} role="listitem" ref={(el) => { rowRefs.current[block.id] = el; }}
            onDragOver={(e) => { if (dragFrom !== null) { e.preventDefault(); setDragOver(i); } }}
            onDrop={(e) => { e.preventDefault(); if (dragFrom !== null) move(dragFrom, i); setDragFrom(null); setDragOver(null); }}
            className={`group relative rounded-lg border bg-surface p-3 pl-10 transition-colors ${hasBlock ? 'border-danger/50' : vs.length ? 'border-warning/40' : 'border-line'} ${dragOver === i ? 'border-primary' : ''}`}>

            {/* Handle + actions */}
            <div className="absolute left-1.5 top-2 flex flex-col items-center gap-0.5">
              <button type="button" draggable={!readOnly}
                onDragStart={() => setDragFrom(i)} onDragEnd={() => { setDragFrom(null); setDragOver(null); }}
                onKeyDown={(e) => { if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); move(i, i - 1); } if (e.altKey && e.key === 'ArrowDown') { e.preventDefault(); move(i, i + 1); } }}
                aria-label={`${LABEL[block.type]} block, position ${i + 1} of ${blocks.length}. Drag, or Alt+Arrow to move.`}
                title="Drag to reorder · Alt+↑/↓" disabled={readOnly}
                className="cursor-grab select-none rounded px-1 font-mono text-[10px] leading-none text-muted hover:bg-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">⋮⋮</button>
              <span className="font-mono text-[9px] uppercase tracking-wide text-muted/70">{LABEL[block.type].slice(0, 5)}</span>
            </div>

            {!readOnly && (
              <div className="absolute right-2 top-2 hidden gap-1 group-focus-within:flex group-hover:flex">
                {CONVERTIBLE.includes(block.type) && (
                  <select aria-label="Convert block type" value={block.type} className="input-field w-auto py-0.5 text-[11px]"
                    onChange={(e) => replaceAt(i, convertBlock(block, e.target.value as BlockType))}>
                    {CONVERTIBLE.map((t) => <option key={t} value={t}>{LABEL[t]}</option>)}
                  </select>
                )}
                <Act label="Move up" onClick={() => move(i, i - 1)}>↑</Act>
                <Act label="Move down" onClick={() => move(i, i + 1)}>↓</Act>
                <Act label="Duplicate block" onClick={() => duplicate(i)}>⧉</Act>
                <Act label="Delete block" danger onClick={() => removeAt(i)}>×</Act>
              </div>
            )}

            <Editor block={block} version={version} readOnly={readOnly} autoFocus={autoFocusId === block.id}
              onChange={(b) => replaceAt(i, b)}
              onSplit={(before: RichText, after: RichText) => {
                const next = newBlock('paragraph'); next.content = after.length ? after : [{ text: '' }];
                onChange([...blocks.slice(0, i), { ...block, content: before.length ? before : [{ text: '' }] }, next, ...blocks.slice(i + 1)]);
                setAutoFocusId(next.id);
              }}
              onDeleteEmpty={blocks.length > 1 ? () => removeAt(i) : undefined}
              onPasteBlocks={(segs: Segment[]) => {
                const made = segmentsToBlocks(segs);
                const isEmpty = block.type === 'paragraph' && !plainText(block.content);
                onChange([...blocks.slice(0, isEmpty ? i : i + 1), ...made, ...blocks.slice(i + 1)]);
              }}
              onSlash={() => setMenuAt(i)} />

            {vs.length > 0 && (
              <ul className="mt-2 space-y-0.5">
                {vs.map((v, k) => <li key={k} className={`text-[11px] ${v.level === 'block' ? 'text-danger' : 'text-warning'}`}>{v.level === 'block' ? '⛔' : '⚠'} {v.message}</li>)}
              </ul>
            )}

            {!readOnly && (
              <button type="button" onClick={() => setMenuAt(i)} aria-label="Insert a block after this one"
                className="absolute -bottom-3 left-1/2 z-10 hidden -translate-x-1/2 rounded-full border border-line bg-surface px-2 text-xs text-muted group-hover:block hover:text-primary focus:block">+</button>
            )}
            {menuAt === i && <SlashMenu onPick={pickType} onClose={() => setMenuAt(null)} />}
          </div>
        );
      })}
      {!readOnly && (
        <div className="relative">
          <button type="button" className="btn-secondary w-full py-2 text-sm" onClick={() => setMenuAt(blocks.length - 1)}>+ Add a block</button>
          {menuAt === blocks.length - 1 && blocks.length === 0 && <SlashMenu onPick={pickType} onClose={() => setMenuAt(null)} />}
        </div>
      )}
    </div>
  );
}

function Act({ label, onClick, danger, children }: { label: string; onClick: () => void; danger?: boolean; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick}
      className={`grid h-6 w-6 place-items-center rounded border text-xs ${danger ? 'border-danger/40 text-danger hover:bg-danger/10' : 'border-line text-slate-300 hover:bg-raised'} focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary`}>
      {children}
    </button>
  );
}

/* Paste: HTML headings and list items keep their meaning; plain text that
   looks like a markdown heading or list item is treated the same way.
   Consecutive list items become one list block. */
function segmentsToBlocks(segs: Segment[]): Block[] {
  const out: Block[] = [];
  for (const seg of segs) {
    const text = plainText(seg.runs);
    let tag = seg.tag;
    let runs = seg.runs;
    let ordered = !!seg.ordered;
    const h = text.match(/^(#{2,4})\s+(.*)$/);
    const li = text.match(/^(?:[-*•]|(\d+)[.)])\s+(.*)$/);
    if (tag === 'p' && h) { tag = `h${h[1].length}`; runs = [{ text: h[2] }]; }
    else if (tag === 'p' && li) { tag = 'li'; ordered = !!li[1]; runs = [{ text: li[2] }]; }
    if (/^h[1-6]$/.test(tag)) {
      const b = newBlock('heading'); b.attrs = { level: Math.min(Math.max(Number(tag[1]), 2), 4), gradient: false }; b.content = runs; out.push(b);
    } else if (tag === 'li') {
      const prev = out[out.length - 1];
      const style = ordered ? 'numbered' : 'bullet';
      if (prev && prev.type === 'list' && prev.attrs?.style === style) prev.content.push({ content: runs, checked: false });
      else { const b = newBlock('list'); b.attrs = { style }; b.content = [{ content: runs, checked: false }]; out.push(b); }
    } else if (tag === 'blockquote') {
      const b = newBlock('callout'); b.attrs = { kind: 'info', title: null }; b.content = runs; out.push(b);
    } else {
      const b = newBlock('paragraph'); b.content = runs; out.push(b);
    }
  }
  return out;
}

function SlashMenu({ onPick, onClose }: { onPick: (t: BlockType) => void; onClose: () => void }) {
  const [q, setQ] = useState('');
  const [cursor, setCursor] = useState(0);
  const items = BLOCK_TYPES.filter((b) => (b.label + ' ' + b.hint + ' ' + b.type).toLowerCase().includes(q.toLowerCase()));
  useEffect(() => { setCursor(0); }, [q]);
  return (
    <div role="dialog" aria-label="Insert block" className="absolute left-10 top-full z-30 mt-1 w-80 rounded-lg border border-line bg-surface p-2 shadow-xl">
      <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type to filter — Enter to insert, Esc to close"
        aria-label="Filter block types" className="input-field mb-1 py-1 text-sm"
        onKeyDown={(e) => {
          if (e.key === 'Escape') { e.preventDefault(); onClose(); }
          if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, items.length - 1)); }
          if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
          if (e.key === 'Enter' && items[cursor]) { e.preventDefault(); onPick(items[cursor].type); }
        }} />
      <ul role="listbox" className="max-h-72 overflow-y-auto">
        {items.map((b, i) => (
          <li key={b.type} role="option" aria-selected={i === cursor}>
            <button type="button" onMouseEnter={() => setCursor(i)} onClick={() => onPick(b.type)}
              className={`flex w-full items-baseline justify-between rounded px-2 py-1.5 text-left text-sm ${i === cursor ? 'bg-raised text-slate-100' : 'text-slate-300'}`}>
              <span>{b.label}{b.visual && <span className="ml-1.5 text-[10px] text-success">visual</span>}</span>
              <span className="text-[11px] text-muted">{b.hint}</span>
            </button>
          </li>
        ))}
        {!items.length && <li className="px-2 py-1 text-xs text-muted">No block matches “{q}”.</li>}
      </ul>
    </div>
  );
}
