import api from '@/lib/api';

/* Task manager (T7) — /api/tasks/items, /plan, /rag, /mirror, /tiers, /rewards. */

export type Rag = 'green' | 'amber' | 'red' | 'none';
export type TaskStatus = 'todo' | 'in_progress' | 'submitted' | 'approved' | 'needs_fix' | 'blocked';

export type Task = {
  id: number; title: string; description: string; project_id: string; site: string; goal: string;
  target_qty: number; unit: string; unitLabel: string; auto: boolean; proof_type: string; effort_hours: number;
  priority: 'P1' | 'P2' | 'P3'; start_at: string; due_at: string; recurrence: string; series_id: number | null;
  status: TaskStatus; blocked_reason: string; marks: number; quality: number | null; rework: number;
  kind: 'task' | 'weekly_idea'; week: string | null; submitted_at: string | null; approved_at: string | null;
  review_note: string; created_by_name: string;
  assignees: { user_id: string; user_name: string }[];
  progress: number; pct: number; rag: Rag; ragWhy: string;
  checklist: { id: number; text: string; done: number }[];
  links?: { id: number; url: string; label: string }[];
  comments?: { id: number; user_name: string; text: string; created_at: string }[];
  entries?: { id: number; user_name: string; qty: number; source: string; proof_url: string; created_at: string }[];
};

export type Person = { user_id: string; name: string; email: string; role: string };
export type Unit = { unit: string; label: string; marks?: number };

export type Signal = {
  period: 'day' | 'week' | 'month'; signal: Rag; pct: number | null; from: string; to: string;
  lines: { project: string; unit: string; unitLabel: string; expected: number; actual: number }[];
  overdue: { id: number; title: string }[];
};

export type Plan = {
  userId: string; month: string; leave: string[]; workdays: number[]; units: Unit[];
  targets: { project: string; unit: string; unitLabel: string; month: string; qty: number;
             weeks: { weekStart: string; qty: number; edited: boolean }[]; days: Record<string, number> }[];
};

export type Tier = { id: number; name: string; min_points: number; bonus_note?: string };

export type Mirror = {
  userId: string; name: string; month: string;
  signals: Record<'day' | 'week' | 'month', Signal>;
  history: { date: string; signal: Rag }[];
  onTimePct: number | null; qualityAvg: number | null; rework: number; points: number;
  tier: (Tier & { bonus_note?: string }) | null;
  nextTier: (Tier & { gap: number; bonus_note?: string }) | null;
  ways: string[]; rank: { rank: number; of: number } | null; showRank: boolean;
  strengths: { type: string; avg: number; n: number }[]; gaps: { type: string; avg: number; n: number }[];
  badges: { key: string; label: string }[];
  ledger: { points: number; reason: string; ref_type: string; ref_id: string; created_at: string }[];
};

export const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: 'To do', in_progress: 'In progress', submitted: 'Submitted', approved: 'Approved',
  needs_fix: 'Needs fix', blocked: 'Blocked',
};
export const BOARD: TaskStatus[] = ['todo', 'in_progress', 'blocked', 'needs_fix', 'submitted', 'approved'];

export const RAG_DOT: Record<Rag, string> = {
  green: 'bg-success', amber: 'bg-warning', red: 'bg-danger', none: 'bg-slate-600',
};
export const RAG_LABEL: Record<Rag, string> = { green: 'Green', amber: 'Amber', red: 'Red', none: 'No target' };

export const fmtDue = (s: string) =>
  new Date(s.replace(' ', 'T')).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

