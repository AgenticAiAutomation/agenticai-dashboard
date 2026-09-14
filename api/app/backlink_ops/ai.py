"""Backlink Ops — the AI layer.

Advisory only. It never computes a score and never decides whether a task is
complete; it reads the numbers the scoring engine produced and comments. If the
provider is unset, slow, rate-limited or broken, every function here falls back
to a deterministic rule-based answer and the desk carries on working. That is
the whole point: the associates' daily workflow must not depend on a third-party
API being up.

No new dependencies — plain urllib. Add a provider by writing one _call_* and
registering it in _PROVIDERS.
"""
import json
import re
import urllib.error
import urllib.request

from .config import settings
from . import store
from .seed import PROJECTS


# --------------------------------------------------------------- providers
def _post_json(url, payload, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _call_gemini(prompt):
    model = settings.AI_MODEL or "gemini-2.5-flash"
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
           f"?key={settings.AI_KEY}")
    data = _post_json(url,
                      {"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}},
                      {"Content-Type": "application/json"}, settings.AI_TIMEOUT)
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_anthropic(prompt):
    model = settings.AI_MODEL or "claude-sonnet-4-20250514"
    data = _post_json("https://api.anthropic.com/v1/messages",
                      {"model": model, "max_tokens": 1200,
                       "messages": [{"role": "user", "content": prompt}]},
                      {"Content-Type": "application/json",
                       "x-api-key": settings.AI_KEY,
                       "anthropic-version": "2023-06-01"},
                      settings.AI_TIMEOUT)
    return "".join(b.get("text", "") for b in data.get("content", []))


def _call_grok(prompt):
    """xAI Grok. OpenAI-compatible chat-completions endpoint.

    Deliberately does NOT send `response_format: json_object`: if xAI ever
    rejects that field the whole call fails and the desk silently drops to
    rules. The prompt asks for JSON and `_ask_json` extracts the first JSON
    object from the reply, which works on every provider.

    Set BACKLINK_OPS_AI_MODEL to the model id current on your account —
    check https://docs.x.ai/docs/models, the ids change. Confirm with
    POST /api/seo/backlink-ops/ai-selftest after setting it.
    """
    model = settings.AI_MODEL or "grok-3-mini"
    data = _post_json(settings.AI_BASE_URL or "https://api.x.ai/v1/chat/completions",
                      {"model": model, "temperature": 0.2,
                       "messages": [{"role": "user", "content": prompt}]},
                      {"Content-Type": "application/json",
                       "Authorization": "Bearer " + settings.AI_KEY},
                      settings.AI_TIMEOUT)
    return data["choices"][0]["message"]["content"]


_PROVIDERS = {"gemini": _call_gemini, "anthropic": _call_anthropic,
              "grok": _call_grok}


def available():
    return settings.AI_PROVIDER in _PROVIDERS and bool(settings.AI_KEY)


def _ask_json(prompt, kind):
    if not available():
        return None
    if store.ai_calls_today() >= settings.AI_DAILY_CAP:
        return None
    try:
        raw = _PROVIDERS[settings.AI_PROVIDER](prompt)
        store.bump_ai(kind)
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:
        try:
            store.bump_ai(kind, failed=True)
        except Exception:
            pass
        return None


# --------------------------------------------------------------- parsing
def parse_ubersuggest(text):
    t = text or ""

    def g(pattern):
        m = re.search(pattern, t, re.I)
        if not m:
            return None
        try:
            return float(re.sub(r"[,\s]", "", m.group(1)))
        except ValueError:
            return None

    vol = g(r"(?:volume|search volume|vol)\D{0,12}([\d,]+)")
    kd = g(r"(?:seo difficulty|difficulty|\bsd\b|\bkd\b)\D{0,12}(\d{1,3})")
    cpc = g(r"cpc\D{0,12}([\d.,]+)")
    return {"volume": int(vol) if vol is not None else None,
            "kd": int(kd) if kd is not None else None,
            "cpc": str(cpc) if cpc is not None else None}


# --------------------------------------------------------------- keyword verdict
def keyword_verdict(project, kw, pasted):
    nums = parse_ubersuggest(pasted)
    P = PROJECTS[project]
    prompt = (
        f"You are the SEO lead reviewing one keyword for {P['name']}.\n"
        f"Business: {P['niche']}\n"
        f"Landing pages available: {', '.join(P['pages'])}\n"
        f"Keyword under review: \"{kw}\"\n"
        f"Raw Ubersuggest paste from the associate:\n---\n{(pasted or '')[:4000]}\n---\n"
        "Return ONLY JSON: {\"volume\":number|null,\"kd\":number|null,\"cpc\":string|null,"
        "\"verdict\":\"chase\"|\"park\"|\"drop\",\"why\":\"one sentence, max 20 words\","
        "\"targetPage\":\"one path from the list\","
        "\"anchors\":[\"3 varied anchor texts, not all exact match\"],"
        "\"linkPlan\":[\"3 specific off-page actions for THIS keyword, name real site types "
        "or Indian platforms\"],\"nextFocus\":\"one sentence on what to check next\"}")
    out = _ask_json(prompt, "keyword")
    if not out:
        out = _keyword_fallback(P, kw, nums)
        out["_source"] = "rules"
    else:
        out["_source"] = settings.AI_PROVIDER
    out["volume"] = out.get("volume") if out.get("volume") is not None else nums["volume"]
    out["kd"] = out.get("kd") if out.get("kd") is not None else nums["kd"]
    out["cpc"] = out.get("cpc") if out.get("cpc") is not None else nums["cpc"]
    return out


def _keyword_fallback(P, kw, nums):
    kd = 40 if nums["kd"] is None else nums["kd"]
    vol = 0 if nums["volume"] is None else nums["volume"]
    if kd <= 35 and vol >= 100:
        verdict, why = "chase", "Reachable difficulty with real volume."
    elif kd <= 50:
        verdict, why = "park", "Worth revisiting once domain strength improves."
    else:
        verdict, why = "drop", "Too hard for the current domain authority."
    head = kw.split(" ")
    return {"verdict": verdict, "why": why, "targetPage": P["pages"][0],
            "anchors": [kw, " ".join(head[:2]) + " services", P["short"] + " " + head[0]],
            "linkPlan": ["Answer a matching question on Quora India",
                         "Get listed on a niche directory in this category",
                         "Publish one guest post on a relevant Indian blog"],
            "nextFocus": "Run the closest long-tail variant next."}


# --------------------------------------------------------------- day coach
def coach(project, stats, level):
    P = PROJECTS[project]
    rows = [{"url": r["url"], "type": r["type"], "da": r["da"], "spam": r["spam"],
             "follow": r["follow"], "anchor": r["anchor"], "target": r["target"], "pts": r["pts"]}
            for r in stats["rows"]]
    prompt = (
        "You are the SEO lead reviewing one associate's off-page work for today.\n"
        f"Site: {P['name']}. Business: {P['niche']}\n"
        f"Level {level['n']} ({level['name']}) requires: {level['target']} points, "
        f"{level['queries']} keyword queries, average DA {level['min_avg_da']}+, "
        f"{level['high_value']} high-value links, exact-match anchors under "
        f"{round(level['max_exact'] * 100)}%.\n"
        f"Today so far: {stats['points']} points, {stats['counted']} links counting, "
        f"avg DA {stats['avgDa']}, {stats['high']} high-value, {stats['queries']} keyword queries.\n"
        f"Links logged:\n{json.dumps(rows)[:5000]}\n"
        "Return ONLY JSON: {\"grade\":\"Great\"|\"Good\"|\"Needs work\","
        "\"headline\":\"one sentence verdict, max 16 words\","
        "\"wins\":[\"up to 2 specific things done well, name the actual domain or anchor\"],"
        "\"fixes\":[\"2-4 specific corrections, each naming the actual link or anchor and what to "
        "do instead\"],\"tomorrow\":[\"2 concrete targets for tomorrow tied to this site's niche\"]}")
    out = _ask_json(prompt, "coach")
    if out:
        out["_source"] = settings.AI_PROVIDER
        return out
    out = _coach_fallback(stats, level)
    out["_source"] = "rules"
    return out


def _coach_fallback(stats, L):
    from .scoring import host_of
    fixes = []
    if stats["avgDa"] < L["min_avg_da"]:
        fixes.append(f"Average DA is {stats['avgDa']}, below the {L['min_avg_da']} this level needs — "
                     "swap the weakest two submissions for higher-authority sites.")
    if stats["high"] < L["high_value"]:
        fixes.append(f"Only {stats['high']} high-value link(s) today — a guest post, niche edit or "
                     "resource-page placement is worth more than five directories.")
    if any(r.get("follow") != "dofollow" for r in stats["rows"]):
        fixes.append("Some links are nofollow or unchecked — verify the rel attribute before logging.")
    if not fixes:
        fixes.append("Nothing structural to fix — push the DA ceiling higher tomorrow.")
    grade = "Great" if stats["done"] else ("Good" if stats["points"] >= L["target"] * 0.7 else "Needs work")
    return {"grade": grade,
            "headline": f"{stats['points']} points against a {L['target']} target.",
            "wins": [f"{host_of(r['url'])} was a strong placement at DA {r['da']}"
                     for r in stats["rows"] if r["pts"] >= 10][:2],
            "fixes": fixes,
            "tomorrow": ["Open with one high-value placement before any directories.",
                         f"Finish the {L['queries']} Ubersuggest queries before lunch."]}


def selftest():
    """One live round-trip, for use right after switching provider or model.
    Returns a dict a human can read; never raises."""
    if settings.AI_PROVIDER not in _PROVIDERS:
        return {"ok": False, "provider": settings.AI_PROVIDER,
                "detail": "Provider is not one of: " + ", ".join(sorted(_PROVIDERS)) +
                          " (or 'none'). The desk runs on deterministic rules."}
    if not settings.AI_KEY:
        return {"ok": False, "provider": settings.AI_PROVIDER,
                "detail": "BACKLINK_OPS_AI_KEY is empty."}
    try:
        raw = _PROVIDERS[settings.AI_PROVIDER](
            'Reply with exactly this JSON and nothing else: {"ok": true, "echo": "backlink-ops"}')
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return {"ok": False, "provider": settings.AI_PROVIDER, "model": settings.AI_MODEL,
                "detail": f"HTTP {e.code} from the provider. {body}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "provider": settings.AI_PROVIDER, "model": settings.AI_MODEL,
                "detail": f"{type(e).__name__}: {e}"}
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return {"ok": False, "provider": settings.AI_PROVIDER, "model": settings.AI_MODEL,
                "detail": "Reached the provider but the reply held no JSON. "
                          "Verdicts would fall back to rules.", "raw": (raw or "")[:200]}
    try:
        json.loads(m.group(0))
    except Exception:
        return {"ok": False, "provider": settings.AI_PROVIDER, "model": settings.AI_MODEL,
                "detail": "Reply contained malformed JSON.", "raw": (raw or "")[:200]}
    return {"ok": True, "provider": settings.AI_PROVIDER,
            "model": settings.AI_MODEL or "(provider default)",
            "detail": "Live call succeeded and returned parseable JSON."}
