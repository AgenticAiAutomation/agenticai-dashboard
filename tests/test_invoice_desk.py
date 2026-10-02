"""Invoice Desk — end-to-end test (no network, temp SQLite, fake identity).

Proves the whole loop and the rules that protect it:
  link → client fills → review queue → Jai prices → issue (numbered, locked)
  → PDF → void → duplicate; plus: non-superuser locked out, link single-use,
  expired/revoked links refused, prices from a client link ignored, sample
  AI-101 arithmetic reproduced exactly, flag-off leaves no trace.

Run:  PYTHONPATH=api python tests/test_invoice_desk.py
"""
import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="inv-")
os.environ.update({"INVOICE_DESK_ENABLED": "1", "INVOICE_DESK_DB": os.path.join(TMP, "inv.db"),
                   "INVOICE_DESK_BACKUP_DIR": os.path.join(TMP, "bk"),
                   "INVOICE_DESK_USER_HOOK": "tests.test_invoice_desk:hook",
                   "INVOICE_DESK_SUPERUSERS": "jai.prajapati91@gmail.com"})

from fastapi import FastAPI                 # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402

USERS = {"jai": {"email": "jai.prajapati91@gmail.com", "name": "Jai", "role": "admin"},
         "lead": {"email": "assoc@agenticaiautomation.co", "name": "SEO Associate 1", "role": "seo_lead"}}


def hook(request):
    return USERS.get(request.headers.get("x-user"))


PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    print(("  PASS  " if cond else "  FAIL  ") + label)
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)


