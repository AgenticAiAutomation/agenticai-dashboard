# Blog Playbook writer (flagged)

An "answer-first" way to write blog posts: TL;DR up top, short question
sections with one visual each, a real example, a cost table, a CTA. The writer
page gets a **Playbook** mode that builds this as a form, beside the existing
**Raw Markdown** editor.

Source brief: `BLOG_PLAYBOOK_DASHBOARD_CHANGES_5thOct2026.md` (Jai, 2026-10-05).

## What it does not touch

The SEO gate is frozen. None of these files changed:

| File | Why it matters |
|---|---|
| `api/app/seo/services/scoring.py` | House score, `PUBLISH_MIN_SCORE = 80` |
| `api/app/seo/services/rankmath.py` | Rank Math parity |
| `api/app/seo/golive.py` | Go-live gate |
| `api/app/seo/services/publisher.py` | JSON contract, `schema_version: 1` |
| Site `blog.py` `SUPPORTED_SCHEMA_VERSION`, JSON-LD in `blog-post.html` | Website contract, schema |

The publish checks in `routes/articles.py` (`_blocking_issues`) are unchanged.
The one publish-route line that changed is the Markdown→HTML conversion. It
uses the Playbook converter only when the flag is on **and** the body opens with
a TL;DR. Anything else gets the old converter, byte for byte.

## The flag

| Setting (`api/.env` or systemd drop-in) | Default | Effect |
|---|---|---|
| `BLOG_PLAYBOOK_ENABLED` | `false` | `true` = on for every SEO login |
| `BLOG_PLAYBOOK_USERS` | empty | Comma-separated emails that get it while the flag is false |

**Day to day, admins grant it in the dashboard:** Users → *Blog Playbook
access*. Tick logins (or "Everyone who can write articles") and Save. The list
is stored in `api/instance/blog_playbook_access.json` (setting
`BLOG_PLAYBOOK_ACCESS_FILE`), and every change is audit-logged. The file only
adds people on top of the two server settings. `ops/blog-playbook-flag.sh off`
removes the drop-in and moves the file aside, so one command still turns it off
for everyone.

Flag off: no mode switch, no builder, no Skim dial. The save payload is the same
as before. `playbook_blocks` sent to the API is ignored. Draft generation uses the
old prompt, and publishing uses the old converter.

## How it works

The builder edits blocks. `web/lib/playbook.ts` `compose()` turns them into the
same Markdown `body_md` the raw editor writes. Scoring, Rank Math, publishing
and the website see an ordinary article.

The blocks are also saved in `seo_articles.playbook_blocks` so the builder can
reopen them. That column is written with plain SQL (`app/seo/playbook.py`) and is
**not mapped** on `SeoArticle`. With the flag off, nothing reads it.

**Never silently rewrite:** an article opens in Playbook mode only if its saved
blocks (or a parse of its body) compose to the body *exactly*. Otherwise it
opens in Raw Markdown. A raw-edited article is never overwritten by stale blocks.
The AI's blocks are offered by an explicit button that says it replaces the body.

### Markdown conventions

```
# Title with keyword and a number

> **TL;DR**
>
> - bullet with the keyword
> - bullet
> - bullet

> **Who this is for:** one line

## A question as the H2?

Short answer paragraph.

1. steps / a | table | / > **Flow:** A → B → C / ![alt](url)

> **Tip:** …   > **Watch out:** …   > **Pro tip:** …

## What does this look like for a real business?

> **Real example:** client type
>
> **Before:** …
>
> **After:** …
>
> - **Metric:** value

## What does it cost and how long does it take?

| Item | One-time | Monthly | Time |
|---|---|---|---|

[FROM AUTHOR: real production story, written by the author]

> **Next step:** lead-in [Book a free 30-minute call](https://calendly.com/agenticaiautomation)
```

Blockquotes, not HTML: `strip_markdown()` removes `>` and `**`, so the scorer
counts clean words. The `>` line before the TL;DR bullets is required or the
bullets render as plain text.

**Changes against the brief:**

- `Flow:` and `Next step:` labels were added so flows and the CTA can be styled.
- In Playbook posts only, a leftover `[FROM AUTHOR: …]` line is dropped at
  publish. The site already prints the story in its own box.
