'use client';

import { useEffect, useRef } from 'react';

/* One short burst when `fire` turns true. No dependency; respects
   prefers-reduced-motion. Same idea as the Backlink Ops desk's burst. */
export default function Confetti({ fire }: { fire: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!fire || !ref.current) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const canvas = ref.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const colors = ['#2563EB', '#10b981', '#f59e0b', '#ef4444', '#a855f7', '#e2e8f0'];
    const bits = Array.from({ length: 140 }, () => ({
      x: canvas.width / 2 + (Math.random() - 0.5) * 200,
      y: canvas.height / 3,
      vx: (Math.random() - 0.5) * 14,
      vy: Math.random() * -12 - 4,
      r: Math.random() * 6 + 3,
      c: colors[Math.floor(Math.random() * colors.length)],
      spin: Math.random() * 6,
    }));
    let frame = 0;
    let raf = 0;
    const tick = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const b of bits) {
        b.vy += 0.35;
        b.x += b.vx;
        b.y += b.vy;
        b.spin += 0.2;
        ctx.fillStyle = b.c;
        ctx.fillRect(b.x, b.y, b.r, b.r * (0.5 + Math.abs(Math.sin(b.spin)) / 2));
      }
      if (++frame < 150) raf = requestAnimationFrame(tick);
      else ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [fire]);

  return <canvas ref={ref} aria-hidden className="pointer-events-none fixed inset-0 z-50" />;
}
