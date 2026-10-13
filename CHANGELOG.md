# Changelog

Newest first. Production state per feature lives in `docs/FEATURE_LOG.md`.

## 2026-10-13 · Dashboard work order (branch `feat/daily-tracker-levels`), not deployed yet

- **Fix (T1):** people rostered on a website now always see it on Backlink Ops, even when it is
  marked not live. The roster matches logins by email, or by name ignoring case. Roster rows that
  match no login are listed for the superuser. whatsappautomation.co.in now ships live.
- **Backlink Ops 1.3.0 (T2, flag `FEATURE_PER_PROJECT_LEVELS`):** level, XP and streak per person
  per website; your Today score is your own links at your own level; superuser grid to set levels.
- **Removed (T3):** the static `/articles/` page (redirects home; archived). Blog publishing unchanged.
- **New (T4, flags `FEATURE_DAILY_TRACKER`, `FEATURE_IDEA_BOARD`):** Daily Tracker at `/tasks/`.
  Proof-backed work logs, review with quality, late = 50%, duplicate block, Backlink Ops rows
  shown automatically, targets, streaks, heatmap, leaderboards, CSV, sheet import. Plus the
  Idea Board with monthly winner badges.
- Homepage Workspace cards and My levels; nav gains Backlink Ops, Daily Tracker, Invoices (admin)
  and a phone row.
