# Removed 2026-10-13 (work order T3)

| File | Was | Restore |
|---|---|---|
| `web/app/articles/page.tsx` | The static `/articles/` page: a flat list of the legacy `articles` table with a status toggle. | `git mv archive/removed_2026-10-13/web/app/articles/page.tsx web/app/articles/page.tsx`, re-add `{ href: '/articles', label: 'Articles' }` to `PRIMARY` in `web/components/Nav.tsx`, rebuild the frontend. |

What was **not** removed, on purpose:

- The `/articles` API router (`api/app/routes/articles.py`). `/countries/` still reads it.
- Blog publishing. It runs through `/api/seo/articles` and `api/app/seo/services/publisher.py`,
  which writes `published/articles/*.json` for agenticaiautomation.co/blog. The removed page never touched it.
- The SEO → Articles tab (`/dashboard/seo/articles`), which is the real article pipeline.

`/articles/` now redirects to `/` (which sends a signed-in user to `/dashboard`), so bookmarks do not 404.
