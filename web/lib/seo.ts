import api from '@/lib/api';

/* Types mirror app/seo/schemas.py. Kept hand-written rather than generated so
   the frontend stays buildable without a codegen step in the deploy. */

export type ArticleType = 'onpage' | 'content';
export type Vertical = 'rpa' | 'n8n' | 'whatsapp' | 'agentic_ai';
export type Country = 'india' | 'nz' | 'ireland' | 'uk';
export type BuyerIntent = 'informational' | 'commercial' | 'transactional';
export type ArticleStatus =
  | 'drafted_by_author'
  | 'in_team_review'
  | 'submitted_for_scoring'
  | 'author_review'
  | 'ready_to_publish'
  | 'published'
  | 'archived';

export const VERTICAL_LABELS: Record<Vertical, string> = {
  whatsapp: 'WhatsApp Automation',
  rpa: 'RPA',
  n8n: 'n8n',
  agentic_ai: 'Agentic AI',
};

export const COUNTRY_LABELS: Record<Country, string> = {
  india: 'India',
  nz: 'New Zealand',
  ireland: 'Ireland',
  uk: 'United Kingdom',
};

/* The server is the authority on this matrix (it re-validates every write);
   this copy only drives the country dropdown so the UI can disable invalid
   options before the request is sent. */
export const APPROVED_MATRIX: Record<Vertical, Country[]> = {
  whatsapp: ['india'],
  rpa: ['nz', 'ireland', 'uk'],
  n8n: ['nz', 'ireland', 'uk', 'india'],
  agentic_ai: ['india', 'nz', 'ireland', 'uk'],
};

export interface Article {
  id: string;
  type: ArticleType;
  status: ArticleStatus;
  title: string | null;
  slug: string | null;
  vertical: Vertical;
  country: Country | null;
  primary_keyword: string;
  keyword_difficulty: number | null;
  monthly_search_volume: number | null;
  buyer_intent: BuyerIntent | null;
  assigned_to: number | null;
  current_score: number | null;
  featured_image_path: string | null;
  featured_image_alt: string | null;
  meta_title: string | null;
  meta_description: string | null;
  wp_post_id: number | null;
  wp_published_url: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export interface ArticleFaq {
  id: string;
  question: string;
  answer: string | null;
  source_url: string | null;
  source_platform: string | null;
  position_in_article: number | null;
}

export interface ArticleDetail extends Article {
  author_draft_md: string | null;
  team_edit_md: string | null;
  final_md: string | null;
  from_author_story: string | null;
  ubersuggest_raw: string | null;
  competitor_urls: Record<string, unknown> | null;
  sources: {
    id: string;
    source_url: string | null;
    source_platform: string | null;
    question_or_prompt: string | null;
  }[];
  faqs: ArticleFaq[];
}

export interface ScoreComment {
  line_number: number;
  current_text: string;
  suggested_fix: string;
  impact_points: number;
  parameter?: string;
}

export interface ScoreParameter {
  key: string;
  label: string;
  group: string;
  points_available: number;
  points_earned: number;
  detail?: string | null;
  implemented: boolean;
}

export interface RankMathTest {
  key: string;
  label: string;
  group: string;
  group_label: string;
  points_earned: number;
  points_available: number;
  passed: boolean;
  message: string;
  informational: boolean;
}

/* Rank Math's own test suite, computed server-side from the draft. Reported
   next to the house score, never merged into it — see services/rankmath.py. */
export interface RankMathReport {
  total_score: number;
  max_score: number;
  grade: string;
  groups: Record<string, { label: string; earned: number; available: number }>;
  tests: RankMathTest[];
  failed: string[];
}

export interface ScoreReport {
  article_id: string;
  version_number: number;
  total_score: number;
  max_score: number;
  groups: Record<string, Record<string, number>>;
  parameters: ScoreParameter[];
  comments: ScoreComment[];
  scored_at: string;
  blocking_issues: string[];
  rank_math?: RankMathReport | null;
}

export interface ManualFaqInput {
  question: string;
  answer: string;
  source_url?: string | null;
}

export interface PullRequest {
  id: string;
  source_platform: 'reddit' | 'quora' | 'paa' | 'answerthepublic';
  source_url: string | null;
  question_captured: string;
  suggested_vertical: Vertical | null;
  suggested_country: Country | null;
  captured_at: string | null;
  converted_to_article_id: string | null;
}

export interface CalendarRow {
  id: string;
  week_number: number | null;
  article_type: ArticleType;
  vertical: Vertical;
  country: Country | null;
  title: string | null;
  primary_keyword: string | null;
  kd: number | null;
  volume: number | null;
  buyer_intent: BuyerIntent | null;
  assigned_to: number | null;
  article_id: string | null;
}

export interface KpiCardData {
  key: string;
  label: string;
  value: number;
  unit: string | null;
  delta: number | null;
  delta_label: string | null;
  target: number | null;
  percent_of_target: number | null;
  direction: 'up' | 'down' | 'flat';
  healthy: boolean | null;
}

export interface Projection {
  label: string;
  current_value: number;
  target_value: number;
  avg_daily_gain: number | null;
  projected_date: string | null;
  confidence_days: number | null;
  days_remaining: number | null;
  status: string;
  message: string;
}

export interface SeriesPoint {
  date: string;
  value: number;
  secondary: number | null;
}

export interface TeamMember {
  user_id: number;
  full_name: string;
  email: string;
  role: string;
  articles_this_week: number;
  articles_published: number;
  avg_score: number | null;
  backlinks_earned: number;
  streak_days: number;
  last_login_at: string | null;
}

export interface Recommendation {
  id: string;
  priority: 'high' | 'medium' | 'low';
  category: 'technical' | 'content' | 'backlink' | 'ranking';
  title: string;
  description: string | null;
  action_required: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ActivityEntry {
  id: number;
  user_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: string | null;
  created_at: string;
}

export interface DashboardHome {
  kpis: KpiCardData[];
  projections: Projection[];
  publish_velocity: SeriesPoint[];
  publish_velocity_weekly_avg: number;
  gsc_series: SeriesPoint[];
  team: TeamMember[];
  recommendations: Recommendation[];
  activity: ActivityEntry[];
  go_live_approved: boolean;
  go_live_message: string;
}

/** Turn a FastAPI error body into one line a human can act on. */
export function apiError(error: unknown, fallback = 'Something went wrong.'): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  if (!detail) {
    const message = (error as { message?: string })?.message;
    return message || fallback;
  }
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === 'string' ? d : d?.msg ?? JSON.stringify(d)))
      .join('; ');
  }
  const obj = detail as Record<string, unknown>;
  if (typeof obj.message === 'string') return obj.message;
  if (Array.isArray(obj.blocking_issues)) return (obj.blocking_issues as string[]).join(' ');
  return JSON.stringify(detail);
}

