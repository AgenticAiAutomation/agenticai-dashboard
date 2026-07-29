"""Integration health checks and the WordPress hello-world proof.

These back the Week 1 deliverable: proving the WordPress REST API, Search
Console, Analytics 4, MinIO, LanguageTool, and Claude wiring all answer before
any real article is written.
"""
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from app.audit import log_event
from app.config import settings
from app.database import get_db
from app.models import User
from app.seo.deps import admin_user, seo_user
from app.seo.golive import check_go_live
from app.seo.matrix import APPROVED_MATRIX, COUNTRY_LABELS, VERTICAL_LABELS
from app.seo.models import CountryVerticalMatrix
from app.seo.services import ServiceUnavailable, claude, wordpress
from app.seo.services.google import Analytics4, SearchConsole

router = APIRouter(prefix="/api/seo", tags=["seo-infra"])


@router.get("/matrix")
def get_matrix(db: Session = Depends(get_db), current_user: User = Depends(seo_user)):
    """The approved country x vertical grid, as the UI renders it."""
    rows = db.query(CountryVerticalMatrix).all()
    if not rows:
        # Fall back to the code constant if the seed has not run yet.
        return {
            "source": "code_fallback",
            "verticals": [
                {
                    "vertical": vertical.value,
                    "label": VERTICAL_LABELS[vertical],
                    "approved_countries": [
                        {"country": c.value, "label": COUNTRY_LABELS[c]}
                        for c in countries
                    ],
                }
                for vertical, countries in APPROVED_MATRIX.items()
            ],
        }

    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        entry = grouped.setdefault(row.vertical, {
            "vertical": row.vertical,
            "label": VERTICAL_LABELS.get(row.vertical, row.vertical),
            "approved_countries": [],
            "blocked_countries": [],
        })
        target = "approved_countries" if row.approved else "blocked_countries"
        entry[target].append({"country": row.country,
                              "label": COUNTRY_LABELS.get(row.country, row.country)})

    return {"source": "database", "verticals": list(grouped.values())}


@router.get("/health/integrations")
def integration_health(current_user: User = Depends(admin_user)):
    """One call that tells Jai exactly which integrations are live."""
    results: Dict[str, Any] = {"checked_at": datetime.now(timezone.utc).isoformat()}

    client = wordpress.get_client()
    results["wordpress"] = {"base_url": client.base_url, "credentials_set": client.configured}
    try:
        results["wordpress"].update(client.ping())
    except ServiceUnavailable as exc:
        results["wordpress"].update({"ok": False, "error": exc.message})

    console = SearchConsole()
    results["search_console"] = {"configured": console.configured,
                                 "site_url": console.site_url}
    if console.configured:
        try:
            results["search_console"].update(console.verify())
        except ServiceUnavailable as exc:
            results["search_console"].update({"ok": False, "error": exc.message})

    ga4 = Analytics4()
    results["analytics4"] = {"configured": ga4.configured, "property_id": ga4.property_id}
    if ga4.configured:
        try:
            results["analytics4"].update(ga4.verify())
        except ServiceUnavailable as exc:
            results["analytics4"].update({"ok": False, "error": exc.message})

    results["anthropic"] = {
        "configured": bool(settings.ANTHROPIC_API_KEY),
        "model": settings.ANTHROPIC_MODEL,
        "daily_budget_inr": settings.SEO_DAILY_BUDGET_INR,
    }
    results["minio"] = {
        "configured": bool(settings.MINIO_ENDPOINT and settings.MINIO_ACCESS_KEY),
        "bucket": settings.MINIO_BUCKET,
    }
    results["languagetool"] = _probe(f"{settings.LANGUAGETOOL_URL.rstrip('/')}/v2/languages")
    results["embedder"] = ({"configured": False, "note": "EMBEDDER_URL not set"}
                           if not settings.EMBEDDER_URL
                           else _probe(settings.EMBEDDER_URL))
    results["serpapi"] = {"configured": bool(settings.SERPAPI_KEY)}
    results["ai_detection"] = {
        "configured": False,
        "note": "No Originality.ai or GPTZero key is wired. Publish rule 5 "
                "(AI detection <20%) is not enforced until one is.",
    }

    go_live = check_go_live()
    results["go_live"] = {
        "approved": go_live.approved,
        "reason": go_live.reason,
        "approval_file": settings.SEO_LIVE_APPROVAL_FILE,
        "wp_status_posts_will_use": go_live.wp_status,
    }
    return results


def _probe(url: str) -> Dict[str, Any]:
    import httpx
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
        return {"configured": True, "reachable": response.status_code < 500,
                "status_code": response.status_code}
    except Exception as exc:
        return {"configured": True, "reachable": False, "error": str(exc)}


@router.post("/health/wordpress-hello-world")
def wordpress_hello_world(
    request: Request,
    title: str = Body(default="Hello world from the dashboard", embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_user),
):
    """Publish a throwaway post to prove the WP REST path end to end.

    Always created as a WordPress draft regardless of the go-live file — this is
    an infrastructure probe, not editorial content.
    """
    client = wordpress.get_client()
    slug = f"dashboard-connectivity-check-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    html = (
        "<p>This post was created by the AgenticAI dashboard to verify the "
        "WordPress REST API integration. It is safe to delete.</p>"
    )
    try:
        post = client.create_or_update_post(
            title=title, content_html=html, slug=slug, status="draft",
            excerpt="Automated connectivity check.",
        )
    except ServiceUnavailable as exc:
        raise ServiceUnavailableHTTP(exc)

    log_event(db, "seo.infra.wp_hello_world", current_user, request,
              target_type="wp_post", target_id=post.id, detail=post.link)
    return {
        "wp_post_id": post.id, "wp_status": post.status, "link": post.link,
        "note": "Created as a WordPress draft. Delete it from WP admin once verified.",
    }


def ServiceUnavailableHTTP(exc: ServiceUnavailable):
    from fastapi import HTTPException
    return HTTPException(status_code=503, detail={
        "error": "service_unavailable", "service": exc.service, "message": exc.message})
