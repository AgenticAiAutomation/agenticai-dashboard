"""Article lifecycle: generate -> team edit -> score -> author review -> publish."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.models import User
from app.seo import enums
from app.seo.deps import (
    admin_user, get_article, seo_user, service_error, slugify, unique_slug,
)
from app.seo.golive import check_go_live
from app.seo.matrix import validate_country_vertical
from app.seo.models import (
    SeoArticle, SeoArticleFaq, SeoArticleSource, SeoArticleVersion, SeoPullRequest,
    SeoScore,
)
from app.seo.schemas import (
    ArticleDetailResponse, ArticleGenerateRequest, ArticleResponse, ArticleTeamEdit,
    FromAuthorStoryRequest, PublishResponse, ScoreResponse, ValidateCountryRequest,
)
from app.seo.services import ServiceUnavailable, claude, scoring, storage, wordpress

router = APIRouter(prefix="/api/seo/articles", tags=["seo-articles"])

PUBLISH_MIN_SCORE = 80


# --------------------------------------------------------------------------
# Generate
# --------------------------------------------------------------------------
@router.post("/generate", response_model=ArticleDetailResponse, status_code=201)
def generate_article(
    payload: ArticleGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    """Author-triggered draft generation. Enforcement rule 1 runs before any spend."""
    validate_country_vertical(db, payload.type, payload.vertical, payload.country)
    claude.check_budget(db)

    published_titles = [
        row[0] for row in db.query(SeoArticle.title)
        .filter(SeoArticle.status == enums.ArticleStatus.published.value)
        .filter(SeoArticle.title.isnot(None)).limit(25).all()
    ]

    prompt = claude.build_draft_prompt(
        article_type=payload.type,
        vertical=payload.vertical,
        country=payload.country,
        primary_keyword=payload.primary_keyword,
        title_hint=payload.title_hint,
        source_platform=payload.source_platform.value if payload.source_platform else None,
        source_url=payload.source_url,
        captured_question=payload.captured_question,
        keyword_difficulty=payload.keyword_difficulty,
        monthly_search_volume=payload.monthly_search_volume,
        competitor_urls=payload.competitor_urls,
        published_titles=published_titles,
    )

    try:
        draft, usage = claude.generate_draft(prompt)
    except ServiceUnavailable as exc:
        raise service_error(exc)

    title = draft.get("title") or payload.title_hint or payload.primary_keyword
    slug = unique_slug(db, slugify(draft.get("slug") or title))

    buyer_intent = payload.buyer_intent.value if payload.buyer_intent else None
    if not buyer_intent:
        candidate = (draft.get("buyer_intent") or "").strip().lower()
        if candidate in {e.value for e in enums.BuyerIntent}:
            buyer_intent = candidate

    article = SeoArticle(
        type=payload.type.value,
        status=enums.ArticleStatus.drafted_by_author.value,
        title=title,
        slug=slug,
        vertical=payload.vertical.value,
        country=payload.country.value if payload.country else None,
        primary_keyword=payload.primary_keyword,
        keyword_difficulty=payload.keyword_difficulty,
        monthly_search_volume=payload.monthly_search_volume,
        buyer_intent=buyer_intent,
        assigned_to=payload.assigned_to,
        author_draft_md=draft.get("body_md"),
        meta_title=draft.get("meta_title"),
        meta_description=draft.get("meta_description"),
        ubersuggest_raw=payload.ubersuggest_raw,
        competitor_urls={
            "competitors": payload.competitor_urls or [],
            "suggested_internal_links": draft.get("internal_link_targets") or [],
            "suggested_external_links": draft.get("external_link_targets") or [],
            "featured_image_concept": draft.get("featured_image_concept"),
        },
    )
    db.add(article)
    db.flush()

    if payload.source_url or payload.captured_question:
        db.add(SeoArticleSource(
            article_id=article.id,
            source_url=payload.source_url,
            source_platform=payload.source_platform.value if payload.source_platform else None,
            question_or_prompt=payload.captured_question,
        ))

    for position, faq in enumerate(draft.get("faqs") or [], start=1):
        platform = (faq.get("source_platform") or "").strip().lower()
        db.add(SeoArticleFaq(
            article_id=article.id,
            question=faq.get("question") or "",
            answer=faq.get("answer"),
            source_url=faq.get("source_url"),
            source_platform=platform if platform in {e.value for e in enums.SourcePlatform}
                            else None,
            position_in_article=position,
        ))

    if payload.pull_request_id:
        pull_request = db.query(SeoPullRequest).filter(
            SeoPullRequest.id == payload.pull_request_id).first()
        if pull_request:
            pull_request.converted_to_article_id = article.id

    claude.record_usage(db, usage, "generate_draft", article.id)
    log_event(db, "seo.article.generated", current_user, request,
              target_type="seo_article", target_id=article.id,
              detail=f"{payload.vertical.value}/{payload.primary_keyword} "
                     f"(₹{usage.cost_inr:.2f})", commit=False)
    db.commit()
    db.refresh(article)
    return _detail(db, article)


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------
@router.get("", response_model=List[ArticleResponse])
def list_articles(
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
    status: Optional[enums.ArticleStatus] = None,
    type: Optional[enums.ArticleType] = None,
    vertical: Optional[enums.Vertical] = None,
    country: Optional[enums.Country] = None,
    assigned_to: Optional[int] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    query = db.query(SeoArticle)
    for column, value in [
        (SeoArticle.status, status), (SeoArticle.type, type),
        (SeoArticle.vertical, vertical), (SeoArticle.country, country),
    ]:
        if value is not None:
            query = query.filter(column == value.value)
    if assigned_to is not None:
        query = query.filter(SeoArticle.assigned_to == assigned_to)
    return (query.order_by(SeoArticle.created_at.desc())
            .offset(offset).limit(limit).all())


@router.get("/{article_id}", response_model=ArticleDetailResponse)
def get_article_detail(
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    return _detail(db, article)


def _detail(db: Session, article: SeoArticle) -> ArticleDetailResponse:
    payload = ArticleDetailResponse.model_validate(article, from_attributes=True)
    payload.sources = db.query(SeoArticleSource).filter(
        SeoArticleSource.article_id == article.id).all()
    payload.faqs = (db.query(SeoArticleFaq)
                    .filter(SeoArticleFaq.article_id == article.id)
                    .order_by(SeoArticleFaq.position_in_article).all())
    return payload


# --------------------------------------------------------------------------
# Country validation
# --------------------------------------------------------------------------
@router.post("/{article_id}/validate-country")
def validate_country(
    payload: ValidateCountryRequest,
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    """200 when the pair is approved, 422 with an explanation when it is not."""
    article_type = payload.type or enums.ArticleType(article.type)
    vertical = payload.vertical or enums.Vertical(article.vertical)
    country = payload.country or (enums.Country(article.country) if article.country else None)

    validate_country_vertical(db, article_type, vertical, country)
    return {
        "approved": True,
        "type": article_type.value,
        "vertical": vertical.value,
        "country": country.value if country else None,
    }


# --------------------------------------------------------------------------
# Team edit
# --------------------------------------------------------------------------
@router.put("/{article_id}/team-edit", response_model=ArticleDetailResponse)
def submit_team_edit(
    payload: ArticleTeamEdit,
    request: Request,
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    if article.status == enums.ArticleStatus.published.value:
        raise HTTPException(
            status_code=409,
            detail="This article is already published. Archive it before editing.",
        )

    article.team_edit_md = payload.team_edit_md
    if payload.meta_title is not None:
        article.meta_title = payload.meta_title
    if payload.meta_description is not None:
        article.meta_description = payload.meta_description
    if payload.slug:
        article.slug = unique_slug(db, slugify(payload.slug), exclude_id=article.id)
    article.status = enums.ArticleStatus.in_team_review.value

    next_version = (db.query(func.coalesce(func.max(SeoArticleVersion.version_number), 0))
                    .filter(SeoArticleVersion.article_id == article.id).scalar()) + 1
    db.add(SeoArticleVersion(
        article_id=article.id,
        version_number=next_version,
        snapshot_md=payload.team_edit_md,
        saved_by=current_user.id,
    ))
    log_event(db, "seo.article.team_edit", current_user, request,
              target_type="seo_article", target_id=article.id,
              detail=f"version {next_version}", commit=False)
    db.commit()
    db.refresh(article)
    return _detail(db, article)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def _build_context(db: Session, article: SeoArticle) -> scoring.ScoringContext:
    markdown = article.final_md or article.team_edit_md or article.author_draft_md or ""

    faqs = [
        {"question": f.question, "answer": f.answer, "source_url": f.source_url}
        for f in db.query(SeoArticleFaq).filter(SeoArticleFaq.article_id == article.id)
        .order_by(SeoArticleFaq.position_in_article).all()
    ]

    # Orphan check: how many other published articles link to this slug.
    inbound = 0
    if article.slug:
        inbound = (db.query(func.count(SeoArticle.id))
                   .filter(SeoArticle.id != article.id)
                   .filter(SeoArticle.status == enums.ArticleStatus.published.value)
                   .filter(func.coalesce(SeoArticle.final_md, "")
                           .like(f"%/{article.slug}%"))
                   .scalar()) or 0

    image_size = None
    if article.featured_image_path:
        try:
            from PIL import Image
            import io
            content, _ = storage.get_object(article.featured_image_path)
            image_size = Image.open(io.BytesIO(content)).size
        except Exception:
            image_size = None

    return scoring.ScoringContext(
        markdown=markdown,
        lines=markdown.splitlines(),
        primary_keyword=article.primary_keyword or "",
        title=article.title,
        slug=article.slug,
        meta_title=article.meta_title,
        meta_description=article.meta_description,
        from_author_story=article.from_author_story,
        featured_image_alt=article.featured_image_alt,
        featured_image_size=image_size,
        faqs=faqs,
        inbound_internal_links=inbound,
    )


@router.post("/{article_id}/score", response_model=ScoreResponse)
def score_article_endpoint(
    request: Request,
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    report = scoring.score_article(_build_context(db, article))

    next_version = (db.query(func.coalesce(func.max(SeoArticleVersion.version_number), 0))
                    .filter(SeoArticleVersion.article_id == article.id).scalar()) or 1

    db.add(SeoScore(
        article_id=article.id,
        version_number=next_version,
        total_score=report["total_score"],
        breakdown_json={"groups": report["groups"], "parameters": report["parameters"],
                        "parameters_skipped": report["parameters_skipped"]},
        comments_json={"comments": report["comments"]},
    ))
    article.current_score = report["total_score"]
    if article.status == enums.ArticleStatus.in_team_review.value:
        article.status = enums.ArticleStatus.submitted_for_scoring.value

    log_event(db, "seo.article.scored", current_user, request,
              target_type="seo_article", target_id=article.id,
              detail=f"score {report['total_score']}", commit=False)
    db.commit()

    return ScoreResponse(
        article_id=article.id,
        version_number=next_version,
        total_score=report["total_score"],
        max_score=100,
        groups=report["groups"],
        parameters=report["parameters"],
        comments=report["comments"],
        scored_at=datetime.now(timezone.utc),
        blocking_issues=_blocking_issues(article, report["total_score"]),
    )


def _blocking_issues(article: SeoArticle, score: Optional[int]) -> List[str]:
    """Everything standing between this article and a live publish."""
    issues = []
    if (score if score is not None else article.current_score or 0) < PUBLISH_MIN_SCORE:
        issues.append(
            f"Score is {score or 0}/100; publishing requires {PUBLISH_MIN_SCORE}.")
    if not (article.from_author_story or "").strip():
        issues.append("The [FROM AUTHOR] section is empty.")
    if not (article.featured_image_alt or "").strip():
        issues.append("The featured image alt caption is missing.")
    if not article.featured_image_path:
        issues.append("No featured image uploaded — WordPress rejects publish without one.")
    return issues


# --------------------------------------------------------------------------
# Hand-off to author
# --------------------------------------------------------------------------
@router.post("/{article_id}/submit-for-author", response_model=ArticleResponse)
def submit_for_author(
    request: Request,
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
    min_score: int = Query(default=70, ge=0, le=100,
                           description="70 for weeks 1-4, 80 from week 5"),
):
    if not (article.team_edit_md or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Submit the team edit before handing the article to the author.")
    if (article.current_score or 0) < min_score:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "score_below_threshold",
                "message": f"Score is {article.current_score or 0}/100; this hand-off "
                           f"requires at least {min_score}. Run Score Draft and fix the "
                           f"highest-impact comments first.",
                "current_score": article.current_score or 0,
                "required": min_score,
            },
        )

    article.status = enums.ArticleStatus.author_review.value
    article.final_md = article.team_edit_md
    log_event(db, "seo.article.submitted_for_author", current_user, request,
              target_type="seo_article", target_id=article.id, commit=False)
    db.commit()
    db.refresh(article)
    return article


@router.put("/{article_id}/from-author-story", response_model=ArticleResponse)
def set_from_author_story(
    payload: FromAuthorStoryRequest,
    request: Request,
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_user),
):
    story = payload.from_author_story.strip()
    if not story:
        raise HTTPException(status_code=422, detail="The From Author section cannot be blank.")

    article.from_author_story = story
    # Substitute the placeholder in the copy that will actually be published.
    body = article.final_md or article.team_edit_md or article.author_draft_md or ""
    import re
    replaced, count = re.subn(r"\[FROM AUTHOR:[^\]]*\]",
                             f"## From the author\n\n{story}", body)
    article.final_md = replaced if count else (
        body + f"\n\n## From the author\n\n{story}\n")

    if article.status == enums.ArticleStatus.author_review.value:
        article.status = enums.ArticleStatus.ready_to_publish.value

    log_event(db, "seo.article.from_author_filled", current_user, request,
              target_type="seo_article", target_id=article.id, commit=False)
    db.commit()
    db.refresh(article)
    return article


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------
@router.post("/{article_id}/upload-image")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    content = await file.read()
    try:
        path = storage.put_object(str(article.id), content,
                                  file.content_type or "image/jpeg")
    except ServiceUnavailable as exc:
        raise service_error(exc)

    article.featured_image_path = path
    log_event(db, "seo.article.image_uploaded", current_user, request,
              target_type="seo_article", target_id=article.id,
              detail=file.filename, commit=False)
    db.commit()
    return {"featured_image_path": path, "bytes": len(content)}


@router.post("/{article_id}/generate-alt")
def generate_alt(
    request: Request,
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    if not article.featured_image_path:
        raise HTTPException(status_code=422,
                            detail="Upload a featured image before generating alt text.")
    claude.check_budget(db)

    body = article.final_md or article.team_edit_md or article.author_draft_md or ""
    try:
        content, mime = storage.get_object(article.featured_image_path)
        alt, usage = claude.generate_alt_caption(
            image_bytes=content,
            mime_type=mime,
            title=article.title or "",
            primary_keyword=article.primary_keyword or "",
            context=scoring.strip_markdown(body)[:1500],
        )
    except ServiceUnavailable as exc:
        raise service_error(exc)

    article.featured_image_alt = alt
    claude.record_usage(db, usage, "generate_alt", article.id)
    log_event(db, "seo.article.alt_generated", current_user, request,
              target_type="seo_article", target_id=article.id, detail=alt, commit=False)
    db.commit()
    return {"featured_image_alt": alt, "cost_inr": usage.cost_inr}


# --------------------------------------------------------------------------
# Publish
# --------------------------------------------------------------------------
def _markdown_to_html(md: str) -> str:
    try:
        import markdown as md_lib
        return md_lib.markdown(md, extensions=["extra", "sane_lists", "toc"])
    except ImportError:
        # The publish path must not fail on a missing optional renderer.
        return "\n".join(f"<p>{line}</p>" for line in md.split("\n\n") if line.strip())


def _faq_html(db: Session, article: SeoArticle) -> str:
    faqs = (db.query(SeoArticleFaq).filter(SeoArticleFaq.article_id == article.id)
            .order_by(SeoArticleFaq.position_in_article).all())
    if not faqs:
        return ""
    parts = ["<h2>Frequently asked questions</h2>"]
    for faq in faqs:
        parts.append(f"<h3>{faq.question}</h3>")
        parts.append(f"<p>{faq.answer or ''}</p>")
        if faq.source_url:
            parts.append(
                f'<p class="faq-source"><small>Asked on '
                f'<a href="{faq.source_url}" rel="nofollow noopener" target="_blank">'
                f'{faq.source_platform or "source"}</a></small></p>'
            )
    return "\n".join(parts)


@router.post("/{article_id}/publish", response_model=PublishResponse)
def publish_article(
    request: Request,
    article: SeoArticle = Depends(get_article),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_user),
):
    """Push to WordPress. Enforcement rules 1-6 all apply here, server-side."""
    # Rule 1 — country x vertical matrix.
    validate_country_vertical(
        db,
        enums.ArticleType(article.type),
        enums.Vertical(article.vertical),
        enums.Country(article.country) if article.country else None,
    )

    # Rules 2, 3, 4 — score, From Author, alt caption.
    blockers = _blocking_issues(article, article.current_score)
    if blockers:
        raise HTTPException(
            status_code=403,
            detail={"error": "publish_blocked", "blocking_issues": blockers},
        )

    # Rule 5 — AI detection. No provider is provisioned, so the gate is reported
    # as unenforced rather than silently passing.
    ai_detection_enforced = False

    if not article.slug:
        raise HTTPException(status_code=422, detail="The article has no slug.")

    # Rule 6 — duplicate slug, checked locally and against WordPress.
    duplicate = (db.query(SeoArticle)
                 .filter(SeoArticle.slug == article.slug, SeoArticle.id != article.id)
                 .first())
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={"error": "duplicate_slug",
                    "message": f"Slug '{article.slug}' is already used by article "
                               f"{duplicate.id}."},
        )

    go_live = check_go_live()
    client = wordpress.get_client()

    try:
        existing = client.find_post_by_slug(article.slug)
        if existing and existing.id != (article.wp_post_id or -1):
            raise HTTPException(
                status_code=409,
                detail={"error": "duplicate_slug",
                        "message": f"WordPress already has a post at slug "
                                   f"'{article.slug}' (post {existing.id})."},
            )

        media_id = None
        if article.featured_image_path:
            content, mime = storage.get_object(article.featured_image_path)
            media_id = client.upload_media(
                storage.filename_for(article.featured_image_path), content, mime,
                alt_text=article.featured_image_alt,
            )

        body_md = article.final_md or article.team_edit_md or ""
        html = _markdown_to_html(body_md) + "\n" + _faq_html(db, article)

        post = client.create_or_update_post(
            title=article.title or article.primary_keyword,
            content_html=html,
            slug=article.slug,
            status=go_live.wp_status,
            excerpt=article.meta_description,
            featured_media=media_id,
            post_id=article.wp_post_id,
            meta={
                "rank_math_title": article.meta_title or article.title,
                "rank_math_description": article.meta_description,
                "rank_math_focus_keyword": article.primary_keyword,
            },
        )
    except ServiceUnavailable as exc:
        raise service_error(exc)

    article.wp_post_id = post.id
    article.wp_published_url = post.link
    if go_live.approved:
        article.status = enums.ArticleStatus.published.value
        article.published_at = datetime.now(timezone.utc)

    log_event(db, "seo.article.published", current_user, request,
              target_type="seo_article", target_id=article.id,
              detail=f"wp_post={post.id} status={post.status}", commit=False)
    db.commit()

    message = (
        f"Published live at {post.link}." if go_live.approved
        else f"Sent to WordPress as a DRAFT (post {post.id}). {go_live.reason}"
    )
    if not ai_detection_enforced:
        message += (" Note: the AI-detection gate is not enforced — no "
                    "Originality.ai/GPTZero key is configured.")

    return PublishResponse(
        article_id=article.id,
        wp_post_id=post.id,
        wp_published_url=post.link,
        wp_status=post.status,
        go_live_approved=go_live.approved,
        message=message,
    )
