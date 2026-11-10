'use client';

import { useRef, useState } from 'react';
import { isAllowedUrl } from '@/lib/playbook';

/**
 * A textarea with two buttons: Bold (also Ctrl+B) wraps the selection in
 * **…**, Link asks for a URL and writes [text](url). Only https://… and
 * site paths /… are accepted (same rule the server applies). Used for H2
 * section paragraphs and FAQ answers — deliberately not for the TL;DR.
 */
export default function FormatTextarea({
  id,
  value,
  onChange,
  rows = 4,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (next: string) => void;
  rows?: number;
  placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [error, setError] = useState<string | null>(null);

  const replaceSelection = (make: (selected: string) => string | null) => {
    const el = ref.current;
    if (!el) return;
    const { selectionStart: start, selectionEnd: end } = el;
    const inserted = make(value.slice(start, end));
    if (inserted === null) return;
    onChange(value.slice(0, start) + inserted + value.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start, start + inserted.length);
    });
  };

  const bold = () => replaceSelection((s) => `**${s || 'bold text'}**`);

  const link = () =>
    replaceSelection((s) => {
      const url = (window.prompt('Link URL — https://… or a site path like /blog/…', 'https://') || '').trim();
      if (!url || url === 'https://') return null;
      if (!isAllowedUrl(url)) {
        setError(`“${url}” is not allowed. Use https://… or a site path starting with /.`);
        return null;
      }
      setError(null);
      return `[${(s || 'link text').replace(/[[\]]/g, '')}](${url})`;
    });

  return (
    <div>
      <div className="mb-1 flex gap-1" role="toolbar" aria-label="Formatting">
        <button type="button" className="btn-secondary px-2 py-0.5 text-xs font-bold"
                title="Bold (Ctrl+B)" aria-label="Bold" onClick={bold}>
          B
        </button>
        <button type="button" className="btn-secondary px-2 py-0.5 text-xs"
                title="Insert link" onClick={link}>
          Link
        </button>
      </div>
      <textarea
        ref={ref}
        id={id}
        className="input-field"
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
            e.preventDefault();
            bold();
          }
        }}
      />
      {error && <p className="mt-1 text-xs text-danger" role="alert">{error}</p>}
    </div>
  );
}
