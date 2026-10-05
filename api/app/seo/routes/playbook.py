"""Blog Playbook routes — flag status, saved builder blocks, advisory skim score.

All three are read-only. They live in their own router so removing the one
include in app/main.py removes them completely (docs/BCP_AND_ROLLBACK.md).
With the flag off for the caller, the article routes answer 404 — the
dashboard hides the Playbook UI and the skim dial — and nothing else changes.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.seo import playbook
from app.seo.deps import get_article, seo_user
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
