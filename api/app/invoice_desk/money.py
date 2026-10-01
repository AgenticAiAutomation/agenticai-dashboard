"""Invoice Desk — the arithmetic. Pure functions, Decimal only, no I/O.

One implementation, used by the API (authoritative on save and issue), the
live totals in the review screen (via POST /totals) and the PDF. A number on
the PDF can therefore never disagree with the number in the database.

Tax rule (place of supply, services, B2B/B2C in India):
  client state code == seller state code  → CGST rate/2 + SGST rate/2
  anything else in India                  → IGST rate
  mode can be forced: "igst" | "cgst_sgst" | "none" (e.g. export under LUT —
  Jai's call, never automatic).
"""
from decimal import Decimal, ROUND_HALF_UP

TWO = Decimal("0.01")

# GST state codes (first two digits of a GSTIN).
STATES = [
    ("01", "Jammu & Kashmir"), ("02", "Himachal Pradesh"), ("03", "Punjab"),
    ("04", "Chandigarh"), ("05", "Uttarakhand"), ("06", "Haryana"), ("07", "Delhi"),
    ("08", "Rajasthan"), ("09", "Uttar Pradesh"), ("10", "Bihar"), ("11", "Sikkim"),
    ("12", "Arunachal Pradesh"), ("13", "Nagaland"), ("14", "Manipur"), ("15", "Mizoram"),
    ("16", "Tripura"), ("17", "Meghalaya"), ("18", "Assam"), ("19", "West Bengal"),
    ("20", "Jharkhand"), ("21", "Odisha"), ("22", "Chhattisgarh"), ("23", "Madhya Pradesh"),
    ("24", "Gujarat"), ("26", "Dadra & Nagar Haveli and Daman & Diu"), ("27", "Maharashtra"),
    ("29", "Karnataka"), ("30", "Goa"), ("31", "Lakshadweep"), ("32", "Kerala"),
    ("33", "Tamil Nadu"), ("34", "Puducherry"), ("35", "Andaman & Nicobar Islands"),
    ("36", "Telangana"), ("37", "Andhra Pradesh"), ("38", "Ladakh"),
    ("97", "Other Territory"), ("96", "Outside India"),
]
STATE_NAME = dict(STATES)

# Services the agency bills. SAC is pre-filled only where it is unambiguous
# (998314 IT design & development, 998315 hosting); confirm the rest with the
# CA and set them per line — the field is editable on every invoice.
CATALOG = [
    {"desc": "Website Design & Development", "sac": "998314", "price": "0"},
    {"desc": "Shared server Hosting", "sac": "998315", "price": "0"},
    {"desc": "Domain Name", "sac": "", "price": "0"},
    {"desc": "GMB profile management", "sac": "", "price": "0"},
    {"desc": "SEO services", "sac": "", "price": "0"},
    {"desc": "WhatsApp automation", "sac": "998314", "price": "0"},
    {"desc": "RPA / process automation", "sac": "998314", "price": "0"},
    {"desc": "Custom AI agent", "sac": "998314", "price": "0"},
    {"desc": "Lead generation", "sac": "", "price": "0"},
    {"desc": "Annual maintenance (AMC)", "sac": "", "price": "0"},
]


def D(v, default="0"):
    try:
        if v in (None, ""):
            return Decimal(default)
        return Decimal(str(v).replace(",", "").strip())
    except Exception:
        return Decimal(default)


def q2(x):
    return x.quantize(TWO, rounding=ROUND_HALF_UP)


def gstin_ok(g):
    g = (g or "").strip().upper()
    if not g:
        return True                       # optional (B2C)
    return len(g) == 15 and g[:2].isdigit() and g.isalnum()


def state_from_gstin(g):
    g = (g or "").strip()
    return g[:2] if len(g) >= 2 and g[:2].isdigit() else ""


def compute(inv, seller_state="06"):
    """inv: {'items':[{qty,rate}], 'discount', 'discount_type', 'tax_mode',
    'tax_rate', 'client':{'state_code','gstin'}} → totals dict (strings)."""
    items_out, items_total = [], Decimal("0")
    for it in inv.get("items") or []:
        qty, rate = D(it.get("qty"), "1"), D(it.get("rate"))
        amt = q2(qty * rate)
        items_total += amt
        items_out.append({**it, "qty": _n(qty), "rate": str(q2(rate)), "amount": str(amt)})

    dval = D(inv.get("discount"))
    if inv.get("discount_type") == "percent":
        discount = q2(items_total * min(max(dval, Decimal(0)), Decimal(100)) / 100)
    else:
        discount = q2(min(max(dval, Decimal(0)), items_total))
    taxable = items_total - discount

    rate = D(inv.get("tax_rate"), "18")
    client = inv.get("client") or {}
    code = client.get("state_code") or state_from_gstin(client.get("gstin"))
    mode = inv.get("tax_mode") or "auto"
    if mode == "auto":
        mode = "cgst_sgst" if code and code == seller_state else "igst"

    lines = []
    if mode == "cgst_sgst":
        half = rate / 2
        c = q2(taxable * half / 100)
        lines = [{"label": f"CGST @ {_n(half)}%", "amount": str(c)},
                 {"label": f"SGST @ {_n(half)}%", "amount": str(c)}]
    elif mode == "igst":
        lines = [{"label": f"IGST @ {_n(rate)}%", "amount": str(q2(taxable * rate / 100))}]
    tax = sum((D(x["amount"]) for x in lines), Decimal("0"))

    exact = taxable + tax
    grand = exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return {"items": items_out, "items_total": str(items_total), "discount": str(discount),
            "taxable": str(taxable), "tax_mode": mode, "tax_lines": lines, "tax": str(q2(tax)),
            "round_off": str(q2(grand - exact)), "total": str(grand),
            "total_words": words(int(grand)), "place_of_supply": STATE_NAME.get(code, "")}


def _n(x):
    """Decimal → shortest clean string ('3', '2.5', '9')."""
    s = format(x.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def inr(v):
    """Indian digit grouping: 1234567.5 → '12,34,567.50'."""
    x = q2(D(v))
    neg, x = x < 0, abs(x)
    whole, frac = str(x).split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + whole + "." + frac


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n):
    return _ONES[n] if n < 20 else (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))


def _three(n):
    h, r = divmod(n, 100)
    return ((_ONES[h] + " Hundred" + (" " if r else "")) if h else "") + (_two(r) if r else "")


def words(n):
    """Indian system, rupees only: 17766 → 'Rupees Seventeen Thousand Seven Hundred Sixty Six Only'."""
    if n == 0:
        return "Rupees Zero Only"
    out = []
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (10**3, "Thousand")):
        k, n = divmod(n, size)
        if k:
            out.append((words(k)[7:-5] if k >= 100 and name == "Crore" else _two(k) if k < 100 else _three(k)) + " " + name)
    if n:
        out.append(_three(n))
    return "Rupees " + " ".join(out) + " Only"
