"""Pull-request-style source capture: Reddit / Quora / PAA questions worth answering."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.models import User
from app.seo import enums
from app.seo.deps import seo_user, slugify, unique_slug
from app.seo.matrix import validate_country_vertical
from app.seo.models import SeoArticle, SeoArticleSource, SeoPullRequest
from app.seo.schemas import (
    PullRequestConvert, PullRequestCreate, PullRequestResponse,
)

router = APIRouter(prefix="/api/seo/pull-requests", tags=["seo-pull-requests"])


@router.post("", response_model=PullRequestResponse, status_code=201)
def create_pull_request(
    payload: PullRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    existing = (db.query(SeoPullRequest)
                .filter(SeoPullRequest.source_url == payload.source_url,
                        SeoPullRequest.question_captured == payload.question_captured)
                .first())
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This question has already been captured from that URL.")

    pull_request = SeoPullRequest(
        source_platform=payload.source_platform.value,
        source_url=payload.source_url,
        question_captured=payload.question_captured,
        suggested_vertical=payload.suggested_vertical.value if payload.suggested_vertical else None,
        suggested_country=payload.suggested_country.value if payload.suggested_country else None,
    )
    db.add(pull_request)
    log_event(db, "seo.pull_request.captured", current_user, request,
              target_type="seo_pull_request", detail=payload.question_captured[:200],
              commit=False)
    db.commit()
    db.refresh(pull_request)
    return pull_request


@router.get("", response_model=List[PullRequestResponse])
def list_pull_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
    platform: Optional[enums.PullRequestPlatform] = None,
    vertical: Optional[enums.Vertical] = None,
    converted: Optional[bool] = Query(default=None,
                                      description="Filter to converted or open items"),
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    query = db.query(SeoPullRequest)
    if platform is not None:
        query = query.filter(SeoPullRequest.source_platform == platform.value)
    if vertical is not None:
        query = query.filter(SeoPullRequest.suggested_vertical == vertical.value)
    if converted is True:
        query = query.filter(SeoPullRequest.converted_to_article_id.isnot(None))
    elif converted is False:
        query = query.filter(SeoPullRequest.converted_to_article_id.is_(None))
    return (query.order_by(SeoPullRequest.captured_at.desc())
            .offset(offset).limit(limit).all())


@router.post("/{pull_request_id}/convert-to-article", status_code=201)
def convert_to_article(
    pull_request_id: UUID,
    payload: PullRequestConvert,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    """Turn a captured question into a seo_articles draft with the source pre-filled."""
    pull_request = db.query(SeoPullRequest).filter(
        SeoPullRequest.id == pull_request_id).first()
    if pull_request is None:
        raise HTTPException(status_code=404, detail="Pull request not found")
    if pull_request.converted_to_article_id:
        raise HTTPException(
            status_code=409,
            detail={"error": "already_converted",
                    "article_id": str(pull_request.converted_to_article_id)},
        )

    validate_country_vertical(db, payload.type, payload.vertical, payload.country)

    title = pull_request.question_captured[:120]
    article = SeoArticle(
        type=payload.type.value,
        status=enums.ArticleStatus.drafted_by_author.value,
        title=title,
        slug=unique_slug(db, slugify(payload.primary_keyword or title)),
        vertical=payload.vertical.value,
        country=payload.country.value if payload.country else None,
        primary_keyword=payload.primary_keyword,
        assigned_to=payload.assigned_to,
    )
    db.add(article)
    db.flush()

    db.add(SeoArticleSource(
        article_id=article.id,
        source_url=pull_request.source_url,
        source_platform=pull_request.source_platform,
        question_or_prompt=pull_request.question_captured,
    ))
    pull_request.converted_to_article_id = article.id

    log_event(db, "seo.pull_request.converted", current_user, request,
              target_type="seo_article", target_id=article.id, commit=False)
    db.commit()
    db.refresh(article)

    return {
        "article_id": str(article.id),
        "slug": article.slug,
        "status": article.status,
        "next_step": (
            "Call POST /api/seo/articles/generate with this pull_request_id to have "
            "the author draft written, or edit the shell article directly."
        ),
    }
