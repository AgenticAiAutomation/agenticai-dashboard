"""Backlink Ops — the scoring engine.

Deterministic and side-effect free: the same sheet always produces the same
score, on the server, in a test, or in a re-run six months from now. The AI
layer never touches a number here — it only comments on the result. That
separation is deliberate: the associates' pay-relevant target must be
auditable and reproducible.

Formula
-------
  points = base(type)
         * da_multiplier
         + 3 if dofollow
         + 4 if topically relevant
         + 2 if verified live/indexed
         * 0.35 if spam score > 5%
         * repeat-domain decay (1.0, 0.7, 0.4 floor)
"""
from urllib.parse import urlparse
from .seed import TYPE_MAP, level as level_for, seed_keywords


def host_of(url):
    try:
        h = urlparse(url).hostname or ""
    except Exception:
        h = ""
    if not h:
        h = str(url or "")
    return h.lower().removeprefix("www.")


def da_multiplier(da):
    da = float(da or 0)
    if da >= 80: return 2.0
    if da >= 60: return 1.7
    if da >= 40: return 1.4
    if da >= 20: return 1.0
    return 0.6


def score_entry(entry, same_day_entries):
    t = TYPE_MAP.get(entry.get("type"), {"p": 3, "tier": "low"})
    pts = float(t["p"]) * da_multiplier(entry.get("da"))
    flags = []

    if entry.get("follow") == "dofollow":
        pts += 3
    elif entry.get("follow") == "nofollow":
        flags.append("Nofollow — no link equity bonus.")
    else:
        flags.append("Follow attribute not checked yet.")

    if entry.get("relevant"):
        pts += 4
    if entry.get("indexed"):
        pts += 2

    if float(entry.get("spam") or 0) > 5:
        pts *= 0.35
        flags.append("Spam score above 5% — most of the value is stripped.")

    if float(entry.get("da") or 0) < 20:
        flags.append("DA under 20 — counts at 60%.")

    h = host_of(entry.get("url"))
    repeats = sum(1 for x in same_day_entries
                  if x.get("id") != entry.get("id") and host_of(x.get("url")) == h)
    if repeats:
        pts *= max(0.4, 1 - repeats * 0.3)
        flags.append("Repeat domain today — diminishing returns applied.")

    return {"pts": round(pts, 1), "flags": flags, "tier": t["tier"]}


def exact_anchor_share(entries, project, bank_keywords=(), cfg=None):
    if not entries:
        return 0.0
    pool = {k.lower().strip() for k in seed_keywords(project, cfg) + list(bank_keywords)}
    exact = sum(1 for e in entries if str(e.get("anchor") or "").lower().strip() in pool)
    return exact / len(entries)


def day_stats(entries, decisions, queries, cfg_level, project, bank_keywords=(), cfg=None):
    """Returns the full per-day picture: scored rows, totals and the
    requirement checklist the associate has to clear."""
    L = level_for(cfg_level, cfg)
    rows, points, counted, high, da_sum, indexed, rejected = [], 0.0, 0, 0, 0.0, 0, 0

    for e in entries:
        sc = score_entry(e, entries)
        dec = decisions.get(e["id"]) or {}
        status = dec.get("status", "pending")
        row = dict(e)
        row.update({"pts": sc["pts"], "flags": sc["flags"], "tier": sc["tier"],
                    "status": status, "note": dec.get("note")})
        rows.append(row)
        if status == "rejected":
            rejected += 1
            continue
        points += sc["pts"]
        counted += 1
        da_sum += float(e.get("da") or 0)
        if sc["tier"] == "high":
            high += 1
        if e.get("indexed"):
            indexed += 1

    points = round(points, 1)
    avg_da = round(da_sum / counted) if counted else 0
    live = [e for e in entries if (decisions.get(e["id"]) or {}).get("status") != "rejected"]
    exact = exact_anchor_share(live, project, bank_keywords, cfg)
    nq = len(queries)

    reqs = [
        {"k": "points",  "ok": points >= L["target"],
         "label": f"Reach {L['target']} link points", "now": f"{round(points)} / {L['target']}"},
    ]
    if L.get("min_links", 0) > 0:
        reqs.append({"k": "links", "ok": counted >= L["min_links"],
                     "label": f"Log {L['min_links']}+ links (approved or pending)",
                     "now": f"{counted} / {L['min_links']}"})
    reqs += [
        {"k": "queries", "ok": nq >= L["queries"],
         "label": f"Run {L['queries']} Ubersuggest queries", "now": f"{nq} / {L['queries']}"},
        {"k": "da",      "ok": counted > 0 and avg_da >= L["min_avg_da"],
         "label": f"Average DA of {L['min_avg_da']}+", "now": f"{avg_da if counted else '—'} avg"},
    ]
    if L["high_value"] > 0:
        reqs.append({"k": "high", "ok": high >= L["high_value"],
                     "label": f"{L['high_value']}+ high-value link"
                              f"{'s' if L['high_value'] > 1 else ''} "
                              "(guest post, niche edit, PR, resource page)",
                     "now": f"{high} / {L['high_value']}"})
    if L["index_rate"] > 0:
        rate = (indexed / counted) if counted else 0
        reqs.append({"k": "idx", "ok": counted > 0 and rate >= L["index_rate"],
                     "label": f"{round(L['index_rate'] * 100)}% of links verified live",
                     "now": f"{round(rate * 100)}%" if counted else "—"})
    reqs.append({"k": "anchor", "ok": exact <= L["max_exact"],
                 "label": f"Exact-match anchors under {round(L['max_exact'] * 100)}%",
                 "now": f"{round(exact * 100)}%"})
    reqs.append({"k": "fix", "ok": rejected == 0,
                 "label": "No rejected links left to fix",
                 "now": f"{rejected} to fix" if rejected else "clear"})

    done = all(r["ok"] for r in reqs)
    if not counted:
        band = "none"
    elif done:
        band = "great"
    elif points >= L["target"] * 0.7:
        band = "good"
    else:
        band = "work"

    return {"rows": rows, "points": points, "counted": counted, "queries": nq,
            "avgDa": avg_da, "high": high, "rejected": rejected, "reqs": reqs,
            "done": done, "band": band, "target": L["target"], "level": L}
