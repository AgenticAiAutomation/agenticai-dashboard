'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Line-number gutter for a textarea, Notepad++ style.
 *
 * The hard part is soft wrap: a logical line that wraps over three visual rows
 * is three rows tall, so numbering by row would drift out of alignment with
 * the text almost immediately. Turning wrap off would keep them aligned but
 * makes prose unwritable — you would scroll sideways through every paragraph.
 *
 * So the heights are measured instead. A hidden mirror div is laid out with
 * the textarea's exact font, width, padding and wrapping rules; each logical
 * line becomes one child, and that child's rendered height is the height its
 * number must occupy. Numbers then line up with their text no matter how many
 * visual rows each one takes.
 */

type Props = {
  /** Textarea being numbered. */
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  value: string;
  /** 1-based line numbers that have a scoring issue, for highlighting. */
  issueLines?: Set<number>;
  /** Scroll offset of the textarea, so the gutter tracks it. */
  scrollTop: number;
  onLineClick?: (line: number) => void;
};

export default function LineGutter({
  textareaRef,
  value,
  issueLines,
  scrollTop,
  onLineClick,
}: Props) {
  const mirrorRef = useRef<HTMLDivElement>(null);
  const [heights, setHeights] = useState<number[]>([]);

  useEffect(() => {
    const textarea = textareaRef.current;
    const mirror = mirrorRef.current;
    if (!textarea || !mirror) return;

    const measure = () => {
      const styles = window.getComputedStyle(textarea);
      // Copy every property that affects where text breaks.
      mirror.style.font = styles.font;
      mirror.style.fontFamily = styles.fontFamily;
      mirror.style.fontSize = styles.fontSize;
      mirror.style.lineHeight = styles.lineHeight;
      mirror.style.letterSpacing = styles.letterSpacing;
      mirror.style.paddingLeft = styles.paddingLeft;
      mirror.style.paddingRight = styles.paddingRight;
      mirror.style.width = `${textarea.clientWidth}px`;

      setHeights(
        Array.from(mirror.children).map((child) =>
          (child as HTMLElement).getBoundingClientRect().height,
        ),
      );
    };

    measure();

    // The wrap point changes with the textarea's width, so re-measure on resize.
    const observer = new ResizeObserver(measure);
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [value, textareaRef]);

  const lines = value.split('\n');

  return (
    <>
      {/* Hidden mirror. aria-hidden and inert: it is a measuring device, not
          content, and must never reach a screen reader or the tab order. */}
      <div
        ref={mirrorRef}
        aria-hidden="true"
        className="pointer-events-none absolute -left-[9999px] top-0 whitespace-pre-wrap break-words"
      >
        {lines.map((line, index) => (
          // A zero-width space keeps an empty line one row tall rather than
          // collapsing to zero height.
          <div key={index}>{line || '​'}</div>
        ))}
      </div>

      <div
        aria-hidden="true"
        className="select-none overflow-hidden border-r border-line bg-surface
                   text-right font-mono text-xs leading-relaxed text-muted"
        style={{ width: `${Math.max(String(lines.length).length, 2) + 1.5}ch` }}
      >
        <div style={{ transform: `translateY(-${scrollTop}px)` }}>
          {lines.map((_, index) => {
            const lineNumber = index + 1;
            const hasIssue = issueLines?.has(lineNumber);
            return (
              <div
                key={index}
                onClick={() => onLineClick?.(lineNumber)}
                style={{ height: heights[index] ? `${heights[index]}px` : undefined }}
                className={`pr-2 ${onLineClick ? 'cursor-pointer' : ''} ${
                  hasIssue
                    ? 'bg-warning/20 font-semibold text-warning'
                    : 'hover:text-slate-300'
                }`}
                title={hasIssue ? 'This line has a scoring suggestion' : undefined}
              >
                {lineNumber}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
