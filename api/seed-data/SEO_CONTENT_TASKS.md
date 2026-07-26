# AgenticAiAutomation — SEO Content System Task Tracker
_Source: v3.1 mega-prompt, adapted to reality. Owner: Jai. Domain: agenticaiautomation.co_

---

## Reality check (read once, then execute)

The v3.1 prompt targets global agentic-AI SERPs. On a fresh domain with low DR, competing against LangChain / Anthropic / CrewAI docs, "rank #1 fast worldwide" is fantasy. This tracker keeps the prompt's structural rigor but re-aims it at winnable SERPs first, then scales.

**Strategic corrections applied to the v3.1 prompt:**
1. Domain fixed: `agenticaiautomation.co` (not .com)
2. Geo focus: **India-first, English** — matches actual ICP (Indian SMEs, APAC, UAE); global comes later
3. Cadence: **2 pillars/month + 2–3 supporting posts/week**, not daily
4. Angle: **"Agentic AI for Indian SMEs & mid-market ops"** — winnable niche, not "definitive global guide"
5. Monolithic prompt split into 3 chained prompts (see Phase 3)

---

## Working protocol (saves tokens every turn)

When starting a task, paste **only**:
> "Working on Phase X, Task Y. Context in SEO_CONTENT_TASKS.md."

Do not re-paste the v3.1 prompt. It's absorbed into Phase 3.
I read the task, ask for the one missing input (if any), deliver that task's output, update the checkbox. No context reload.

Deliverables live in `/agenticai-seo/` alongside this file:
- `positioning.md` (Phase 0 output)
- `keyword-cluster.md` (Phase 1)
- `content-map.md` (Phase 2)
- `prompts/brief.md`, `prompts/article.md`, `prompts/pack.md` (Phase 3)
- `articles/<slug>.md` (Phase 4)

---

## Phase 0 — Strategic decisions (BLOCKER for everything else)

Answer these once. Nothing downstream works without them.

- [ ] **0.1** Confirmed target geo: India-first (recommended) OR geo-neutral OR global
- [ ] **0.2** ICP priority ranking (1 = highest):
  - [ ] SME founders (Indian, ₹1–50 Cr revenue)
  - [ ] Mid-market ops/COO
  - [ ] Enterprise digital transformation
  - [ ] Agencies reselling your work
- [ ] **0.3** Primary content goal: (a) demo bookings, (b) SEO authority for product exit, (c) both — with weight
- [ ] **0.4** Existing content on `agenticaiautomation.co` — paste list of live URLs (or "none")
- [ ] **0.5** Realistic weekly hours you or writer can commit
- [ ] **0.6** Budget for tools (Ahrefs/SEMrush/Surfer/none)

**Output:** `positioning.md` — one paragraph, pinned to top of every future prompt.

---

## Phase 1 — Keyword & topical cluster map

- [ ] **1.1** Generate 40 seed keywords (mix: head + long-tail + commercial + informational)
- [ ] **1.2** Score each on: search intent, competition proxy (0–3), business-fit (0–3), quick-win potential
- [ ] **1.3** Kill anything scoring <4 combined
- [ ] **1.4** Group survivors into 5–7 pillar clusters
- [ ] **1.5** Assign 5–10 supporting long-tail per pillar

**Output:** `keyword-cluster.md` — table format, ready to feed into content map.

**Input I need from you before starting:** Phase 0 answers + any keywords you already believe you should rank for.

---

## Phase 2 — Content architecture

- [ ] **2.1** Define 5–7 pillar pages (2500–4000 words each)
- [ ] **2.2** Define supporting cluster posts per pillar (5–10 each, 1500–2200 words)
- [ ] **2.3** URL slug convention (short, keyword-first, no dates)
- [ ] **2.4** Internal linking map (pillar ↔ cluster, cluster ↔ cluster where relevant)
- [ ] **2.5** Publishing sequence (which pillar first, which cluster posts feed it)

**Output:** `content-map.md` — visual-ish tree + numbered publish order.

---

## Phase 3 — Refine & split the v3.1 prompt

The monolithic prompt burns tokens and dilutes quality. Split into three chained prompts.

