"""Invoice Desk — the PDF, laid out after the AI-101 sample (Shailesh Patel).

Same look: logo top-left, seller block top-right in blue, a hairline, centred
TAX INVOICE, number/date, Bill To, the four-column table with a bold Discount
row, Subtotal / GST / Total, payment terms, bank details, blue footer line.

Added where the sample left a gap a GST tax invoice needs: client GSTIN and
place of supply, SAC per line (column shown only when used), the GST split
(CGST+SGST or IGST — never "IGST / CGST & SGST" on one line), round-off, and
the total in words. Built-in Times fonts only, so it renders identically on
any server with no font files; amounts are written "INR", not ₹, for the
same reason.
"""
import io
import os
from datetime import datetime

from .money import inr

LOGO = os.path.join(os.path.dirname(__file__), "static", "logo.jpg")
BLUE = (0.106, 0.227, 0.541)      # #1B3A8A — the sample's heading blue
GREY = (0.35, 0.35, 0.35)


def available():
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:
        return False


def _date(iso):
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d")
    except Exception:
        return iso or ""
    n = d.day
    suf = "th" if 11 <= n <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf} {d.strftime('%b %Y')}"


def render(inv, settings_snapshot, draft=False):
    """inv: invoice row (data, totals, number, status). Returns PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    data, tot = inv["data"], inv["totals"]
    seller, bank = settings_snapshot["seller"], settings_snapshot["bank"]
    client = data.get("client") or {}
    W, H = A4
    blue = colors.Color(*BLUE)

    base = ParagraphStyle("b", fontName="Times-Roman", fontSize=10.5, leading=13)
    bold = ParagraphStyle("bb", parent=base, fontName="Times-Bold")
    small = ParagraphStyle("s", parent=base, fontSize=9, leading=12)
    cell = ParagraphStyle("c", parent=base, fontSize=10, leading=12.5)
    cellb = ParagraphStyle("cb", parent=cell, fontName="Times-Bold")
    title = ParagraphStyle("t", parent=bold, fontSize=16, leading=20, alignment=TA_CENTER)

    def esc(s):
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def header_footer(c, doc):
        c.saveState()
        first = doc.page == 1      # the letterhead is first-page only; footer on all
        # logo
        if first and os.path.exists(LOGO):
            c.drawImage(LOGO, 72, H - 48 - 92, width=145, height=92, preserveAspectRatio=True)
        # seller block, right-aligned (first page only)
        if first:
            x, y = W - 72, H - 64
            c.setFillColor(blue); c.setFont("Times-Bold", 15)
            c.drawRightString(x, y, seller.get("name", ""))
            c.setFillColorRGB(*GREY); c.setFont("Times-Roman", 7.6)
            for line in (seller.get("tagline") or "").splitlines():
                y -= 11; c.drawRightString(x, y, line.upper())
            c.setFillColorRGB(0, 0, 0)
            if seller.get("gstin"):
                y -= 13; c.setFont("Times-Bold", 9.5); c.drawRightString(x, y, f"GSTIN: {seller['gstin']}")
            c.setFont("Times-Roman", 9.5)
            if seller.get("email"):
                y -= 13; c.drawRightString(x, y, f"Email: {seller['email']}")
            if seller.get("phone"):
                y -= 12; c.drawRightString(x, y, f"Phone: {seller['phone']}")
            for line in (seller.get("address") or "").splitlines():
                y -= 12; c.drawRightString(x, y, line)
        # hairline
        if first:
            c.setStrokeColorRGB(0.85, 0.85, 0.85); c.setLineWidth(0.6)
            c.line(72, H - 162, W - 172, H - 162)
        # footer
        c.setFillColor(blue); c.setFont("Times-Bold", 9)
        foot = " | ".join(p for p in (seller.get("name"), seller.get("gstin") and f"GSTIN: {seller['gstin']}",
                                      seller.get("email")) if p)
        c.drawCentredString(W / 2, 36, foot)
        c.setFillColorRGB(0.69, 0.13, 0.13); c.setFont("Times-Bold", 8.5)
        c.drawCentredString(W / 2, 24, "This is a system generated invoice")
        mark = "DRAFT" if draft else "VOID" if inv.get("status") == "void" else None
        if mark:
            c.setFillColorRGB(0.85, 0.2, 0.2); c.setFillAlpha(0.12)
            c.setFont("Helvetica-Bold", 110); c.translate(W / 2, H / 2); c.rotate(35)
            c.drawCentredString(0, 0, mark)
        c.restoreState()

    story = [Spacer(1, 138), Paragraph("TAX INVOICE", title), Spacer(1, 12)]
    number = inv.get("number") or "DRAFT"
    story += [Paragraph(f"Invoice No: {esc(number)}", base),
              Paragraph(f"Date: {esc(_date(data.get('invoice_date', '')))}", base)]
    if data.get("due_date"):
        story.append(Paragraph(f"Due Date: {esc(_date(data['due_date']))}", base))
    story.append(Spacer(1, 10))

    bill = ["Bill To:"]
    for k in ("name", "company"):
        if client.get(k):
            bill.append(esc(client[k]))
    if client.get("business"):
        bill.append(f"Nature of Business: {esc(client['business'])}")
    addr = ", ".join(p for p in (client.get("address"), client.get("city"),
                                 client.get("pincode")) if p)
    if addr:
        bill.append(esc(addr))
    if client.get("gstin"):
        bill.append(f"GSTIN: {esc(client['gstin'].upper())}")
    if tot.get("place_of_supply"):
        code = client.get("state_code") or (client.get("gstin") or "")[:2]
        bill.append(f"Place of Supply: {esc(tot['place_of_supply'])}" + (f" ({code})" if code and code != "96" else ""))
    for line in bill:
        story.append(Paragraph(line, base))
    story.append(Spacer(1, 16))

    # ---- items table
    show_sac = any((it.get("sac") or "").strip() for it in tot["items"])
    head = ["Description of Services"] + (["SAC"] if show_sac else []) + ["Qty", "Rate", "Amount (INR)"]
    rows = [[Paragraph(h, cellb) for h in head]]
    for it in tot["items"]:
        r = [Paragraph(esc(it.get("desc")), cell)]
        if show_sac:
            r.append(Paragraph(esc(it.get("sac")), cell))
        r += [Paragraph(esc(it.get("qty")), cell), Paragraph(inr(it.get("rate")), cell),
              Paragraph(inr(it.get("amount")), cell)]
        rows.append(r)
    has_discount = float(tot.get("discount") or 0) > 0
    if has_discount:
        label = data.get("discount_label") or "Discount"
        if data.get("discount_type") == "percent":
            label += f" ({esc(data.get('discount'))}%)"
        r = [Paragraph(esc(label), cellb)] + [""] * (len(head) - 2) + [Paragraph("- " + inr(tot["discount"]), cellb)]
        rows.append(r)
    avail = W - 144
    widths = ([avail * .36, avail * .13, avail * .08, avail * .18, avail * .25] if show_sac
              else [avail * .36, avail * .10, avail * .30, avail * .24])
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [t, Spacer(1, 12)]

    # ---- totals, in the sample's flowing style
    story.append(Paragraph(f"Subtotal: {inr(tot['taxable'])}", base))
    story.append(Spacer(1, 6))
    if tot["tax_lines"]:
        for tl in tot["tax_lines"]:
            story.append(Paragraph(f"Add: {esc(tl['label'])}: &nbsp;&nbsp;{inr(tl['amount'])}", base))
    else:
        story.append(Paragraph("GST: Not charged" + (f" — {esc(data.get('tax_note'))}" if data.get("tax_note") else ""), base))
    if float(tot.get("round_off") or 0):
        story.append(Paragraph(f"Round off: {inr(tot['round_off'])}", base))
    # The stamp — loud by request: boxed, bold, red, on the page body.
    stamp_style = ParagraphStyle("stamp", parent=bold, fontSize=13, leading=17,
                                 alignment=TA_CENTER, textColor=colors.Color(0.69, 0.13, 0.13))
    stamp = Table([[Paragraph("THIS IS A SYSTEM GENERATED INVOICE", stamp_style)],
                   [Paragraph("No signature is required.", ParagraphStyle(
                       "stamp2", parent=small, alignment=TA_CENTER))]],
                  colWidths=[W - 144])
    stamp.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.6, colors.Color(0.69, 0.13, 0.13)),
        ("BACKGROUND", (0, 0), (-1, -1), colors.Color(1, 0.95, 0.95)),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [Spacer(1, 8), Paragraph(f"Total Amount: INR {inr(tot['total'])}", bold),
              Paragraph(f"<i>{esc(tot.get('total_words'))}</i>", small), Spacer(1, 10),
              KeepTogether([stamp]), Spacer(1, 14)]

    if data.get("payment_terms"):
        story.append(Paragraph(f"Payment Terms: {esc(data['payment_terms'])}", base))
        story.append(Spacer(1, 12))
    story.append(Paragraph("Bank Details:", bold))
    for label, key in (("Account Name", "account_name"), ("Account No", "account_no"),
                       ("IFSC Code", "ifsc"), ("Bank Name", "bank_name"), ("UPI", "upi")):
        if key == "upi" and not bank.get("upi"):
            continue
        story.append(Paragraph(f"{label}: {esc(bank.get(key))}", bold))
    if data.get("notes"):
        story += [Spacer(1, 12), Paragraph("Notes:", bold),
                  Paragraph(esc(data["notes"]).replace("\n", "<br/>"), base)]
    if inv.get("status") == "void":
        story += [Spacer(1, 12), Paragraph(f"VOID — {esc(inv.get('void_reason'))}", bold)]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=72, rightMargin=72, topMargin=40,
                            bottomMargin=48, title=f"Invoice {number}",
                            author=seller.get("name", ""))
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return buf.getvalue()
