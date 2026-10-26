import data from './routes.json';

/* The route registry (web/lib/routes.json) — the ONE list of dashboard pages.
   Nav, SEO sub-tabs and the homepage grid all read it through these helpers. */

export type Group = 'SEO' | 'Content' | 'Team' | 'Finance' | 'Admin';
export type Flag = 'tracker' | 'ideas' | 'taskManager' | 'tasksV2' | 'followups';

export type RouteEntry = {
  slug: string;
  title: string;
  icon: string;
  group: Group;
  roles: 'all' | string[];
  status: 'live' | 'hidden' | 'planned' | 'removed';
  purpose: string;
  nav?: boolean;
  navTitle?: string;
  tab?: number;
  pin?: number;
  tabTitle?: string;
  server?: boolean;
  requires?: Flag;
};

export const GROUPS = data.groups as Group[];
export const ROUTES = data.routes as RouteEntry[];
export const PUBLIC_ORIGIN = 'https://dashboard.agenticaiautomation.co';

export const isAdminRole = (role: string | null | undefined) => role === 'owner' || role === 'admin';

export function allowed(r: RouteEntry, role: string | null | undefined): boolean {
  if (r.roles === 'all') return true;
  // owner = Jai (legacy-equivalent to admin): sees everything.
  if (role === 'owner') return true;
  return !!role && r.roles.includes(role);
}

/** Flags reported by /api/tasks/status; unknown (null) hides flagged entries. */
export type Flags = Partial<Record<Flag, boolean>> | null;

function flagOk(r: RouteEntry, flags: Flags) {
  return !r.requires || !!flags?.[r.requires];
}

/** Homepage cards: live pages this role may open, in registry order, grouped. */
export function homeGroups(role: string | null | undefined, flags: Flags) {
  return GROUPS.map((g) => ({
    group: g,
    routes: ROUTES.filter((r) => r.group === g && r.status === 'live' && allowed(r, role) && flagOk(r, flags)),
  })).filter((g) => g.routes.length > 0);
}

/** The homepage's top row: the desks people open every day. */
export function pinnedRoutes(role: string | null | undefined, flags: Flags) {
  return ROUTES.filter((r) => r.pin && r.status === 'live' && allowed(r, role) && flagOk(r, flags))
    .sort((a, b) => (a.pin ?? 0) - (b.pin ?? 0));
}

export function navRoutes(role: string | null | undefined) {
  return ROUTES.filter((r) => r.nav && r.status === 'live' && allowed(r, role));
}

export function seoTabs(role: string | null | undefined) {
  return ROUTES.filter((r) => r.tab && (r.status === 'live' || r.status === 'hidden') && allowed(r, role))
    .sort((a, b) => (a.tab ?? 0) - (b.tab ?? 0));
}

/** Next.js routes compare without the trailing slash, query or hash. */
export const pathOf = (slug: string) => slug.replace(/[?#].*$/, '').replace(/\/$/, '') || '/';