- The cost and real-example blocks carry their own question H2.

CTA targets: Calendly `calendly.com/agenticaiautomation`, WhatsApp
`wa.me/917982881739`, funnel `wa.agenticaiautomation.co`.

## Skim score (advisory)

`api/app/seo/services/skim.py`, out of 100. **Never blocks publish.** It is not
imported by `scoring.py` or read by the publish route.

| Check | Points |
|---|---|
| TL;DR present (8), exactly 3 bullets (6), keyword in the first (6) | 20 |
| No H2 section over 250 words (proportional) | 20 |
| Something visual every ≤ 300 words of text (proportional) | 20 |
| Real example with ≥ 2 numbers (5 if present with fewer) | 15 |
| Table present | 10 |
| CTA present | 10 |
| First paragraph ≤ 60 words | 5 |

## Why publishing needs its own converter

The legacy converter puts a blank line before every block line. As a result:

- every table row becomes its own paragraph, so tables never render;
- Python-Markdown merges neighbouring blockquotes, so the TL;DR and "Who" become one box.

`services/playbook_render.py` keeps same-kind lines together and gives every
blockquote its own element. If it raises, publishing falls back to the legacy
converter.

## Website (`AgenticWeb`, branch `feat/blog-playbook`)

- `blog.py` `playbook_html` filter, registered in `app.py`. It acts only on posts
  with a TL;DR block. It adds `pb-tldr / pb-who / pb-tip / pb-warn / pb-example /
  pb-flow / pb-cta` classes and wraps tables in `.table-scroll`. Older posts are
  returned as the identical string.
- `templates/blog-post.html`: `{{ article.html | playbook_html | safe }}`.
- Styles: `static/assets/css/components.css`, **not** `static/css/theme.css` as
  the brief said. `blog-post.html` loads only `static/assets/css/*`, so rules in
  `theme.css` would never reach a post. The site's own tokens are used (`--good`,
  `--warn`, `--orange`, `--carbon-2`). `--accent-wash` and `--pass` exist only
  in `theme.css`.

## Tests

| Suite | Command | Covers |
|---|---|---|
| Composer | `node tests/playbook/compose.test.mts` | §6.2 one H1, ≥3 H2, keyword in first 100 words, no HTML; §6.3 round trip; never-rewrite rule |
| API | `python -m pytest tests/test_blog_playbook.py -q` | §6.1 parity flag on/off, §6.4 flag off, §6.6 gate 79/80, skim, converter, routes |
| Existing | `python tests/smoke.py` (in `api/`), `python -m pytest tests/test_autoreview.py tests/test_scoring.py -q` | Unchanged behaviour |
| Website | `python -m pytest tests/test_blog_playbook.py -q` (site repo) | §6.5 old post byte-identical, Playbook post styled |
| Live parity | `python -m scripts.playbook_score_parity` (see below) | §1 every real article, before vs after |

`tests/playbook/sample.md` is the composer's output. The Python tests score and
render that file, so both languages test the same bytes. Refresh it with
`node tests/playbook/compose.test.mts --write-fixture`.

## Deploy order

1. Copy `api/scripts/playbook_score_parity.py` to `/root`, then from
   `/var/www/agenticai-dashboard/api` run
   `venv/bin/python /root/playbook_score_parity.py --out /root/parity-before.json`
   (the old code is still checked out; the script only reads)
2. Migration: `alembic upgrade head` (adds the nullable column)
3. API with flag **off**; restart; then
   `python -m scripts.playbook_score_parity --out /root/parity-after.json` and
   `--compare /root/parity-before.json /root/parity-after.json` → must say OK
4. Website filter + CSS (site repo)
5. Frontend build + upload
6. `BLOG_PLAYBOOK_USERS=<Jai's login email>`, restart → one test article
7. `BLOG_PLAYBOOK_ENABLED=true` for the SEO team

**Migration note:** `feat/blog-engine-v2` also has a revision `003` that revises
`002`. Whichever lands second must point its `down_revision` at the other.

Rollback: see `docs/BCP_AND_ROLLBACK.md` → *Blog Playbook*.
