import api from '@/lib/api';

/* Daily Tracker + Idea Board (/api/tasks/*, /api/ideas/*) and the per-site
   levels on Backlink Ops (/api/seo/backlink-ops/levels). Those modules answer
   errors as {error, message}, not FastAPI's {detail}. */

export type Site = { id: string; name: string; short: string; domain: string; hue: string; active: boolean };

export type TrackerStatus = {
  tracker: boolean;
  ideas: boolean;
  taskManager?: boolean;
  isSuperuser?: boolean;
  role?: string;
  readOnly: boolean;
  me: { id: string; name: string; email: string };
  isAdmin: boolean;
  sites: Record<string, Site>;
  allowed: string[];
  today: string;
  backdateDays: number;
  noteMax: number;
  target: number;
  settings: { default_daily_target: number; backlink_daily_cap: number; late_factor: number; show_rank?: boolean } | null;
  badges: { month: string; kind: string; idea_id: number }[];
};

export type WorkType = { id: number; name: string; base_marks: number; active: number; sort_order: number; kind: string };

export type Log = {
  id: number | string;
  userId?: string;
  userName: string;
  project: string;
  site: string;
  workTypeId?: number;
  workType: string;
  baseMarks?: number;
  proofUrl: string;
  note: string;
  minutes?: number;
  date: string;
  submittedAt?: string;
  late: boolean;
  status: 'submitted' | 'approved' | 'needs_fix' | 'rejected' | 'pending';
  quality?: number | null;
  marks: number | null;
  reviewer?: string | null;
  reviewNote?: string | null;
  source: 'manual' | 'backlink_ops';
};

export type DayTotals = {
  marks: number; approved: number; pending: number; needs_fix: number;
  bo_links: number; bo_pending: number; bo_marks: number; done: boolean; items: number;
};

export type Ranked = { userId: string; name: string; marks: number; rank: number };

export type Summary = {
  range: string; from: string; to: string; today: string; target: number;
  todayTotals: DayTotals;
  series: { date: string; marks: number; target: number; hit: boolean }[];
  heatmap: { date: string; marks: number; hit: boolean; future: boolean }[];
  streak: number;
  rank: number | null;
  projectRanks: Record<string, number | null>;
  leaderboard: { from: string; to: string; overall: Ranked[]; projects: Record<string, Ranked[]> };
  person: { userId: string; name: string };
};

export type Idea = {
  id: number; user_id: string; user_name: string; project_id: string; site: string;
  title: string; problem: string; idea: string; expected_result: string; metric: string;
  test_plan?: string; effort?: string; week?: string | null;
  status: 'new' | 'shortlisted' | 'in_trial' | 'worked' | 'didnt_work';
  result_note: string; month_won: string | null; created_at: string;
  votes: number; votedByMe: boolean; isMine: boolean;
};

export type ReportRow = {
  userId: string; name: string; email: string; marks: number; daysHit: number; days: number;
  pctHit: number; target: number;
  projects: Record<string, { marks: number; items: number; pending: number }>;
  badges: { month: string; idea_id: number }[];
};

export type LevelRow = {
  userId: string; name: string; email: string; project: string; level: number; levelName: string;
  xp: number; streak: number; target: number; ready: boolean;
  todayPoints: number; todayDone: boolean; todayLinks: number;
  site?: string; domain?: string; hue?: string;
};

export const IDEA_LABEL: Record<Idea['status'], string> = {
  new: 'New',
  shortlisted: 'Shortlisted',
  in_trial: 'In trial',
  worked: 'Worked ✅',
  didnt_work: "Didn't work",
};

export function msg(error: unknown, fallback = 'Something went wrong.'): string {
  const data = (error as { response?: { data?: { message?: string; detail?: unknown } } })?.response?.data;
  if (data?.message) return data.message;
  if (typeof data?.detail === 'string') return data.detail;
  return (error as { message?: string })?.message || fallback;
}

export const is404 = (error: unknown) =>
  (error as { response?: { status?: number } })?.response?.status === 404;

export const trackerApi = {
  status: () => api.get<TrackerStatus>('/api/tasks/status'),
  workTypes: () => api.get<{ types: WorkType[] }>('/api/tasks/work-types'),
  saveWorkTypes: (types: Partial<WorkType>[]) => api.put<{ types: WorkType[] }>('/api/tasks/work-types', { types }),
  logs: (params: { date?: string; project_id?: string; user_id?: string }) =>
    api.get<{ date: string; logs: Log[] }>('/api/tasks/logs', { params }),
  createLog: (body: Record<string, unknown>) =>
    api.post<{ log: Log; late: boolean; message: string }>('/api/tasks/logs', body),
  updateLog: (id: number, body: Record<string, unknown>) => api.put<{ log: Log }>(`/api/tasks/logs/${id}`, body),
  deleteLog: (id: number) => api.delete(`/api/tasks/logs/${id}`),
  review: (id: number, body: { status: string; quality?: number; note?: string }) =>
    api.post<{ log: Log }>(`/api/tasks/logs/${id}/review`, body),
  reviewBulk: (body: { ids: number[]; status: string; quality?: number }) =>
    api.post<{ reviewed: number }>('/api/tasks/logs/review-bulk', body),
  queue: () => api.get<{ logs: Log[]; ideas: Idea[]; tasks?: import('@/lib/tasks').Task[] }>('/api/tasks/review-queue'),
  summary: (range: 'day' | 'week' | 'month', user_id?: string) =>
    api.get<Summary>('/api/tasks/summary', { params: { range, user_id } }),
  report: (start?: string, end?: string) =>
    api.get<{ from: string; to: string; people: ReportRow[] }>('/api/tasks/report', { params: { start, end } }),
  exportCsv: (start?: string, end?: string) =>
    api.get<Blob>('/api/tasks/export.csv', { params: { start, end }, responseType: 'blob' }),
  importCsv: (csv: string) =>
    api.post<{ added: number; skipped: { row: number; why: string }[] }>('/api/tasks/import', { csv }),
  saveSettings: (body: Record<string, number>) => api.put('/api/tasks/settings', body),
  setTarget: (user_id: string, daily_marks_target: number) =>
    api.put('/api/tasks/targets', { user_id, daily_marks_target }),
  ideas: (params: { project_id?: string; status?: string } = {}) =>
    api.get<{ ideas: Idea[]; winners: { month: string; user_name: string; idea_id: number }[] }>('/api/ideas', { params }),
  createIdea: (body: Record<string, string>) => api.post<{ idea: Idea }>('/api/ideas', body),
  ideaStatus: (id: number, body: { status: string; result_note?: string }) =>
    api.post<{ idea: Idea }>(`/api/ideas/${id}/status`, body),
  vote: (id: number) => api.post<{ idea: Idea }>(`/api/ideas/${id}/vote`),
  myLevels: () => api.get<{ rows: LevelRow[]; readyAfter: number }>('/api/seo/backlink-ops/levels'),
  allLevels: () =>
    api.get<{
      rows: LevelRow[];
      projects: Record<string, { short: string; hue: string; active: boolean }>;
      unmatched: { name: string; email: string; project: string }[];
    }>('/api/seo/backlink-ops/levels/all'),
};
