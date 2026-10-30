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

/* v3 hour credits for the work month (26th..25th) so far (finished days). owedMinutes = short beyond the allowance. */
export type Credit = {
  month: string; workedMinutes: number; targetMinutes: number; idleMinutes: number;
  balanceMinutes: number; allowanceMinutes: number; owedMinutes: number; from: string; to: string;
  ringsClosed: number; ringDays: number;
};

/* v3 Big Ideas board (open to everyone). */
export type BigIdea = {
  id: number; user_id: string; name: string; month: string; title: string; channel: string; idea: string;
  status: string; assigned_to: string | null; assignedName: string; project: string; task_id: number | null;
  note: string; created_at: string;
};
export type IdeaBoard = {
  month: string; ideas: BigIdea[]; channels: string[]; required: number; forNomination: number; me: string;
  people: { user_id: string; name: string; counted: number; worked: number; assigned: number; nominated: boolean }[];
  isSuperuser: boolean; statuses: string[]; projects: string[];
  employeeOfMonth: { user_id: string; name: string; note: string } | null;
};

/* v3: Jai's predefined daily tasks; user_id '*' = everyone. */
export type Routine = {
  id: number; title: string; category: string; category_id: number; details: Record<string, string>;
  priority: string; user_id: string; active: number;
};

export type WState = {
  now: string; today: string;
  running: { interval: Interval; task: WTask | null; stale: boolean } | null;
  tasks: WTask[]; pool: WTask[]; holds: Hold[]; approve: Hold[];
  categories: Category[]; people: { user_id: string; name: string }[];
  work: {
    workedMinutes: number; provenMinutes: number; targetMinutes: number; leftMinutes: number;
    needProof: { slot: string; minutes: number; taskId: number | null }[];
  };
  settings: { slotMinutes: number; dailyTargetHours: number; dayLateAfter: string; greenMin: number; amberMin: number; thinkingCap: number };
  tasksDone: number;
  hours: { week: number[]; days: { date: string; hours: number; note: string }[] } | null;
  isSuperuser: boolean;
  hoursChanges: { week: number[]; effective_from: string }[];
  credit: Credit | null; teamCredits: (Credit & { user_id: string; name: string; allowanceHours: number })[]; allowanceAll: number;
  teamDays: { user_id: string; name: string | null; start_at: string; end_at: string | null; status: string }[];
  dayFlow: boolean; day: WorkDay | null;
  blockReasons: string[]; routines: Routine[]; routinesAll: Routine[];
  breaks: { used: Record<'break' | 'lunch' | 'thinking' | 'waiting', number>; limit: { break: number; lunch: number } };
  suggestions?: WTask[]; needsApproval?: boolean;
};

const V = '/api/tasks/v2';
export const wtApi = {
  state: () => api.get<WState>(`${V}/state`),
  create: (body: Record<string, unknown>) => api.post<{ task: WTask }>(`${V}/tasks`, body),
  start: (id: number) => api.post<WState>(`${V}/tasks/${id}/start`),
  pause: () => api.post<WState>(`${V}/pause`),
  takeBreak: (type: string) => api.post<WState>(`${V}/break`, { type }),
  endSession: (end: string) => api.post<WState>(`${V}/session/end`, { end }),
  complete: (id: number, evidence_url: string) => api.post<WState>(`${V}/tasks/${id}/complete`, { evidence_url }),
  block: (id: number, body: { depends_on_user_id?: string; depends_on_name?: string; reason: string; detail?: string }) =>
    api.post<WState>(`${V}/tasks/${id}/block`, body),
  unblock: (id: number) => api.post<WState>(`${V}/tasks/${id}/unblock`),
  decide: (id: number, approve: boolean, note = '') => api.post<WState>(`${V}/holds/${id}/decide`, { approve, note }),
  proof: (body: Record<string, string>) => api.post<WState>(`${V}/proof`, body),
  startDay: () => api.post<WState>(`${V}/day/start`),
  endDay: () => api.post<WState>(`${V}/day/end`),
  reopenDay: (user_id?: string) => api.post<WState>(`${V}/day/reopen`, { user_id }),
  weekHours: (week: number[], from?: string) => api.post<WState>(`${V}/hours/week`, { week, from: from || undefined }),
  dayHours: (date: string, hours: number | null, note = '') => api.post<WState>(`${V}/hours/day`, { date, hours, note }),
  createRoutine: (body: Record<string, unknown>) => api.post<WState>(`${V}/routines`, body),
  routineActive: (id: number, active: boolean) => api.post<WState>(`${V}/routines/${id}/active`, { active }),
  allowance: (user_id: string, hours: number) => api.post<WState>(`${V}/hours/allowance`, { user_id, hours }),
  ideas: () => api.get<IdeaBoard>(`${V}/ideas`),
  submitIdea: (body: { title: string; channel: string; idea: string }) => api.post<IdeaBoard>(`${V}/ideas`, body),
  decideIdea: (id: number, body: { status: string; assign_to?: string; project?: string; note?: string }) =>
    api.post<IdeaBoard>(`${V}/ideas/${id}/decide`, body),
  pickEmployeeOfMonth: (user_id: string, note = '') => api.post<IdeaBoard>(`${V}/ideas/employee-of-month`, { user_id, note }),
  startRoutine: (id: number) => api.post<WState>(`${V}/routines/${id}/start`),
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
