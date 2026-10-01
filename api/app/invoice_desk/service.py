"""Invoice Desk — every rule, no web framework.

Each function takes the resolved user (or None) and plain arguments and
returns (status, payload). routes.py only translates. Rules:

  * Money is superuser-only. The public fill form can only ADD a submission
    to the review queue through a valid, unexpired, unused link — it can
    never read, edit or list anything.
  * Prices typed on a public form are a suggestion: they arrive as a
    submission and nothing is issued until Jai approves it.
  * Issued invoices are immutable. A mistake is fixed by Void + Duplicate,
    never by editing — the number sequence stays honest for GST.
  * Totals are always recomputed on the server (money.compute); a number sent
    by a browser is never stored as-is.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import money, store
from .config import settings

ERR_AUTH = (401, {"error": "not_authenticated", "message": "Sign in to the dashboard first."})
ERR_FORBID = (403, {"error": "forbidden", "message": "Only Jai can open the invoice desk."})
ERR_FROZEN = (503, {"error": "read_only",
                    "message": "The invoice desk is read-only during maintenance. Try again shortly."})
NOT_FOUND = (404, {"error": "not_found", "message": "That invoice no longer exists."})

LIMITS = {"name": 120, "company": 160, "business": 200, "address": 400, "city": 80, "pincode": 12, "gstin": 15,
          "email": 160, "phone": 30, "state_code": 2}


def is_superuser(user):
    return bool(user) and (str(user.get("email") or "").lower() in settings.SUPERUSERS)


def _guard(user, write=False):
    if not user:
        return ERR_AUTH
    if not is_superuser(user):
        return ERR_FORBID
    if write and settings.READ_ONLY:
        return ERR_FROZEN
    return None


def _bad(msg):
    return 400, {"error": "invalid", "message": msg}


def _actor(user):
    return (user or {}).get("email") or (user or {}).get("name") or "public"


# --------------------------------------------------------------- cleaning
def _clean_client(raw):
    raw = raw if isinstance(raw, dict) else {}
    c = {k: str(raw.get(k) or "").strip()[:n] for k, n in LIMITS.items()}
    c["gstin"] = c["gstin"].upper()
    if c["gstin"] and not c["state_code"]:
        c["state_code"] = money.state_from_gstin(c["gstin"])
    if c["state_code"] and c["state_code"] not in money.STATE_NAME:
        c["state_code"] = ""
    return c


def _clean_items(raw, allow_price=True):
    items = []
    for it in (raw if isinstance(raw, list) else [])[:40]:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("desc") or "").strip()[:200]
        if not desc:
            continue
        qty = money.D(it.get("qty"), "1")
        rate = money.D(it.get("rate")) if allow_price else money.D(0)
        if qty <= 0 or qty > 100000 or rate < 0 or rate > 100000000:
            continue
        items.append({"desc": desc, "sac": str(it.get("sac") or "").strip()[:8],
                      "qty": money._n(qty), "rate": str(money.q2(rate))})
    return items


def _clean_data(body, base=None):
    """Merge an edit onto the stored data; only known fields survive."""
    d = dict(base or {})
    if "client" in body:
        d["client"] = _clean_client(body["client"])
    if "items" in body:
        d["items"] = _clean_items(body["items"])
    if "discount" in body:
        d["discount"] = str(money.q2(max(money.D(body.get("discount")), money.D(0))))
    if "discount_type" in body:
        d["discount_type"] = "percent" if body["discount_type"] == "percent" else "flat"
    for k, n in (("discount_label", 60), ("payment_terms", 120), ("notes", 1500),
                 ("tax_note", 200), ("client_note", 1500)):
        if k in body:
            d[k] = str(body.get(k) or "").strip()[:n]
    if "tax_mode" in body:
        d["tax_mode"] = body["tax_mode"] if body["tax_mode"] in ("auto", "igst", "cgst_sgst", "none") else "auto"
    if "tax_rate" in body:
        r = money.D(body.get("tax_rate"), "18")
        d["tax_rate"] = money._n(r) if 0 <= r <= 40 else "18"
    for k in ("invoice_date", "due_date"):
        if k in body:
            v = str(body.get(k) or "").strip()[:10]
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                v = "" if k == "due_date" else store.today_ist()
            d[k] = v
    d.setdefault("client", _clean_client({}))
    d.setdefault("items", [])
    d.setdefault("invoice_date", store.today_ist())
    return d


def _totals(d):
    return money.compute(d, store.get_settings()["seller"].get("state_code", "06"))


def _summary(inv):
    c = (inv["data"] or {}).get("client") or {}
    return {"id": inv["id"], "number": inv["number"], "status": inv["status"],
            "source": inv["source"], "client": c.get("company") or c.get("name") or "—",
            "contact": c.get("name"), "total": inv["totals"]["total"],
            "date": inv["data"].get("invoice_date"), "created_at": inv["created_at"],
            "updated_at": inv["updated_at"], "issued_at": inv["issued_at"],
            "priced": any(money.D(i.get("rate")) > 0 for i in inv["data"].get("items") or [])}


# --------------------------------------------------------------- desk
def health():
    ok = store.integrity_ok()
    from . import pdf
    return (200 if ok else 503), {"feature": "invoice-desk", "version": settings.VERSION,
                                  "db_ok": ok, "pdf": pdf.available(), "read_only": settings.READ_ONLY}


def bootstrap(user):
    g = _guard(user)
    if g:
        return g
    from . import pdf
    return 200, {"me": user, "settings": store.get_settings(), "counts": store.counts(),
                 "states": money.STATES, "catalog": store.get_settings()["catalog"], "today": store.today_ist(),
                 "readOnly": settings.READ_ONLY, "pdf": pdf.available(),
                 "version": settings.VERSION, "publicBase": settings.PUBLIC_BASE + settings.URL_PREFIX}


VIEWS = {"queue": ("submitted", "draft"), "issued": ("issued",), "void": ("void",),
         "all": ("submitted", "draft", "issued", "void")}


def list_invoices(user, view="queue"):
    g = _guard(user)
    if g:
        return g
    rows = store.list_invoices(VIEWS.get(view, VIEWS["queue"]))
    return 200, {"view": view, "invoices": [_summary(r) for r in rows], "counts": store.counts()}


def get_invoice(user, inv_id):
    g = _guard(user)
    if g:
        return g
    inv = store.get_invoice(inv_id)
    return (200, {"invoice": inv}) if inv else NOT_FOUND


def create(user, body):
    g = _guard(user, write=True)
    if g:
        return g
    s = store.get_settings()["defaults"]
    seed = {"payment_terms": s.get("payment_terms", ""), "tax_rate": s.get("tax_rate", "18"),
            "notes": s.get("notes", ""), "tax_mode": "auto", "discount_type": "flat"}
    d = _clean_data(body or {}, seed)
    inv = {"id": "inv_" + uuid.uuid4().hex[:12], "status": "draft", "source": "desk",
           "link_token": None, "data": d, "totals": _totals(d),
           "created_at": store.now_iso(), "updated_at": store.now_iso()}
    store.add_invoice(inv)
    store.audit(_actor(user), "invoice.create", inv["id"])
    return 201, {"invoice": store.get_invoice(inv["id"])}


def save(user, inv_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    inv = store.get_invoice(inv_id)
    if not inv:
        return NOT_FOUND
    if inv["status"] not in ("submitted", "draft"):
        return 409, {"error": "locked", "message": "Issued invoices can't be edited. Void it and duplicate."}
    d = _clean_data(body or {}, inv["data"])
    store.update_invoice(inv_id, d, _totals(d), status="draft")
    store.audit(_actor(user), "invoice.save", inv_id, {"total": _totals(d)["total"]})
    return 200, {"invoice": store.get_invoice(inv_id)}


def totals(user, body):
    """Live preview for the editor — same maths as save/issue/PDF."""
    g = _guard(user)
    if g:
        return g
    return 200, _totals(_clean_data(body or {}, {"tax_rate": "18"}))


def issue(user, inv_id, body=None):
    g = _guard(user, write=True)
    if g:
        return g
    inv = store.get_invoice(inv_id)
    if not inv:
        return NOT_FOUND
    if inv["status"] not in ("submitted", "draft"):
        return 409, {"error": "locked", "message": "This invoice is already issued."}
    d = _clean_data(body or {}, inv["data"])
    t = _totals(d)
    c = d.get("client") or {}
    if not (c.get("name") or c.get("company")):
        return _bad("Add who the invoice is for (Bill To) before issuing.")
    if not d["items"]:
        return _bad("Add at least one service line.")
    if money.D(t["total"]) <= 0:
        return _bad("The total is zero — set the prices before issuing.")
    if c.get("gstin") and not money.gstin_ok(c["gstin"]):
        return _bad("The client GSTIN should be 15 letters/numbers — fix it or leave it blank.")
    cfg = store.get_settings()
    # Issued is locked forever, so the details it freezes must be complete.
    # GST Rule 46 needs the supplier's address; without bank or UPI the
    # client has nothing to pay into.
    if not cfg["seller"].get("address"):
        return _bad("Add your business address in Settings before issuing — a GST invoice must show it.")
    if not (cfg["bank"].get("account_no") and cfg["bank"].get("ifsc")) and not cfg["bank"].get("upi"):
        return _bad("Add bank details (account no + IFSC) or a UPI ID in Settings before issuing.")
    try:
        store.backup("pre-issue")          # issued invoices are legal records
    except Exception:
        pass                                # never block billing on a backup hiccup
    number = store.issue_invoice(inv_id, d, t, {"seller": cfg["seller"], "bank": cfg["bank"]},
                                 _actor(user))
    if not number:
        return 409, {"error": "locked", "message": "This invoice was issued a moment ago."}
    store.audit(_actor(user), "invoice.issue", inv_id, {"number": number, "total": t["total"]})
    return 200, {"invoice": store.get_invoice(inv_id)}


def void(user, inv_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    reason = str((body or {}).get("reason") or "").strip()[:200]
    if not reason:
        return _bad("Say why it's void — it prints on the invoice and stays in the book.")
    if not store.void_invoice(inv_id, reason):
        return 409, {"error": "not_issued", "message": "Only issued invoices can be voided."}
    store.audit(_actor(user), "invoice.void", inv_id, {"reason": reason})
    return 200, {"invoice": store.get_invoice(inv_id)}


def duplicate(user, inv_id):
    g = _guard(user, write=True)
    if g:
        return g
    inv = store.get_invoice(inv_id)
    if not inv:
        return NOT_FOUND
    d = dict(inv["data"])
    d["invoice_date"] = store.today_ist()
    d.pop("due_date", None)
    new = {"id": "inv_" + uuid.uuid4().hex[:12], "status": "draft", "source": "desk",
           "link_token": None, "data": d, "totals": _totals(d),
           "created_at": store.now_iso(), "updated_at": store.now_iso()}
    store.add_invoice(new)
    store.audit(_actor(user), "invoice.duplicate", new["id"], {"from": inv_id})
    return 201, {"invoice": store.get_invoice(new["id"])}


def delete(user, inv_id):
    g = _guard(user, write=True)
    if g:
        return g
    if not store.delete_invoice(inv_id):
        return 409, {"error": "locked", "message": "Issued invoices can't be deleted — void them instead."}
    store.audit(_actor(user), "invoice.delete", inv_id)
    return 200, {"ok": True}


def pdf_bytes(user, inv_id):
    """Returns (status, bytes|payload, filename)."""
    g = _guard(user)
    if g:
        return g[0], g[1], None
    from . import pdf
    if not pdf.available():
        return 503, {"error": "pdf_unavailable",
                     "message": "PDF engine not installed on the server (pip install reportlab). "
                                "Ask Jai to redeploy."}, None
    inv = store.get_invoice(inv_id)
    if not inv:
        return NOT_FOUND[0], NOT_FOUND[1], None
    issued = inv["status"] in ("issued", "void")
    snap = inv["snapshot"] if issued and inv["snapshot"] else store.get_settings()
    body = pdf.render(inv, snap, draft=not issued)
    c = inv["data"].get("client") or {}
    who = "".join(ch for ch in (c.get("name") or c.get("company") or "client") if ch.isalnum() or ch in " .-_")
    fname = f"{inv['number'] or 'DRAFT'} - {who.strip()} - Invoice.pdf"
    return 200, body, fname


# --------------------------------------------------------------- settings
def get_settings(user):
    g = _guard(user)
    return g or (200, store.get_settings())


def put_settings(user, body):
    g = _guard(user, write=True)
    if g:
        return g
    body = body or {}
    cfg = store.get_settings()
    for section, fields in (("seller", ("name", "tagline", "gstin", "state_code", "email", "phone", "address")),
                            ("bank", ("account_name", "account_no", "ifsc", "bank_name", "upi")),
                            ("defaults", ("payment_terms", "tax_rate", "notes"))):
        src = body.get(section)
        if isinstance(src, dict):
            for f in fields:
                if f in src:
                    cfg[section][f] = str(src.get(f) or "").strip()[:400]
    if cfg["seller"].get("gstin") and not money.gstin_ok(cfg["seller"]["gstin"]):
        return _bad("Your GSTIN should be 15 letters/numbers.")
    cfg["seller"]["gstin"] = cfg["seller"].get("gstin", "").upper()
    if cfg["seller"].get("gstin") and not cfg["seller"].get("state_code"):
        cfg["seller"]["state_code"] = cfg["seller"]["gstin"][:2]
    cat = body.get("catalog")
    if isinstance(cat, list):
        clean = []
        for c in cat[:60]:
            if not isinstance(c, dict) or not str(c.get("desc") or "").strip():
                continue
            price = money.D(c.get("price"))
            if price < 0:
                return _bad("Prices can't be negative.")
            clean.append({"desc": str(c["desc"]).strip()[:200], "sac": str(c.get("sac") or "").strip()[:8],
                          "price": str(money.q2(price))})
        if not clean:
            return _bad("Keep at least one item in the price list.")
        cfg["catalog"] = clean
    num = body.get("numbering")
    if isinstance(num, dict):
        prefix = str(num.get("prefix", cfg["numbering"]["prefix"])).strip()[:12]
        try:
            nxt = int(num.get("next", cfg["numbering"]["next"]))
        except (TypeError, ValueError):
            return _bad("Next invoice number must be a whole number.")
        if nxt < 1:
            return _bad("Next invoice number must be 1 or more.")
        cfg["numbering"] = {"prefix": prefix, "next": nxt}
    store.put_settings(cfg, _actor(user))
    store.audit(_actor(user), "settings.update", None,
                {"numbering": cfg["numbering"], "bank_set": bool(cfg["bank"].get("account_no"))})
    return 200, cfg


# --------------------------------------------------------------- links
def _link_out(l):
    ok, why = store.link_usable(l)
    return {**l, "url": f"{settings.PUBLIC_BASE}{settings.URL_PREFIX}/f/{l['token']}",
            "show_prices": bool(l["show_prices"]), "revoked": bool(l["revoked"]),
            "live": ok, "state": why or "Live"}


def list_links(user):
    g = _guard(user)
    if g:
        return g
    return 200, {"links": [_link_out(l) for l in store.list_links()]}


def create_link(user, body):
    g = _guard(user, write=True)
    if g:
        return g
    body = body or {}
    try:
        days = min(max(int(body.get("days") or settings.LINK_DAYS), 1), 90)
        uses = min(max(int(body.get("max_uses") or 1), 1), 50)
    except (TypeError, ValueError):
        return _bad("Days and uses must be whole numbers.")
    exp = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
    rec = {"token": store.new_token(), "label": str(body.get("label") or "").strip()[:80],
           "client_hint": str(body.get("client_hint") or "").strip()[:120],
           "show_prices": 1 if body.get("show_prices") else 0, "max_uses": uses,
           "expires_at": exp, "created_by": _actor(user), "created_at": store.now_iso()}
    store.add_link(rec)
    store.audit(_actor(user), "link.create", rec["token"][:8],
                {"label": rec["label"], "uses": uses, "days": days, "prices": bool(rec["show_prices"])})
    return 201, {"link": _link_out(store.get_link(rec["token"]))}


def revoke_link(user, token):
    g = _guard(user, write=True)
    if g:
        return g
    if not store.revoke_link(token):
        return NOT_FOUND
    store.audit(_actor(user), "link.revoke", token[:8])
    return 200, {"ok": True}


def audit_trail(user, limit=200):
    g = _guard(user)
    return g or (200, {"events": store.recent_audit(min(max(int(limit or 200), 1), 1000))})


# --------------------------------------------------------------- public form
_hits = {}


def _rate_ok(ip):
    now = time.time()
    q = [t for t in _hits.get(ip, []) if now - t < 3600]
    if len(q) >= settings.PUBLIC_RATE:
        _hits[ip] = q
        return False
    q.append(now)
    _hits[ip] = q
    return True


def public_meta(token):
    link = store.get_link(token or "")
    ok, why = store.link_usable(link)
    if not ok:
        return 410, {"error": "link_closed", "message": why}
    seller = store.get_settings()["seller"]
    return 200, {"seller": seller.get("name"), "label": link["label"],
                 "client_hint": link["client_hint"], "show_prices": bool(link["show_prices"]),
                 "states": money.STATES, "catalog": [c["desc"] for c in store.get_settings()["catalog"]]}


def public_submit(token, body, ip=""):
    if settings.READ_ONLY:
        return ERR_FROZEN
    body = body or {}
    if body.get("website"):                     # honeypot — real people never fill it
        return 200, {"ok": True}
    if not _rate_ok(ip or "?"):
        return 429, {"error": "slow_down", "message": "Too many submissions. Please try again later."}
    link = store.get_link(token or "")
    ok, why = store.link_usable(link)
    if not ok:
        return 410, {"error": "link_closed", "message": why}
    client = _clean_client(body.get("client"))
    if not client["name"]:
        return _bad("Please enter your name.")
    if not (client["email"] or client["phone"]):
        return _bad("Please give an email or a phone number so we can reach you.")
    if client["email"] and ("@" not in client["email"] or "." not in client["email"].split("@")[-1]):
        return _bad("That email doesn't look right.")
    if client["gstin"] and not money.gstin_ok(client["gstin"]):
        return _bad("GSTIN should be 15 letters/numbers — or leave it blank.")
    items = _clean_items(body.get("items"), allow_price=bool(link["show_prices"]))
    cat = {c["desc"]: c for c in store.get_settings()["catalog"]}
    for it in items:                       # client never types SAC/price; fill from the price list
        known = cat.get(it["desc"]) or {}
        it["sac"] = it["sac"] or known.get("sac", "")
        if money.D(it["rate"]) == 0 and money.D(known.get("price")) > 0:
            it["rate"] = str(money.q2(money.D(known["price"])))
    if not items:
        return _bad("Pick at least one service.")
    defaults = store.get_settings()["defaults"]
    d = _clean_data({"client": client, "client_note": body.get("note") or ""},
                    {"items": items, "payment_terms": defaults.get("payment_terms", ""),
                     "tax_rate": defaults.get("tax_rate", "18"), "tax_mode": "auto",
                     "discount_type": "flat", "notes": defaults.get("notes", "")})
    inv = {"id": "inv_" + uuid.uuid4().hex[:12], "status": "submitted", "source": "link",
           "link_token": token, "data": d, "totals": _totals(d),
           "created_at": store.now_iso(), "updated_at": store.now_iso()}
    saved, why = store.submit_via_link(token, inv)
    if not saved:
        return 410, {"error": "link_closed", "message": why}
    store.audit("public:" + (ip or "?"), "invoice.submitted", inv["id"],
                {"link": token[:8], "label": link["label"], "lines": len(items)})
    return 201, {"ok": True, "message": "Thank you — your details are in. We'll send the invoice shortly."}