export const seoApi = {
  dashboardHome: () => api.get<DashboardHome>('/api/seo/dashboard/home'),
  siteHealth: () => api.get('/api/seo/dashboard/site-health'),
  teamStats: () => api.get<TeamMember[]>('/api/seo/dashboard/team-stats'),

  listArticles: (params: Record<string, string | undefined> = {}) =>
    api.get<Article[]>('/api/seo/articles', { params }),
  getArticle: (id: string) => api.get<ArticleDetail>(`/api/seo/articles/${id}`),
  /* Write-it-yourself. No LLM key involved on either call. */
  createManual: (body: Record<string, unknown>) =>
    api.post<ArticleDetail>('/api/seo/articles', body),
  saveDraft: (id: string, body: Record<string, unknown>) =>
    api.put<ArticleDetail>(`/api/seo/articles/${id}/write`, body),
  /* Optional assisted route; requires ANTHROPIC_API_KEY on the server. */
  generate: (body: Record<string, unknown>) =>
    api.post<ArticleDetail>('/api/seo/articles/generate', body),
  teamEdit: (id: string, body: Record<string, unknown>) =>
    api.put<ArticleDetail>(`/api/seo/articles/${id}/team-edit`, body),
  score: (id: string) => api.post<ScoreReport>(`/api/seo/articles/${id}/score`),
  submitForAuthor: (id: string, minScore: number) =>
    api.post(`/api/seo/articles/${id}/submit-for-author`, null, {
      params: { min_score: minScore },
    }),
  setFromAuthor: (id: string, story: string) =>
    api.put(`/api/seo/articles/${id}/from-author-story`, { from_author_story: story }),
  uploadImage: (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`/api/seo/articles/${id}/upload-image`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  generateAlt: (id: string) => api.post(`/api/seo/articles/${id}/generate-alt`),
  publish: (id: string) => api.post(`/api/seo/articles/${id}/publish`),

  listPullRequests: (params: Record<string, string | undefined> = {}) =>
    api.get<PullRequest[]>('/api/seo/pull-requests', { params }),
  createPullRequest: (body: Record<string, unknown>) =>
    api.post('/api/seo/pull-requests', body),
  convertPullRequest: (id: string, body: Record<string, unknown>) =>
    api.post(`/api/seo/pull-requests/${id}/convert-to-article`, body),

  calendar: () => api.get<CalendarRow[]>('/api/seo/calendar'),
  importCalendar: (file: File, replace: boolean) => {
    const form = new FormData();
    form.append('file', file);
    return api.post('/api/seo/calendar/import-csv', form, {
      params: { replace },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  recommendations: (params: Record<string, string | undefined> = {}) =>
    api.get<Recommendation[]>('/api/seo/recommendations', { params }),
  resolveRecommendation: (id: string) =>
    api.post(`/api/seo/recommendations/${id}/resolve`),
  audits: (params: Record<string, string | undefined> = {}) =>
    api.get('/api/seo/audits', { params }),

  backlinks: () => api.get('/api/seo/backlinks'),
  addBacklink: (body: Record<string, unknown>) => api.post('/api/seo/backlinks', body),

  matrix: () => api.get('/api/seo/matrix'),
  integrationHealth: () => api.get('/api/seo/health/integrations'),
  recordDomainRating: (value: number) =>
    api.post('/api/seo/metrics/domain-rating', { domain_rating: value }),
};
