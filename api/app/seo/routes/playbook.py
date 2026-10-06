"""Blog Playbook routes — flag status, saved builder blocks, advisory skim score,
and (admins only) who has access.

All but the access PUT are read-only. They live in their own router so removing the one
include in app/main.py removes them completely (docs/BCP_AND_ROLLBACK.md).
With the flag off for the caller, the article routes answer 404 — the
dashboard hides the Playbook UI and the skim dial — and nothing else changes.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import log_event
from app.config import settings
from app.database import get_db
from app.models import ROLE_SEO_LEAD, User
from app.seo import playbook
from app.seo.deps import admin_user, get_article, seo_user
from app.seo.models import SeoArticle
from app.seo.services import skim

router = APIRouter(tags=["seo-playbook"])


def _require_enabled(user: User) -> None:
    if not playbook.enabled_for(user):
        raise HTTPException(status_code=404,
                            detail="The Blog Playbook writer is not enabled.")


@router.get("/api/seo/playbook")
def playbook_status(current_user: User = Depends(seo_user)):
    """Whether the Playbook writer is switched on for the calling login."""
    return {"enabled": playbook.enabled_for(current_user)}


class PlaybookAccessUpdate(BaseModel):
    everyone: bool = False
    emails: List[str] = Field(default_factory=list, max_length=200)


def _access_report(db: Session) -> dict:
    """Every login that can write articles, and whether it has the Playbook."""
    access = playbook.load_access()
    server_users = playbook._allowed_emails()
    users = (db.query(User)
             .filter(User.role.in_(ROLE_SEO_LEAD), User.is_active.is_(True))
             .order_by(User.email).all())
    return {
        "everyone": access["everyone"],
        "emails": access["emails"],
        # Set on the server (systemd drop-in); shown, not editable here.
        "server_enabled": bool(settings.BLOG_PLAYBOOK_ENABLED),
        "server_emails": sorted(server_users),
        "users": [{
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "granted": u.email.lower() in access["emails"],
            "via_server": bool(settings.BLOG_PLAYBOOK_ENABLED) or u.email.lower() in server_users,
            "enabled": playbook.enabled_for(u),
        } for u in users],
    }


@router.get("/api/seo/playbook/access")
def get_playbook_access(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_user),
):
    """Admins: who has the Playbook writer."""
    return _access_report(db)


@router.put("/api/seo/playbook/access")
def set_playbook_access(
    payload: PlaybookAccessUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_user),
):
    """Admins: grant or remove the Playbook writer, per login or for everyone.

    Only logins that can write articles can be granted; anything else is
    refused rather than silently stored.
    """
    eligible = {u.email.lower() for u in db.query(User)
                .filter(User.role.in_(ROLE_SEO_LEAD), User.is_active.is_(True)).all()}
    wanted = {e.strip().lower() for e in payload.emails if e.strip()}
    unknown = sorted(wanted - eligible)
    if unknown:
        raise HTTPException(status_code=422, detail={
            "error": "unknown_logins",
            "message": "These are not active logins that can write articles: "
                       + ", ".join(unknown),
        })
    before = playbook.load_access()
    saved = playbook.save_access(payload.everyone, sorted(wanted))
    log_event(db, "seo.playbook.access_changed", current_user, request,
              target_type="blog_playbook",
              detail=(f"everyone {before['everyone']}->{saved['everyone']}; "
                      f"emails {before['emails']} -> {saved['emails']}"))
    return _access_report(db)


@router.get("/api/seo/articles/{article_id}/playbook")
def get_playbook_blocks(
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    """The saved builder document for this article, or null if there is none."""
    _require_enabled(current_user)
    return {"article_id": str(article.id),
            "playbook_blocks": playbook.load_blocks(db, article.id)}


@router.get("/api/seo/articles/{article_id}/skim")
def skim_score(
    article: SeoArticle = Depends(get_article),
    current_user: User = Depends(seo_user),
):
    """Advisory skim score for the saved draft. Never part of the publish gate."""
    _require_enabled(current_user)
    # Same body the house scorer reads (routes/articles.py `_build_context`).
    markdown = article.final_md or article.team_edit_md or article.author_draft_md or ""
    report = skim.score(markdown, article.primary_keyword or "")
    report["article_id"] = str(article.id)
    return report
