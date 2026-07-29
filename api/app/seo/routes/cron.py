"""Internal cron endpoints.

Called by systemd timers on the VPS with the X-Cron-Secret header. Each one is
idempotent for the day it runs, so a retry does not double-write.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.seo import enums
from app.seo.deps import require_cron_secret
from app.seo.golive import check_go_live
from app.seo.models import (
    SeoArticle, SeoAudit, SeoBacklink, SeoGscDaily, SeoPullRequest, SeoRecommendation,
)
from app.seo.services import ServiceUnavailable
from app.seo.services.google import Analytics4, SearchConsole

router = APIRouter(prefix="/api/seo/cron", tags=["seo-cron"],
                   dependencies=[Depends(require_cron_secret)])


def _upsert_recommendation(db: Session, *, priority: str, category: str, title: str,
                           description: str, action: str) -> bool:
    """Add a recommendation unless an identical unresolved one already exists."""
    existing = (db.query(SeoRecommendation)
                .filter(SeoRecommendation.title == title,
                        SeoRecommendation.resolved_at.is_(None)).first())
    if existing:
        return False
    db.add(SeoRecommendation(priority=priority, category=category, title=title,
                             description=description, action_required=action))
    return True


def _sync_gsc(db: Session, days: int) -> Dict[str, Any]:
    """Pull Search Analytics into seo_gsc_daily. GSC data lags ~2 days."""
    console = SearchConsole()
    if not console.configured:
        return {"synced": 0, "skipped": "GSC service account not configured"}

    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=days)
    try:
        rows = console.query(start, end, dimensions=["date", "query", "page"])
    except ServiceUnavailable as exc:
        return {"synced": 0, "error": exc.message}

    written = 0
    for row in rows:
        try:
            row_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        query_text, page_url = row.get("query") or "", row.get("page") or ""

        record = (db.query(SeoGscDaily)
                  .filter(SeoGscDaily.date == row_date,
                          SeoGscDaily.query == query_text,
                          SeoGscDaily.page_url == page_url).first())
        if record is None:
            record = SeoGscDaily(date=row_date, query=query_text, page_url=page_url)
            db.add(record)
        record.clicks = int(row.get("clicks") or 0)
        record.impressions = int(row.get("impressions") or 0)
        record.avg_position = row.get("position")
        record.ctr = row.get("ctr")
        written += 1
    return {"synced": written, "range": [start.isoformat(), end.isoformat()]}


@router.post("/daily-audit")
def daily_audit(db: Session = Depends(get_db)):
    today = date.today()
    gsc = _sync_gsc(db, days=3)

    published = SeoArticle.status == enums.ArticleStatus.published.value
    findings: Dict[str, Any] = {
        "gsc": gsc,
        "published_total": (db.query(func.count(SeoArticle.id))
                            .filter(published).scalar()) or 0,
        "published_last_7d": (db.query(func.count(SeoArticle.id))
                              .filter(published,
                                      SeoArticle.published_at >= today - timedelta(days=7))
                              .scalar()) or 0,
        "backlinks_last_7d": (db.query(func.count(SeoBacklink.id))
                              .filter(SeoBacklink.discovered_at >=
                                      today - timedelta(days=7)).scalar()) or 0,
        "open_pull_requests": (db.query(func.count(SeoPullRequest.id))
                               .filter(SeoPullRequest.converted_to_article_id.is_(None))
                               .scalar()) or 0,
        "go_live_approved": check_go_live().approved,
    }

    created = 0
    if findings["published_last_7d"] < 6:
        created += _upsert_recommendation(
            db, priority="high", category="content",
            title="Publishing velocity is below the 6/week target",
            description=f"{findings['published_last_7d']} articles published in the "
                        f"last 7 days against a target of 6.",
            action="Move the highest-scoring drafts through author review today.",
        )
    if findings["backlinks_last_7d"] < 3:
        created += _upsert_recommendation(
            db, priority="medium", category="backlink",
            title="Backlink velocity is below the 3/week target",
            description=f"{findings['backlinks_last_7d']} backlinks recorded in the "
                        f"last 7 days against a target of 3.",
            action="Answer three HARO queries and log the placements in /seo/backlinks.",
        )
    if findings["open_pull_requests"] < 10:
        created += _upsert_recommendation(
            db, priority="low", category="content",
            title="Pull request backlog is running low",
            description=f"Only {findings['open_pull_requests']} unconverted questions "
                        f"remain in the inbox.",
            action="Run the Reddit/Quora/PAA scrape or capture questions manually.",
        )

    # Orphan check: published articles with no inbound internal links.
    orphans = []
    published_articles = db.query(SeoArticle).filter(published).all()
    corpus = "\n".join(a.final_md or "" for a in published_articles)
    for article in published_articles:
        if article.slug and corpus.count(f"/{article.slug}") < 2:
            orphans.append(article.slug)
    if orphans:
        findings["orphans"] = orphans
        created += _upsert_recommendation(
            db, priority="medium", category="technical",
            title=f"{len(orphans)} published articles are orphaned",
            description="These have fewer than 2 inbound internal links: "
                        + ", ".join(orphans[:15]),
            action="Add internal links from related published articles.",
        )

    findings["recommendations_created"] = created
    _record_audit(db, enums.AuditType.daily, today, findings)
    db.commit()
    return {"audit_type": "daily", "date": today.isoformat(), "findings": findings}


@router.post("/weekly-audit")
def weekly_audit(db: Session = Depends(get_db)):
    today = date.today()
    gsc = _sync_gsc(db, days=14)

    week_start = today - timedelta(days=7)
    scores = (db.query(func.avg(SeoArticle.current_score))
              .filter(SeoArticle.updated_at >= week_start,
                      SeoArticle.current_score.isnot(None)).scalar())

    findings = {
        "gsc": gsc,
        "avg_score_this_week": round(float(scores), 1) if scores is not None else None,
        "clicks_last_7d": int((db.query(func.coalesce(func.sum(SeoGscDaily.clicks), 0))
                               .filter(SeoGscDaily.date >= week_start).scalar()) or 0),
        "impressions_last_7d": int(
            (db.query(func.coalesce(func.sum(SeoGscDaily.impressions), 0))
             .filter(SeoGscDaily.date >= week_start).scalar()) or 0),
        "top10_pages": (db.query(func.count(func.distinct(SeoGscDaily.page_url)))
                        .filter(SeoGscDaily.date >= week_start,
                                SeoGscDaily.avg_position <= 10).scalar()) or 0,
    }

    created = 0
    if findings["avg_score_this_week"] is not None and findings["avg_score_this_week"] < 80:
        created += _upsert_recommendation(
            db, priority="high", category="content",
            title="Average article score is below the publish threshold",
            description=f"This week's average is {findings['avg_score_this_week']}/100. "
                        f"Publishing requires 80.",
            action="Work the line-by-line comments on the lowest-scoring drafts.",
        )
    findings["recommendations_created"] = created

    _record_audit(db, enums.AuditType.weekly, today, findings)
    db.commit()
    return {"audit_type": "weekly", "date": today.isoformat(), "findings": findings}


@router.post("/monthly-audit")
def monthly_audit(db: Session = Depends(get_db)):
    today = date.today()
    gsc = _sync_gsc(db, days=35)
    month_start = today - timedelta(days=30)

    findings = {
        "gsc": gsc,
        "published_this_month": (db.query(func.count(SeoArticle.id))
                                 .filter(SeoArticle.status ==
                                         enums.ArticleStatus.published.value,
                                         SeoArticle.published_at >= month_start)
                                 .scalar()) or 0,
        "backlinks_this_month": (db.query(func.count(SeoBacklink.id))
                                 .filter(SeoBacklink.discovered_at >= month_start)
                                 .scalar()) or 0,
        "clicks_this_month": int(
            (db.query(func.coalesce(func.sum(SeoGscDaily.clicks), 0))
             .filter(SeoGscDaily.date >= month_start).scalar()) or 0),
    }

    ga4 = Analytics4()
    if ga4.configured:
        try:
            findings["ga4_organic"] = ga4.organic_sessions(month_start, today)[:60]
        except ServiceUnavailable as exc:
            findings["ga4_error"] = exc.message
    else:
        findings["ga4"] = "not configured"

    _record_audit(db, enums.AuditType.monthly, today, findings)
    db.commit()
    return {"audit_type": "monthly", "date": today.isoformat(), "findings": findings}


def _record_audit(db: Session, audit_type: enums.AuditType, audit_date: date,
                  findings: Dict[str, Any]) -> None:
    existing = (db.query(SeoAudit)
                .filter(SeoAudit.audit_type == audit_type.value,
                        SeoAudit.audit_date == audit_date).first())
    if existing:
        merged = dict(existing.results_json or {})
        merged.update(findings)
        existing.results_json = merged
    else:
        db.add(SeoAudit(audit_type=audit_type.value, audit_date=audit_date,
                        results_json=findings))


# --------------------------------------------------------------------------
# Source scraping
# --------------------------------------------------------------------------
VERTICAL_KEYWORDS = {
    enums.Vertical.whatsapp: ["whatsapp automation", "whatsapp business api"],
    enums.Vertical.rpa: ["rpa implementation", "robotic process automation"],
    enums.Vertical.n8n: ["n8n workflow", "n8n automation"],
    enums.Vertical.agentic_ai: ["ai agents for business", "agentic ai automation"],
}


@router.post("/reddit-quora-scrape")
def scrape_sources(
    db: Session = Depends(get_db),
    per_keyword: int = Query(default=3, ge=1, le=10),
):
    """Capture People Also Ask questions via SerpAPI into the pull-request inbox."""
    if not settings.SERPAPI_KEY:
        return {"captured": 0,
                "skipped": "SERPAPI_KEY is not set — capture questions manually via "
                           "POST /api/seo/pull-requests."}

    import httpx

    captured, errors = 0, []
    with httpx.Client(timeout=30.0) as client:
        for vertical, keywords in VERTICAL_KEYWORDS.items():
            for keyword in keywords:
                try:
                    response = client.get("https://serpapi.com/search.json", params={
                        "q": keyword, "engine": "google", "hl": "en",
                        "api_key": settings.SERPAPI_KEY,
                    })
                    response.raise_for_status()
                    questions = response.json().get("related_questions", [])
                except Exception as exc:
                    errors.append({"keyword": keyword, "error": str(exc)})
                    continue

                for item in questions[:per_keyword]:
                    question = (item.get("question") or "").strip()
                    if not question:
                        continue
                    link = item.get("link") or f"https://www.google.com/search?q={keyword}"
                    duplicate = (db.query(SeoPullRequest)
                                 .filter(SeoPullRequest.question_captured == question)
                                 .first())
                    if duplicate:
                        continue
                    db.add(SeoPullRequest(
                        source_platform=enums.PullRequestPlatform.paa.value,
                        source_url=link,
                        question_captured=question,
                        suggested_vertical=vertical.value,
                    ))
                    captured += 1
    db.commit()
    return {"captured": captured, "errors": errors}