export const tasksApi = {
  list: (params: { scope?: 'mine' | 'all'; user_id?: string; project_id?: string; status?: string; due_before?: string } = {}) =>
    api.get<{ tasks: Task[]; now: string }>('/api/tasks/items', { params }),
  get: (id: number) => api.get<{ task: Task }>(`/api/tasks/items/${id}`),
  create: (body: Record<string, unknown>) => api.post<{ task: Task; warnings: string[] }>('/api/tasks/items', body),
  update: (id: number, body: Record<string, unknown>) => api.put<{ task: Task }>(`/api/tasks/items/${id}`, body),
  remove: (id: number) => api.delete(`/api/tasks/items/${id}`),
  status: (id: number, status: TaskStatus, reason?: string) =>
    api.post<{ task: Task }>(`/api/tasks/items/${id}/status`, { status, reason }),
  approve: (id: number, body: { status: 'approved' | 'needs_fix'; quality?: number; note?: string }) =>
    api.post<{ task: Task; points?: number }>(`/api/tasks/items/${id}/approve`, body),
  progress: (id: number, qty: number, proof_url: string) =>
    api.post<{ task: Task }>(`/api/tasks/items/${id}/progress`, { qty, proof_url }),
  comment: (id: number, text: string) => api.post<{ task: Task }>(`/api/tasks/items/${id}/comments`, { text }),
  link: (id: number, url: string, label = '') => api.post<{ task: Task }>(`/api/tasks/items/${id}/links`, { url, label }),
  addCheck: (id: number, text: string) => api.post<{ task: Task }>(`/api/tasks/items/${id}/checklist`, { text }),
  check: (id: number, itemId: number, done: boolean) =>
    api.put<{ task: Task }>(`/api/tasks/items/${id}/checklist/${itemId}`, { done }),
  people: () => api.get<{ people: Person[] }>('/api/tasks/people'),
  plan: (user_id?: string, month?: string) => api.get<Plan>('/api/tasks/plan', { params: { user_id, month } }),
  setTarget: (body: { user_id: string; project_id: string; unit: string; month: string; qty: number }) =>
    api.put<Plan>('/api/tasks/plan', body),
  setSplit: (body: { user_id: string; project_id: string; unit: string; month: string; week_start: string; qty: number | null }) =>
    api.put<Plan>('/api/tasks/plan/split', body),
  applyTemplate: (body: { user_id: string; project_id: string; month: string; role?: string }) =>
    api.post<Plan>('/api/tasks/plan/template', body),
  templates: () => api.get<{ templates: { role: string; unit: string; unitLabel: string; qty_per_week: number }[]; units: Unit[] }>('/api/tasks/templates'),
  saveTemplates: (templates: { role: string; unit: string; qty_per_week: number }[]) => api.put('/api/tasks/templates', { templates }),
  leave: (user_id: string, date: string, remove = false, reason = 'leave') =>
    remove ? api.post('/api/tasks/leave/remove', { user_id, date }) : api.put('/api/tasks/leave', { user_id, date, reason }),
  rag: (user_id?: string) => api.get<{ signals: Record<'day' | 'week' | 'month', Signal> }>('/api/tasks/rag', { params: { user_id } }),
  teamRag: () => api.get<{ rows: { userId: string; name: string; day: Rag; week: Rag; month: Rag }[] }>('/api/tasks/rag/team'),
  ragSettings: (green_min: number, amber_min: number) => api.put('/api/tasks/rag-settings', { green_min, amber_min }),
  mirror: (user_id?: string, month?: string) => api.get<Mirror>('/api/tasks/mirror', { params: { user_id, month } }),
  mirrorSettings: (show_rank: boolean) => api.put('/api/tasks/mirror-settings', { show_rank }),
  tiers: () => api.get<{ tiers: Tier[]; canEdit: boolean }>('/api/tasks/tiers'),
  saveTiers: (tiers: Tier[]) => api.put<{ tiers: Tier[] }>('/api/tasks/tiers', { tiers }),
  rewards: (month?: string) =>
    api.get<{ month: string; canApprove: boolean;
              rows: { userId: string; name: string; points: number; tier: string; bonusNote: string; approved: unknown }[] }>(
      '/api/tasks/rewards', { params: { month } }),
  approveRewards: (month: string) => api.post('/api/tasks/rewards/approve', { month }),
  rewardsCsv: (month: string) => api.get<Blob>('/api/tasks/rewards.csv', { params: { month }, responseType: 'blob' }),
};

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
