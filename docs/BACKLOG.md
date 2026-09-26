# Backlog

Work that is known, decided against for now, or blocked on something outside
the code. Anything here is deliberate — if it is not in this file and not
built, it was forgotten rather than deferred.

Format: one heading per item, with **why it is not done** and **what unblocks
it**, so the next person does not re-derive the decision.

---

## wa-funnel: nobody is paged when a lead arrives

**Status:** deferred 2026-09-25, agreed with Jai.

`WA_FUNNEL_NOTIFY=none` in `wa-funnel.service`. Leads are stored in the leads
table and the one-line summary is written to the journal on every submission,
so nothing is lost and a lead is recoverable with:

```bash
journalctl -u wa-funnel | grep LEAD
```

But no email is sent and no webhook fires, so a lead can sit unseen until
someone opens the desk.

**What unblocks it:** either
- SMTP credentials → set `WA_FUNNEL_NOTIFY=email` plus `WA_FUNNEL_SMTP_HOST`,
  `WA_FUNNEL_SMTP_USER`, `WA_FUNNEL_SMTP_PASS`, `WA_FUNNEL_MAIL_FROM`,
  `WA_FUNNEL_MAIL_TO`; or
- the existing WhatsApp bot platform's endpoint → set
  `WA_FUNNEL_NOTIFY=webhook` and `WA_FUNNEL_WEBHOOK_URL` (plus
  `WA_FUNNEL_WEBHOOK_TOKEN` if it wants a bearer).

Both are env-only: edit the unit, `daemon-reload`, `restart`. No code change,
no redeploy. The code for both paths is written and in `notify.py`.

**Why it matters more than it looks:** the funnel promises every
non-qualifying lead a reply "within 2 business days". Until something pages
the team, that promise depends on someone remembering to open the desk.

---

## Who owns the "within 2 business days" promise

**Status:** open, needs a person not a commit.

Every lead below the qualifying threshold sees that sentence. It is the most
load-bearing line in the funnel and code cannot keep it.

**What unblocks it:** a named owner and a habit — most simply, the leads desk
filtered to `status=open`, checked daily. Once notifications are on (above),
that becomes a push rather than a pull.

---

## wa-funnel has no GitHub remote

**Status:** open.

The VPS clone's `origin` is the git bundle it was installed from, so
`ops/deploy.sh` cannot pull. Deploys currently mean staging a fresh bundle.

**What unblocks it:** create the repo under the AgenticAiAutomation org, push
`main` and the `v1.0.0` tag, then on the server:

```bash
git -C /var/www/wa-funnel remote set-url origin <github-url>
```

After that `ops/deploy.sh` works as documented.

---

## Leads backup is on the same disk as the leads

**Status:** flagged, unverified.

`ops/backup.sh` writes to `/var/backups/wa-funnel`, which is on the same
volume as `instance/leads.db`. That is a convenience copy, not a backup: it
survives a bad deploy, not a disk.

**What unblocks it:** confirm whether the VPS already has an off-box schedule
that picks up `/var/backups`. If it does, nothing to do. If it does not, this
needs an off-box destination before the leads table carries real value.

---

## content-brain is exposed to the public internet

**Status:** found 2026-09-25 while assigning a port for wa-funnel. Not ours to
fix without Jai's say-so, recorded so it is not lost.

`content-brain.service` binds `0.0.0.0:5005` and
`http://187.127.173.209:5005/` answers 200 from outside the box — verified.
That path bypasses nginx: no TLS, none of the `site-hardening.conf` rules.
`ufw status` is inactive, which is what leaves it reachable; every other
service is unreachable from outside only by luck of binding to localhost.

**What unblocks it:** either put it behind an nginx server block and rebind to
`127.0.0.1`, or enable ufw and allow only 22/80/443. See
`docs/VPS_SERVICES.md`.

---

## Stale ports and providers in the older deploy docs

**Status:** mitigated, not fixed.

`DEPLOY.md`, `DEPLOY-YOUR-VPS.md` and `DEPLOYMENT-CHECKLIST.md` still name the
dashboard API as port 5003 (it is 5004) and Cloudflare as the DNS provider (it
is Hostinger). Each now carries a banner pointing at `docs/VPS_SERVICES.md`,
which is correct and verified.

**What unblocks it:** a pass through those three files, or a decision to
delete them in favour of the registry.

---

## wa-leads: read access is owner-only

**Status:** decided 2026-09-25, revisit if the team grows into it.

The leads desk is owner-only for reading as well as writing. If the SEO lead
should be able to watch the pipeline without changing it, that is one env line
plus one nav check — both named in `docs/WA_LEADS.md`. Written down because
the restriction is a decision, not an oversight.
