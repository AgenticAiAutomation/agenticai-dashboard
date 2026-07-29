"""Shared dependencies and helpers for the SEO routers."""
import re
import secrets
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.models import ROLE_ADMIN, ROLE_SEO_LEAD, User
from app.seo.models import SeoArticle
from app.seo.services import ServiceUnavailable

# Anyone who may create or edit articles.
seo_user = require_role(ROLE_SEO_LEAD)
# Jai only — publishing, user management, author-review actions.
admin_user = require_role(ROLE_ADMIN)


def get_article(article_id: UUID, db: Session = Depends(get_db)) -> SeoArticle:
    article = db.query(SeoArticle).filter(SeoArticle.id == article_id).first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


def require_cron_secret(x_cron_secret: Optional[str] = Header(default=None)) -> None:
    """Cron endpoints are internal. Without a configured secret they are closed."""
    if not settings.CRON_SECRET:
        raise HTTPException(
            status_code=503,
            detail="CRON_SECRET is not configured, so cron endpoints are disabled.",
        )
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Cron-Secret")


def slugify(value: str, max_length: int = 70) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    if len(slug) <= max_length:
        return slug
    # Cut on a word boundary so the slug stays readable.
    return slug[:max_length].rsplit("-", 1)[0] or slug[:max_length]


def unique_slug(db: Session, base: str, exclude_id: Optional[UUID] = None) -> str:
    slug, suffix = base, 2
    while True:
        query = db.query(SeoArticle).filter(SeoArticle.slug == slug)
        if exclude_id is not None:
            query = query.filter(SeoArticle.id != exclude_id)
        if query.first() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def service_error(exc: ServiceUnavailable) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"error": "service_unavailable", "service": exc.service,
                "message": exc.message},
    )
