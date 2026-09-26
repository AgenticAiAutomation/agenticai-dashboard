'use client';

/* Lead notification bell.
 *
 * The funnel's job ends when a lead is stored; this is how a person finds out.
 * It replaces the email alert: no SMTP credential, no deliverability, nothing
 * to go quietly wrong between here and an inbox. If the dashboard is open, a
 * new lead is seen.
 *
 * "Seen" is per browser, in localStorage, not per account on the server — two
 * people watching both get told, which is what you want for a lead.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';

const POLL_MS = 30_000;
const SEEN_KEY = 'wa_leads_seen_id';
const MUTE_KEY = 'wa_leads_muted';

interface NotificationLead {
  id: number;
  created_at: string;
  name: string;
  industry: string;
  subtype: string;
  fit_score: number;
  qualified: boolean;
  status: string;
}

/* A short two-note chime, synthesised rather than shipped as an audio file:
   no asset to fetch, no 404 to debug, and it cannot be blocked as a tracker.
   Browsers refuse audio until the page has been interacted with, so a failure
   here is expected and silent — the badge still appears. */
function ping() {
  try {
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const now = ctx.currentTime;
    [880, 1320].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      const at = now + i * 0.13;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.16, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.3);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(at);
      osc.stop(at + 0.32);
    });
    setTimeout(() => ctx.close().catch(() => {}), 1200);
  } catch {
    /* no audio available — the badge is the real notification */
  }
}

function ago(iso: string) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function LeadBell() {
  const router = useRouter();
  const [leads, setLeads] = useState<NotificationLead[]>([]);
  const [unseen, setUnseen] = useState(0);
  const [open, setOpen] = useState(false);
  const [muted, setMuted] = useState(false);
  const [available, setAvailable] = useState(true);

  const seenRef = useRef<number>(0);
  const startedRef = useRef(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      seenRef.current = Number(localStorage.getItem(SEEN_KEY) || 0);
      setMuted(localStorage.getItem(MUTE_KEY) === '1');
    } catch {
      /* private window — start from zero, poll still works */
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const res = await api.get(`/api/wa-leads/notifications?since_id=${seenRef.current}`);
      const data = res.data as { latest_id: number; unseen: number; leads: NotificationLead[] };
      setAvailable(true);
      setLeads(data.leads);
      setUnseen(data.unseen);

      // Chime only for leads that arrived while this tab was watching. On the
      // first poll after a reload there may be a backlog; showing the count is
      // right, making a noise about leads from yesterday is not.
      if (startedRef.current && data.unseen > 0 && !muted) ping();
      startedRef.current = true;
    } catch (e: any) {
      // 404 = not the owner, 503 = funnel not deployed. Either way the bell
      // has nothing to say, so it hides rather than showing an error.
      if (e?.response?.status === 404 || e?.response?.status === 503) setAvailable(false);
    }
  }, [muted]);

  useEffect(() => {
    if (!localStorage.getItem('access_token')) return;
    poll();
    const t = setInterval(poll, POLL_MS);
    // Catch up immediately when the tab is brought back, rather than waiting
    // out the remainder of the interval.
    const onVisible = () => { if (document.visibilityState === 'visible') poll(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVisible); };
  }, [poll]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const markAllSeen = () => {
    const highest = leads.length ? leads[0].id : seenRef.current;
    seenRef.current = highest;
    try { localStorage.setItem(SEEN_KEY, String(highest)); } catch {}
    setUnseen(0);
    setLeads([]);
  };

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    try { localStorage.setItem(MUTE_KEY, next ? '1' : '0'); } catch {}
    if (!next) ping();      // let them hear what they just turned on
  };

  const openLead = (id: number) => {
    markAllSeen();
    setOpen(false);
    // Two routes to the same place: the event is heard when the leads page is
    // already mounted (router.push would not remount it), the query parameter
    // is read when arriving from somewhere else.
    window.dispatchEvent(new CustomEvent<number>('wa-leads:open', { detail: id }));
    if (!window.location.pathname.startsWith('/dashboard/leads')) {
      router.push(`/dashboard/leads?lead=${id}`);
    }
  };

  if (!available) return null;

  return (
    <div className="relative" ref={boxRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-slate-300 transition-colors hover:bg-raised hover:text-white"
        aria-label={unseen > 0 ? `${unseen} new leads` : 'Leads'}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unseen > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-[1.25rem] items-center
                           justify-center rounded-full bg-danger px-1 text-[11px] font-semibold
                           text-white">
            {unseen > 9 ? '9+' : unseen}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl border
                        border-line bg-surface shadow-2xl">
          <header className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="text-sm font-semibold text-white">
              {unseen > 0 ? `${unseen} new lead${unseen === 1 ? '' : 's'}` : 'Leads'}
            </span>
            <button
              onClick={toggleMute}
              className="text-xs text-muted hover:text-white"
              title={muted ? 'Sound is off' : 'Sound is on'}
            >
              {muted ? '🔇 Sound off' : '🔔 Sound on'}
            </button>
          </header>

          <div className="max-h-80 overflow-y-auto">
            {leads.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted">
                Nothing new. A lead appears here within 30 seconds of someone
                finishing the form.
              </p>
            ) : (
              leads.map((l) => (
                <button
                  key={l.id}
                  onClick={() => openLead(l.id)}
                  className="block w-full border-b border-line/60 px-4 py-3 text-left
                             transition-colors last:border-0 hover:bg-raised"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-medium text-white">{l.name}</span>
                    <span className={`shrink-0 text-xs tabular-nums ${
                      l.qualified ? 'text-success' : 'text-muted'}`}>
                      {l.fit_score}
                    </span>
                  </div>
                  <p className="truncate text-xs text-muted">{l.subtype}</p>
                  <p className="text-xs text-muted">{ago(l.created_at)}</p>
                </button>
              ))
            )}
          </div>

          <footer className="flex items-center justify-between border-t border-line px-4 py-2">
            <button
              onClick={() => { setOpen(false); router.push('/dashboard/leads'); }}
              className="text-xs text-primary hover:underline"
            >
              Open the leads desk
            </button>
            {unseen > 0 && (
              <button onClick={markAllSeen} className="text-xs text-muted hover:text-white">
                Mark all seen
              </button>
            )}
          </footer>
        </div>
      )}
    </div>
  );
}
