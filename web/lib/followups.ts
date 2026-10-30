import api from '@/lib/api';

/* Follow-ups (CRM) — /api/followups/*. Errors come as {error, message}. */

export type Contact = {
  id: number; name: string; company: string; phone: string; whatsapp: string; email: string; city: string;
  notes: string; lead_id: number | null; waLink: string; telLink: string;
  lastLog: { text: string; at: string } | null;
  followups?: Followup[]; notes_list?: never;
};
export type Note = { id: number; text: string; created_by: string; created_at: string };
export type Kind = 'call' | 'meeting' | 'payment' | 'whatsapp' | 'email' | 'other';
export type Followup = {
  id: number; contact_id: number; kind: Kind; title: string; due_at: string; all_day: number;
  priority: 'P1' | 'P2' | 'P3'; location: string; status: 'open' | 'done' | 'cancelled';
  outcome: string; done_at: string | null; done_by: string | null; prev_id: number | null;
  guide: string; overdue: boolean; today: boolean; contact: Contact;
};
export type Board = {
  now: string; todo: Followup[]; overdue: number; today: number; upcoming: Followup[]; later: number;
  done: Followup[]; kinds: Record<Kind, string>;
};

export type Project = {
  id: number; name: string; site_id: string; contact_id: number | null; billing: 'one_time' | 'recurring';
  cycle: 'monthly' | 'quarterly' | 'half_yearly' | 'yearly'; next_due: string | null; amount_note: string;
  notes: string; active: number; contact: Contact | null; daysToDue?: number;
  reminder: { id: number; due_at: string; status: string } | null;
};

export const KIND_LABEL: Record<Kind, string> = {
  call: '📞 Call', meeting: '🤝 Meeting', payment: '₹ Payment', whatsapp: '💬 WhatsApp', email: '✉ Email', other: '• Other',
};
export const PRI_STYLE: Record<string, string> = {
  P1: 'text-danger border-danger/40 bg-danger/10', P2: 'text-warning border-warning/40 bg-warning/10',
  P3: 'text-slate-300 border-line bg-raised',
};

export const when = (s: string, allDay?: number) => {
  const d = new Date(s.replace(' ', 'T'));
  const date = d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
  return allDay ? date : `${date}, ${d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}`;
};

export const fuApi = {
  status: () => api.get<{ allowed: boolean; superuser: boolean }>('/api/followups/status'),
  team: () => api.get<{ team: { email: string; name: string; added_at: string }[] }>('/api/followups/team'),
  teamAdd: (email: string, name: string) => api.post<{ team: { email: string; name: string; added_at: string }[] }>('/api/followups/team', { email, name }),
  teamRemove: (email: string) => api.post<{ team: { email: string; name: string; added_at: string }[] }>('/api/followups/team/remove', { email }),
  board: () => api.get<Board>('/api/followups/board'),
  calendar: (start?: string, end?: string) =>
    api.get<{ from: string; to: string; items: Followup[] }>('/api/followups/calendar', { params: { start, end } }),
  create: (body: Record<string, unknown>) => api.post<{ followup: Followup }>('/api/followups/items', body),
  update: (id: number, body: Record<string, unknown>) => api.put<{ followup: Followup }>(`/api/followups/items/${id}`, body),
  done: (id: number, outcome: string, next?: Record<string, unknown>) =>
    api.post<{ followup: Followup; next?: Followup }>(`/api/followups/items/${id}/done`, { outcome, next }),
  snooze: (id: number, due_at?: string) => api.post<{ followup: Followup }>(`/api/followups/items/${id}/snooze`, { due_at }),
  contacts: (q?: string) => api.get<{ contacts: Contact[] }>('/api/followups/contacts', { params: { q } }),
  contact: (id: number) => api.get<{ contact: Contact & { followups: Followup[]; notes: Note[] } }>(`/api/followups/contacts/${id}`),
  createContact: (body: Record<string, unknown>) => api.post<{ contact: Contact }>('/api/followups/contacts', body),
  updateContact: (id: number, body: Record<string, unknown>) => api.put<{ contact: Contact }>(`/api/followups/contacts/${id}`, body),
  projects: () => api.get<{ projects: Project[]; sites: Record<string, string>; cycles: string[]; remindDays: number }>('/api/followups/projects'),
  createProject: (body: Record<string, unknown>) => api.post<{ project: Project }>('/api/followups/projects', body),
  updateProject: (id: number, body: Record<string, unknown>) => api.put<{ project: Project }>(`/api/followups/projects/${id}`, body),
  note: (id: number, text: string) => api.post(`/api/followups/contacts/${id}/notes`, { text }),
};
