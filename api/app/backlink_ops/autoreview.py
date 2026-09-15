"""Backlink Ops — automatic link review (v1.1).

The desk was built so the superuser approves every link. At 30-40 links per
associate per day that is a full-time job, which is the opposite of the point.
This module does the first pass instead:

  1. OPEN the submitted page and look for a link to our domain — the anchor
     text and the real rel attribute (dofollow / nofollow) come from the page,
     not from the form.
  2. HARD RULES that need no judgement: page missing, our link not on it,
     spam score over 5%, a third link on the same site today. These are sent
     back to the associate with a one-line reason.
  3. ONE batched AI call for everything that passed, asking only for the
     judgement calls (relevance, plausible DA, spam site). Approve / send back
     / flag. If the AI is off, capped or down, the rules decide alone — a
     clean deterministic pass is approved, nothing is ever silently dropped.

Runs from cron (X-Backlink-Ops-Cron header) once an hour inside working
hours, or from the superuser's "Run now" button. Every decision is stamped in
bo_reviews with reviewer "auto" or "ai", and in the audit trail, so a human
can always see why a link was approved or bounced. Stdlib only.
"""
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse

from . import ai, audit, store
from .config import settings
from .scoring import host_of
from .seed import projects as _projects

UA = ("Mozilla/5.0 (compatible; BacklinkOpsVerifier/1.1; "
      "+https://agenticaiautomation.co) AppleWebKit/537.36 Chrome/124 Safari/537.36")
MAX_BYTES = 1_500_000
# Sites that render links with JavaScript or wall off bots: an empty result
# there means "could not see", not "not there". Left to the AI / a human.
JS_WALLED = ("reddit.com", "quora.com", "linkedin.com", "facebook.com", "instagram.com",
             "x.com", "twitter.com", "medium.com", "pinterest.com", "youtube.com")


# --------------------------------------------------------------- fetching
class _Links(HTMLParser):
    """Collects (href, rel, text) for every <a>, plus the page <title>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self._cur, self._title_on, self.title = [], None, False, ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            a = dict(attrs)
            self._cur = [a.get("href") or "", (a.get("rel") or "").lower(), []]
        elif tag == "title":
            self._title_on = True

    def handle_data(self, data):
        if self._cur is not None:
            self._cur[2].append(data)
        if self._title_on:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "a" and self._cur is not None:
            href, rel, text = self._cur
            self.links.append((href, rel, " ".join("".join(text).split())))
            self._cur = None
        elif tag == "title":
            self._title_on = False


def _norm(s):
    return " ".join(str(s or "").lower().split())


def fetch(url, timeout=None):
    """Returns (status, html_or_None, error). Follows redirects. Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
                                               "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout or settings.VERIFY_TIMEOUT) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            body = r.read(MAX_BYTES)
            if "html" not in ctype and b"<a" not in body[:4000].lower():
                return r.status, None, f"not an HTML page ({ctype.split(';')[0] or 'unknown type'})"
            return r.status, body.decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 — DNS, timeout, TLS, refused: all "could not open"
        return 0, None, str(e)[:120]


def inspect(html, our_domain, anchor):
    """Looks for a link to `our_domain`. Returns
    {"found": bool, "follow": "dofollow"|"nofollow"|None, "anchor_match": bool|None,
     "title": str, "matches": int}."""
    p = _Links()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 — broken HTML is still HTML
        pass
    dom = our_domain.lower().lstrip(".")
    want = _norm(anchor)
    hits = []
    for href, rel, text in p.links:
        h = href.strip()
        if not h or h.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            host = (urlparse(h if "://" in h else "https://" + h).hostname or "").lower()
        except Exception:
            continue
        if host == dom or host.endswith("." + dom):
            hits.append((rel, _norm(text)))
    if not hits:
        return {"found": False, "follow": None, "anchor_match": None,
                "title": _norm(p.title)[:120], "matches": 0}
    # Prefer the hit whose text matches the claimed anchor; else the first.
    best = next((h for h in hits if want and (h[1] == want or want in h[1])), hits[0])
    nofollow = any(t in best[0].split() for t in ("nofollow", "ugc", "sponsored"))
    return {"found": True, "follow": "nofollow" if nofollow else "dofollow",
            "anchor_match": (best[1] == want or want in best[1]) if want else None,
            "title": _norm(p.title)[:120], "matches": len(hits)}


def verify(entry, project):
    """Open one submitted URL and report what is really there. Never raises."""
    url = entry["url"]
    host = host_of(url)
    status, html, err = fetch(url)
    out = {"http": status, "error": err, "found": None, "follow": None,
           "anchor_match": None, "title": "", "walled": any(host == d or host.endswith("." + d)
                                                            for d in JS_WALLED)}
    if html is None:
        return out
    out.update(inspect(html, project.get("domain") or "", entry.get("anchor")))
    return out


# --------------------------------------------------------------- the run
def _same_host_count(entry, all_pending_today):
    h = entry["host"]
    return sum(1 for e in all_pending_today
               if e["project"] == entry["project"] and e["date"] == entry["date"] and e["host"] == h)


