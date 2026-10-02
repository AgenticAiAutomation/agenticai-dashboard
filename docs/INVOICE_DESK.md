# Invoice Desk

Client fills a link (billing details only) → submission lands in a review queue → Jai adds services + prices →
**Approve & issue** → numbered, locked PDF in the AI-101 layout.

- Desk (Jai only): `https://dashboard.agenticaiautomation.co/invoices/`
- Client form: `https://dashboard.agenticaiautomation.co/invoices/f/<token>` (no login)
- API: `/api/invoices/*` · Code: `api/app/invoice_desk/` · DB: `api/instance/invoice_desk.db`

## Daily use

1. **Fill links → Create link.** Label + client name. Copy or WhatsApp it.
   Default: 1 submission, 14 days.
2. Client fills name, business name, **nature of business**, GSTIN (optional), address, state, a note → **Review queue** shows *New from client*. The form has no services section and is always light mode.
3. Open it. Fix details. Pick items — price fills from your **Price list** (Settings). Add discount (₹ or %), GST. Totals update live.
4. **Preview PDF** (watermarked DRAFT) → **Approve & issue**. Number assigned, PDF opens.
5. Mistake on an issued invoice? **Void** (reason prints on it) → **Duplicate** → fix → issue.

## Rules built in

| Rule | Why |
|---|---|
| Superuser emails only (`INVOICE_DESK_SUPERUSERS`) | Money. Associates get 403. |
| Number given only at issue, one transaction, unique index | Sequential, no gaps, no duplicates (GST). |
| Issued = locked; no edit, no delete | Fix by Void + Duplicate. |
| Seller + bank details frozen into each issued invoice | Changing Settings never rewrites old invoices. |
| No issue without seller address + bank (or UPI) | Locked forever — a blank bank block can never be fixed. |
| Voided PDF carries a VOID watermark | A voided copy can't pass as a live invoice. |
| Totals always recomputed on the server | Browser numbers are never stored. |
| Client links carry billing details only; any services/prices sent are dropped | Client never picks services or sets a price — you add them on the desk. |
| GST auto: same state as seller (06 Haryana) → CGST 9 + SGST 9, else IGST 18 | Sample showed "IGST / CGST & SGST" on one line — now split correctly. Override per invoice. |
| Every PDF says **THIS IS A SYSTEM GENERATED INVOICE** (boxed, under the total) + footer line | As requested. |
| Online backup before every issue | Issued invoices are legal records. Keeps last 90. |
| Public form: token, expiry, use-count, honeypot, 10/hour/IP | Spam + abuse brake. |

## First-time setup (Settings tab)

- **Business address + bank details** — blank on the sample. **Approve & issue is refused until
  both are set** (address: GST Rule 46; bank: account no + IFSC, or a UPI ID). Drafts and
  previews work without them.
- **Price list** — set your standard price per item once; every invoice picks it up.
- **Next number** — set to **102** (AI-101 already issued). Change if you issued more by hand.
- **SAC codes** — pre-filled only for website dev / hosting (998314 / 998315). Confirm the rest with your CA.

## Deploy

**Scripted (first deploy):** `ops/deploy-invoice-desk.sh`, run as root on the VPS. It checks
the live tree is clean and fast-forwardable, shows the commits and asks first, adds the
settings as a systemd drop-in (`dashboard-api.service.d/invoice-desk.conf`) and the nginx
blocks as `snippets/invoice-desk.conf`, then health-gates and rolls itself back on failure.

**By hand**, the same steps:

1. `pip install -r api/requirements.txt` (adds `reportlab`).
2. Add the `INVOICE_DESK_*` lines from `infra/dashboard-api.service` to the live unit → `systemctl daemon-reload`.
3. Add `infra/nginx-invoice-desk.conf` blocks to `sites-available/dashboard-frontend` → `nginx -t && systemctl reload nginx`.
4. Restart `dashboard-api`. Check: `curl -s https://dashboard.agenticaiautomation.co/api/invoices/health`.

## Business continuity

| Breaks | Effect | Action |
|---|---|---|
| Module error | Dashboard normal, `/invoices` 404 | Read log, fix, redeploy |
| reportlab missing | Desk works, PDF button says so | `pip install reportlab`, restart |
| DB corrupt | `/health` 503 | Restore (L3) |
| Maintenance | `INVOICE_DESK_READ_ONLY=1` — view + download only | Flip back |

## Rollback

- **L1 (10s, no data loss):** `INVOICE_DESK_ENABLED=0` in the unit, restart. Feature gone; DB kept.
- **L2 (30s):** `ops/rollback.sh --to <previous sha>`.
- **L3:** stop service, `cp backups/invoice_desk/<file>.db instance/invoice_desk.db`, start.
- **Uninstall:** remove the 2 lines in `api/app/main.py` + nginx blocks. Nothing else touched.

## Tests

`PYTHONPATH=api python tests/test_invoice_desk.py` — 56 checks (sample maths 17,766, price list, business field, stamp,
roles, single-use links, issue needs address + bank, lock, numbering, void, snapshot, flag-off).

## Scaling later

- Email the PDF on issue (SMTP env + one call after `issue`).
- WhatsApp "your invoice is ready" via the Leadwa/agentic-platform sender.
- Payment status (Paid / Part-paid) + reminders — new columns, same table.
- Move to Postgres when another app needs to join invoices (same schema).
