import api from '@/lib/api';

/* Tasks v2 (/api/tasks/v2/*): task timer, 15-minute proof, road blockers.
   The server is the truth; the page only shows the running clock. */

export type Field = { key: string; label: string; type: 'text' | 'choice'; options?: string[] };
export type Category = { id: number; name: string; fields: Field[]; deadline_workdays: number; hold_needs_approval: number };

export type WTask = {
  id: number; title: string; description: string; category: string; category_id: number;
  priority: 'P1' | 'P2' | 'P3'; estimate_min: number; status: string; pool: boolean;
  assigned_to: string | null; due_date: string | null; details: Record<string, string>; evidence_url: string;
};

export type Interval = { id: number; task_id: number | null; type: string; start_ts: string };
export type Hold = {
  id: number; task_id: number; user_id: string; depends_on_name: string; reason: string;
  start_ts: string; end_ts: string | null; status: string; title?: string;
};

/* v3: one row per person per day. status on_time | late; end_at null while the day runs. */
export type WorkDay = { date: string; start_at: string; end_at: string | null; status: string; end_source: string };

export type WState = {
  now: string; today: string;
  running: { interval: Interval; task: WTask | null; stale: boolean } | null;
  tasks: WTask[]; pool: WTask[]; holds: Hold[]; approve: Hold[];
  categories: Category[]; people: { user_id: string; name: string }[];
  work: {
    workedMinutes: number; provenMinutes: number; targetMinutes: number; leftMinutes: number;
    needProof: { slot: string; minutes: number; taskId: number | null }[];
  };
  settings: { slotMinutes: number; dailyTargetHours: number; dayLateAfter: string };
  isSuperuser: boolean;
  dayFlow: boolean; day: WorkDay | null; openDay: WorkDay | null;
  suggestions?: WTask[]; needsApproval?: boolean;
};

const V = '/api/tasks/v2';
export const wtApi = {
  state: () => api.get<WState>(`${V}/state`),
  create: (body: Record<string, unknown>) => api.post<{ task: WTask }>(`${V}/tasks`, body),
  start: (id: number) => api.post<WState>(`${V}/tasks/${id}/start`),
  pause: () => api.post<WState>(`${V}/pause`),
  endSession: (end: string) => api.post<WState>(`${V}/session/end`, { end }),
  complete: (id: number, evidence_url: string) => api.post<WState>(`${V}/tasks/${id}/complete`, { evidence_url }),
  block: (id: number, body: { depends_on_user_id?: string; depends_on_name?: string; reason: string }) =>
    api.post<WState>(`${V}/tasks/${id}/block`, body),
  unblock: (id: number) => api.post<WState>(`${V}/tasks/${id}/unblock`),
  decide: (id: number, approve: boolean, note = '') => api.post<WState>(`${V}/holds/${id}/decide`, { approve, note }),
  proof: (body: Record<string, string>) => api.post<WState>(`${V}/proof`, body),
  startDay: () => api.post<WState>(`${V}/day/start`),
  endDay: () => api.post<WState>(`${V}/day/end`),
  setDayEnd: (end: string) => api.post<WState>(`${V}/day/set-end`, { end }),
};

/** "2026-10-26T10:15" (IST slot) → "10:15–10:30" */
export const slotLabel = (slot: string, minutes = 15) => {
  const [h, m] = slot.slice(11, 16).split(':').map(Number);
  const end = h * 60 + m + minutes;
  return `${slot.slice(11, 16)}–${String(Math.floor(end / 60) % 24).padStart(2, '0')}:${String(end % 60).padStart(2, '0')}`;
};

/** ISO time → "9:42 am" in IST */
export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' });

export const hm = (min: number) => `${Math.floor(min / 60)}h ${String(Math.round(min % 60)).padStart(2, '0')}m`;