def run(trigger="cron", actor="auto-review"):
    """One pass over every pending link. Returns a summary dict (also stored
    as bo_config['autoreview_last'] for the desk)."""
    started = time.time()
    summary = {"trigger": trigger, "at": store.now_iso(), "checked": 0, "approved": 0,
               "sent_back": 0, "flagged": 0, "ai": "off", "errors": 0, "seconds": 0}
    if not settings.AUTOREVIEW:
        summary["skipped"] = "BACKLINK_OPS_AUTOREVIEW is off"
        store.put_meta("autoreview_last", summary, actor)
        return summary

    cfg = store.get_config()
    P = _projects(cfg)
    pending = store.pending_entries(settings.AUTOREVIEW_MAX_AGE_DAYS)
    # Everything logged today, approved or not, for the repeat-domain rule.
    today = store.today_ist()
    todays = {}
    for e in pending:
        todays.setdefault(e["project"], None)
    todays = {p: store.entries_for(p, today) for p in todays}

    candidates, last_fetch_host = [], {}
    for e in pending:
        proj = P.get(e["project"])
        if not proj:
            continue
        summary["checked"] += 1

        # Hard rules that need no page fetch.
        if float(e.get("spam") or 0) > 5:
            _decide(e, "needs_fix", "Spam score is over 5% — pick a cleaner site.", "auto")
            summary["sent_back"] += 1
            continue
        repeats = _same_host_count(e, todays.get(e["project"], []))
        if repeats >= 3:
            _decide(e, "needs_fix", f"That is link #{repeats} on {e['host']} today — "
                                    "spread across different sites.", "auto")
            summary["sent_back"] += 1
            continue

        # Polite crawling: small gap between hits on the same host.
        gap = settings.VERIFY_MIN_GAP
        if gap and last_fetch_host.get(e["host"]):
            wait = gap - (time.time() - last_fetch_host[e["host"]])
            if wait > 0:
                time.sleep(min(wait, 3))
        v = verify(e, proj)
        last_fetch_host[e["host"]] = time.time()

        if v["http"] in (404, 410):
            _decide(e, "needs_fix", f"Page not found (HTTP {v['http']}) — check the URL.", "auto")
            summary["sent_back"] += 1
            continue
        if v["found"] is False and not v["walled"]:
            _decide(e, "needs_fix", "Our link is not on that page yet. If it is waiting for "
                                    "moderation, log it again once it is live.", "auto")
            summary["sent_back"] += 1
            continue
        if v["found"] and v["follow"] and v["follow"] != e.get("follow"):
            # The page is the truth; fix the field so scoring is honest.
            store.set_entry_follow(e["id"], v["follow"])
            e["follow"] = v["follow"]
            e["_follow_fixed"] = True
        if v["error"] and not v["walled"] and v["http"] not in (403, 429, 401, 503):
            summary["errors"] += 1

        candidates.append((e, v))

    # One AI call for the lot (capped), else rules alone.
    verdicts = None
    if candidates and ai.available():
        batch = candidates[:settings.AUTOREVIEW_BATCH]
        groups = {}
        for e, v in batch:
            g = groups.setdefault(e["project"], {"project": P[e["project"]], "links": []})
            g["links"].append({"id": e["id"], "url": e["url"], "host": e["host"], "type": e["type"],
                               "da": e["da"], "spam": e["spam"], "follow": e["follow"],
                               "anchor": e["anchor"], "target": e["target"],
                               "page_title": v.get("title") or "",
                               # A bot wall with no link on it is "could not see", not "absent".
                               "link_found": (None if (v["walled"] and not v["found"]) else v["found"])})
        verdicts = ai.review_batch(list(groups.values()))
        summary["ai"] = settings.AI_PROVIDER if verdicts is not None else "failed"

    for e, v in candidates:
        fixed = " (rel attribute corrected to %s from the page)" % e["follow"] if e.get("_follow_fixed") else ""
        vd = (verdicts or {}).get(e["id"])
        if vd:
            if vd["verdict"] == "approve":
                _decide(e, "approved", ("Checked by AI." + fixed).strip(), "ai")
                summary["approved"] += 1
            elif vd["verdict"] == "needs_fix":
                _decide(e, "needs_fix", vd["note"] or "Please re-check this link.", "ai")
                summary["sent_back"] += 1
            else:
                _decide(e, "pending", "Needs a human look: " + (vd["note"] or "AI could not tell."), "ai")
                summary["flagged"] += 1
            continue
        # Rules alone (AI off/failed, or this link fell outside the batch).
        if v["found"]:
            _decide(e, "approved", ("Link verified on the page." + fixed).strip(), "auto")
            summary["approved"] += 1
        else:
            why = ("Could not open the page (%s)." % (v["error"] or "bot wall")) if v["error"] \
                else "Page opened but the link could not be confirmed."
            _decide(e, "pending", "Needs a human look: " + why, "auto")
            summary["flagged"] += 1

    summary["seconds"] = round(time.time() - started, 1)
    store.put_meta("autoreview_last", summary, actor)
    audit.stamp("autoreview.run", actor=actor, role="system", detail=summary)
    return summary


def _decide(entry, status, note, reviewer):
    store.set_decision(entry["id"], status, note, reviewer)
    audit.stamp("autoreview.decide", actor=reviewer, role="system", target=entry["id"],
                       detail={"status": status, "reviewer": reviewer, "host": entry["host"],
                               "project": entry["project"], "note": note})