def main():
    from app.invoice_desk import money
    print("--- arithmetic: the AI-101 sample")
    s = money.compute({"items": [{"qty": 1, "rate": "4078.08"}, {"qty": 1, "rate": 12500},
                                 {"qty": 3, "rate": 400}, {"qty": 1, "rate": "2556.86"}],
                       "discount": "5278.94", "client": {"state_code": "24"}})
    check("taxable 15,056.00", s["taxable"] == "15056.00")
    check("out of state → IGST 18% = 2,710.08", s["tax_lines"] == [{"label": "IGST @ 18%", "amount": "2710.08"}])
    check("total rounds to 17,766", s["total"] == "17766" and s["round_off"] == "-0.08")
    h = money.compute({"items": [{"qty": 1, "rate": 1000}], "client": {"gstin": "06ABCDE1234F1Z5"}})
    check("same state (Haryana GSTIN) → CGST 9% + SGST 9%",
          [x["label"] for x in h["tax_lines"]] == ["CGST @ 9%", "SGST @ 9%"] and h["total"] == "1180")
    check("Indian number words", money.words(17766) == "Rupees Seventeen Thousand Seven Hundred Sixty Six Only")

    print("--- mounted on a dashboard-shaped app")
    import app.invoice_desk as pkg
    app = FastAPI()

    @app.get("/api/seo/backlinks")
    def existing():
        return {"ok": True}

    check("registers", pkg.register(app) is True)
    c = TestClient(app)
    J, L = {"x-user": "jai"}, {"x-user": "lead"}
    A = "/api/invoices"
    check("existing route untouched", c.get("/api/seo/backlinks").json() == {"ok": True})
    check("health ok", c.get(A + "/health").json()["db_ok"] is True)
    check("no session → 401", c.get(A + "/bootstrap").status_code == 401)
    check("associate → 403 (money is Jai-only)", c.get(A + "/bootstrap", headers=L).status_code == 403)
    check("Jai → 200", c.get(A + "/bootstrap", headers=J).status_code == 200)
    check("desk page served", "Invoice Desk" in c.get("/invoices/").text)

    print("--- fill link")
    check("associate cannot create links", c.post(A + "/links", headers=L, json={}).status_code == 403)
    lk = c.post(A + "/links", headers=J, json={"label": "Website project", "client_hint": "Shailesh Patel"}).json()["link"]
    tok = lk["token"]
    check("link URL is on the dashboard host", lk["url"].endswith("/invoices/f/" + tok))
    check("fill page served (noindex)", c.get("/invoices/f/" + tok).headers.get("x-robots-tag", "").startswith("noindex"))
    meta = c.get(A + "/public/" + tok).json()
    check("public meta exposes no money/settings", "bank" not in str(meta) and meta["client_hint"] == "Shailesh Patel")
    bad = c.post(A + "/public/" + tok, json={"client": {"name": "X"}, "items": []})
    check("needs an email or phone", bad.status_code == 400)
    page = c.get("/invoices/f/" + tok).text
    check("client form has no Services box", "Services" not in page and "svc" not in page)
    check("client form is light mode only", 'content="light only"' in page and "prefers-color-scheme" not in page)
    check("public meta lists no services or prices", "catalog" not in meta and "show_prices" not in meta)
    sub = c.post(A + "/public/" + tok, json={
        "client": {"name": "Shailesh Patel", "phone": "9999999999", "state_code": "24"},
        "items": [{"desc": "Website Design & Development", "qty": 1, "rate": 1}, {"desc": "Domain Name", "qty": 1}],
        "note": "PO 7781"})
    check("client submits (201)", sub.status_code == 201)
    again = c.post(A + "/public/" + tok, json={"client": {"name": "Y", "phone": "1"}, "items": [{"desc": "x"}]})
    check("single-use link refuses a second submission (410)", again.status_code == 410)
    check("honeypot swallowed silently", c.post(A + "/public/nope", json={"website": "spam"}).status_code == 200)
    check("unknown token → 410", c.post(A + "/public/nope", json={"client": {"name": "a", "phone": "1"},
                                                                  "items": [{"desc": "x"}]}).status_code == 410)

    print("--- review queue")
    q = c.get(A + "/list?view=queue", headers=J).json()["invoices"]
    check("submission is in the queue", len(q) == 1 and q[0]["status"] == "submitted")
    iid = q[0]["id"]
    inv = c.get(A + "/inv/" + iid, headers=J).json()["invoice"]
    check("services sent on a client link are ignored (desk adds them)", inv["data"]["items"] == [])
    check("client note kept", inv["data"]["client_note"] == "PO 7781")
    check("zero total cannot be issued", c.post(A + "/inv/" + iid + "/issue", headers=J).status_code == 400)
    edit = {"items": [{"desc": "Shared server Hosting", "qty": 1, "rate": "4078.08"},
                      {"desc": "Website Design & Development", "qty": 1, "rate": "12500"},
                      {"desc": "GMB profile management", "qty": 3, "rate": "400"},
                      {"desc": "Domain Name", "qty": 1, "rate": "2556.86"}],
            "discount": "5278.94", "invoice_date": "2026-10-01"}
    sv = c.put(A + "/inv/" + iid, headers=J, json=edit)
    check("Jai sets prices (saved as draft)", sv.status_code == 200 and sv.json()["invoice"]["status"] == "draft")
    check("server recomputed the total", sv.json()["invoice"]["totals"]["total"] == "17766")
    check("draft PDF renders", c.get(A + "/inv/" + iid + "/pdf", headers=J).content[:4] == b"%PDF")

    print("--- issue, lock, void, duplicate")
    check("no issue while bank + address are blank (the AI-102 sample gap)",
          c.post(A + "/inv/" + iid + "/issue", headers=J, json={}).status_code == 400)
    c.put(A + "/settings", headers=J, json={"seller": {"address": "Gurugram, Haryana"}})
    check("address alone is not enough — still needs bank or UPI",
          c.post(A + "/inv/" + iid + "/issue", headers=J, json={}).status_code == 400)
    c.put(A + "/settings", headers=J, json={"bank": {"account_no": "1234567890", "ifsc": "HDFC0000001"}})
    iss = c.post(A + "/inv/" + iid + "/issue", headers=J, json={})
    num = iss.json()["invoice"]["number"]
    check("issued as AI-102 (continues after AI-101)", iss.status_code == 200 and num == "AI-102")
    check("backup taken before issue", any(f.endswith("pre-issue.db") for f in os.listdir(os.path.join(TMP, "bk"))))
    check("issued invoice is locked", c.put(A + "/inv/" + iid, headers=J, json=edit).status_code == 409)
    check("issued invoice cannot be deleted", c.delete(A + "/inv/" + iid, headers=J).status_code == 409)
    check("cannot issue twice", c.post(A + "/inv/" + iid + "/issue", headers=J).status_code == 409)
    pdf = c.get(A + "/inv/" + iid + "/pdf", headers=J)
    check("issued PDF downloads", pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
          and "AI-102" in pdf.headers["content-disposition"])
    # settings change must not rewrite an issued invoice
    c.put(A + "/settings", headers=J, json={"bank": {"account_no": "CHANGED"}})
    snap = c.get(A + "/inv/" + iid, headers=J).json()["invoice"]["snapshot"]
    check("issued invoice keeps the bank details it was issued with", snap["bank"]["account_no"] == "1234567890")
    check("void needs a reason", c.post(A + "/inv/" + iid + "/void", headers=J, json={}).status_code == 400)
    v = c.post(A + "/inv/" + iid + "/void", headers=J, json={"reason": "wrong GSTIN"})
    check("void works", v.json()["invoice"]["status"] == "void")
    dup = c.post(A + "/inv/" + iid + "/duplicate", headers=J).json()["invoice"]
    check("duplicate is a fresh unnumbered draft", dup["status"] == "draft" and dup["number"] is None)
    d2 = c.post(A + "/inv/" + dup["id"] + "/issue", headers=J, json={}).json()["invoice"]
    check("next issue is AI-103 — no gaps, no reuse", d2["number"] == "AI-103")

    print("--- v1.1: nature of business, price list, loud stamp")
    cat = c.get(A + "/settings", headers=J).json()["catalog"]
    cat[0]["price"] = "12500"
    check("price list saved", c.put(A + "/settings", headers=J, json={"catalog": cat}).status_code == 200)
    check("bad price refused", c.put(A + "/settings", headers=J,
                                     json={"catalog": [{"desc": "x", "price": "-1"}]}).status_code == 400)
    lk3 = c.post(A + "/links", headers=J, json={"label": "biz"}).json()["link"]
    c.post(A + "/public/" + lk3["token"], json={"client": {"name": "Biz Co", "phone": "1", "business": "Dental clinic"},
                                                "items": [{"desc": cat[0]["desc"], "qty": 1}]})
    bz = [i for i in c.get(A + "/list?view=queue", headers=J).json()["invoices"] if i["client"] == "Biz Co"][0]
    bzi = c.get(A + "/inv/" + bz["id"], headers=J).json()["invoice"]
    check("nature of business captured", bzi["data"]["client"]["business"] == "Dental clinic")
    raw = c.get(A + "/inv/" + bz["id"] + "/pdf", headers=J).content
    try:                                    # test-only helper; the server doesn't need it
        import io, pypdf
        txt = "".join(pg.extract_text() for pg in pypdf.PdfReader(io.BytesIO(raw)).pages).encode()
    except ImportError:
        import subprocess
        txt = subprocess.run(["pdftotext", "-", "-"], input=raw, capture_output=True).stdout
    check("PDF carries the loud system-generated stamp", b"THIS IS A SYSTEM GENERATED INVOICE" in txt)
    check("PDF prints nature of business", b"Dental clinic" in txt)

    print("--- links lifecycle + settings validation")
    lk2 = c.post(A + "/links", headers=J, json={"label": "team", "show_prices": True, "max_uses": 2}).json()["link"]
    c.post(A + "/public/" + lk2["token"], json={"client": {"name": "Team entry", "email": "a@b.co"},
                                                "items": [{"desc": "SEO services", "qty": 1, "rate": "5000"}]})
    team = [i for i in c.get(A + "/list?view=queue", headers=J).json()["invoices"] if i["client"] == "Team entry"][0]
    check("even an old price-enabled request adds no services", team["total"] == "0")
    check("revoke", c.delete(A + "/links/" + lk2["token"], headers=J).status_code == 200)
    check("revoked link refused", c.get(A + "/public/" + lk2["token"]).status_code == 410)
    check("bad seller GSTIN refused", c.put(A + "/settings", headers=J,
                                            json={"seller": {"gstin": "123"}}).status_code == 400)
    check("audit trail recorded the issue",
          any(e["action"] == "invoice.issue" for e in c.get(A + "/audit", headers=J).json()["events"]))

    print("--- flag off")
    os.environ["INVOICE_DESK_ENABLED"] = "0"
    for m in [m for m in list(sys.modules) if m.startswith("app.invoice_desk")]:
        del sys.modules[m]
    pkg2 = importlib.import_module("app.invoice_desk")
    app2 = FastAPI()
    check("disabled → not mounted", pkg2.register(app2) is False)
    check("disabled → route absent", TestClient(app2).get(A + "/health").status_code == 404)

    print(f"\n{PASS} passed, {FAIL} failed. Temp dir: {TMP}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