- [ ] **3.1** Write `prompts/brief.md` — takes: keyword + intent + positioning. Outputs: SEO brief only (meta, keywords, LSI, SERP features, slug, internal links). ~30% of v3.1's structure.
- [ ] **3.2** Write `prompts/article.md` — takes: brief. Outputs: article body only (H1→conclusion, no schema, no FAQ, no social). ~50% of v3.1's structure.
- [ ] **3.3** Write `prompts/pack.md` — takes: article. Outputs: schema JSON-LD + FAQ block + image alt/caption pack + social snippets + hashtag pack. ~20% of v3.1's structure.
- [ ] **3.4** Fix v3.1's broken bits: domain, geo, realistic ranking claims, remove "daily publishing" pressure

**Output:** 3 prompt files, each self-contained. Reused for every article going forward.

---

## Phase 4 — Article production pipeline

Fill in after Phase 1 (keyword map).

Template row per article:
- [ ] **4.x.a** Run `prompts/brief.md` → save `articles/<slug>-brief.md`
- [ ] **4.x.b** Human review of brief (5 min gate — is this actually different from top 3 SERP?)
- [ ] **4.x.c** Run `prompts/article.md` → save `articles/<slug>.md`
- [ ] **4.x.d** Run `prompts/pack.md` → append schema/FAQ/social
- [ ] **4.x.e** Publish to Flask site, add to sitemap
- [ ] **4.x.f** Distribution loop (Phase 6)
- [ ] **4.x.g** Log in tracker: publish date, target keyword, initial position at day 7 / 30 / 90

**First article:** [TBD after Phase 1]

---

## Phase 5 — Technical SEO baseline (one-time, do in parallel with Phase 1)

- [ ] **5.1** `robots.txt` reviewed — no accidental blocks
- [ ] **5.2** `sitemap.xml` auto-generated and pinged to GSC
- [ ] **5.3** GSC verification finalized (tag already prepped per prior work)
- [ ] **5.4** Bing Webmaster Tools added
- [ ] **5.5** Sitewide schema: Organization + WebSite (with SearchAction)
- [ ] **5.6** Breadcrumb schema on all article pages
- [ ] **5.7** Blog index page + pagination (`/blog`, `/blog/page/2`)
- [ ] **5.8** Core Web Vitals audit (Flask/Gunicorn on port 5001) — LCP, CLS, INP
- [ ] **5.9** Analytics wired (GA4 or Plausible — decide)
- [ ] **5.10** Author bio pages with E-E-A-T signals (your 11yr IT + 9yr automation background)
- [ ] **5.11** `hreflang` — skip unless multi-geo confirmed in Phase 0

---

## Phase 6 — Distribution loop (without this, nothing ranks on a young domain)

Per article, every time. Non-negotiable.

- [ ] **6.1** LinkedIn post from Jai's founder profile (native post, not just link)
- [ ] **6.2** X/Twitter thread (5–7 tweets, thread hook = article's uncomfortable truth)
- [ ] **6.3** Relevant Reddit — r/IndianStartups, r/EntrepreneurRideAlong, r/automation (add value, don't spam-drop)
- [ ] **6.4** Newsletter send (even 50 subs = signal)
- [ ] **6.5** Repurpose into WhatsApp status / broadcast (your actual channel)
- [ ] **6.6** Backlink pitches: 3 guest posts/month target, HARO-style responses to journalist queries

**Monthly rhythm:** 1 dedicated hour/week for distribution per article for its first 30 days.

---

## Progress log

| Date | Phase.Task | Status | Notes |
|------|-----------|--------|-------|
| 2026-07-25 | Tracker created | ✅ | v1 |
| | | | |

---

## Kill list (things NOT to do, from the v3.1 prompt)

These sound good but hurt on a young domain:
- ❌ Daily publishing (dilutes indexing budget, no distribution capacity)
- ❌ Chasing head terms like "agentic AI" or "AI automation" in year one
- ❌ Word-count targets above 3200 for non-pillar posts (bloat kills dwell)
- ❌ Keyword density chasing (0.8–1.4% is fine as a floor, not a target)
- ❌ Fake "author bios" without real E-E-A-T backing — use Jai's actual credentials

---

## Open questions blocking Phase 0

Answer inline in your next message; I'll fill `positioning.md`:

1. Domain final: `.co` confirmed, or moving to `.com`?
2. India-first English positioning — comfortable, or need geo-neutral for UAE/US clients?
3. Existing published posts on the domain — count and URLs?
4. Weekly hours you can put in (be honest — 3? 10? 20?)
5. Are you writing, or is someone on your team of 5 doing this?
6. Any keywords you've already decided you want to rank for, regardless of my analysis?
