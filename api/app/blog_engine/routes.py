"""Block editor endpoints.

Mounted under /api/seo/articles/{id}/blocks and /api/seo/media. Behind
settings.BLOG_ENGINE_V2: with the flag off every route here answers 404, so
the dashboard behaves exactly as it does today.

Roles reuse the existing JWT roles, no new auth surface:
    viewer    read (GET blocks, revisions, preview)
    seo_lead  authoring (save, restore, upload); cannot publish
    admin     publish; may override a validator with a logged reason
"""
from __future__ import annotations

import io
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.blog_engine import convert, css, validate
from app.blog_engine.render import ArticleMeta, Author, RenderResult, render_article, render_page
from app.blog_engine.schema import BlockError, ImageAttrs, parse_blocks
from app.config import settings
from app.database import get_db
from app.models import User
from app.seo import enums as seo_enums
from app.audit import log_event
from app.seo.deps import admin_user, get_article, seo_user, service_error
from app.seo.models import SeoArticle, SeoArticleRevision
from app.seo.routes.articles import PUBLISH_MIN_SCORE, _blocking_issues, _replace_faqs
from app.seo.schemas import ManualFaq
from app.seo.services import ServiceUnavailable, indexnow, publisher

router = APIRouter(prefix="/api/seo", tags=["blog-engine"])

REVISIONS_KEPT = 50
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def engine_on() -> None:
    if not settings.BLOG_ENGINE_V2:
        raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ViolationOut(BaseModel):
    level: str
    rule: str
    message: str
    block_id: Optional[str] = None


class BlocksReport(BaseModel):
    word_count: int
    reading_minutes: int
    visuals: int
    block_types: List[str]
    effects: Dict[str, int]
    headings: List[List[Any]]
    violations: List[ViolationOut]
    blocking: int
    warnings: int


class BlocksResponse(BaseModel):
    article_id: uuid.UUID
    content_format: str
    blocks: List[Dict[str, Any]]
    title: Optional[str]
    slug: Optional[str]
    meta_title: Optional[str]
    meta_description: Optional[str]
    primary_keyword: str
    status: str
    revision_number: int
    can_edit: bool
    can_publish: bool
    report: Optional[BlocksReport] = None
    deferred_css_href: str
    author_name: str


class BlocksSave(BaseModel):
    blocks: List[Dict[str, Any]]
    title: Optional[str] = None
    slug: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    primary_keyword: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=200)


class BlocksSaveResponse(BaseModel):
    saved: bool
    revision_number: int
    changed: bool
    report: BlocksReport
    markdown_words: int


class PreviewResponse(BaseModel):
    html: str
    report: BlocksReport


class RevisionOut(BaseModel):
    revision_number: int
    created_at: Optional[datetime]
    created_by: Optional[str]
    note: Optional[str]
    block_count: int
    title: Optional[str]


class PublishBlocks(BaseModel):
    override_reason: Optional[str] = Field(default=None, min_length=10, max_length=500)


class PublishBlocksResponse(BaseModel):
    published: bool
    url: str
    page_path: str
    css_path: str
    indexnow: Optional[str]
    overridden: List[str]
    message: str


class MediaUploadResponse(BaseModel):
    src: str
    width: int
    height: int
    bytes: int
    format: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _author() -> Author:
    creds = [c.strip() for c in settings.BLOG_AUTHOR_CREDENTIALS.split(";") if c.strip()]
    return Author(
        name=settings.BLOG_AUTHOR_NAME, kind="Person",
        url=settings.BLOG_AUTHOR_LINKEDIN or None,
        job_title=settings.BLOG_AUTHOR_TITLE or None,
        bio=settings.BLOG_AUTHOR_BIO or None,
        photo=settings.BLOG_AUTHOR_PHOTO or None,
        same_as=[settings.BLOG_AUTHOR_LINKEDIN] if settings.BLOG_AUTHOR_LINKEDIN else [],
        credentials=creds,
    )


def _hero(article: SeoArticle) -> Optional[ImageAttrs]:
    """The featured image, as the site serves it (published/media/blog/<slug>.<ext>)."""
    if not article.featured_image_path or not article.featured_image_alt:
        return None
    ext = os.path.splitext(article.featured_image_path)[1].lower() or ".jpg"
    ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
    try:
        return ImageAttrs(src=f"/static/blog/{article.slug}{ext}", alt=article.featured_image_alt,
                          width=1200, height=630, layout="inset", priority=True)
    except ValueError:
        return None


def _meta(db: Session, article: SeoArticle) -> ArticleMeta:
    related = [
        (r.title, f"/blog/{r.slug}") for r in
        db.query(SeoArticle)
        .filter(SeoArticle.status == seo_enums.ArticleStatus.published.value,
                SeoArticle.id != article.id, SeoArticle.slug.isnot(None))
        .order_by(SeoArticle.published_at.desc().nullslast()).limit(3).all()
        if r.title
    ]
    pub = article.published_at or datetime.now(timezone.utc)
    upd = article.updated_at or pub
    return ArticleMeta(
        slug=article.slug or "untitled", title=article.title or article.primary_keyword,
        meta_title=article.meta_title, meta_description=article.meta_description or "",
        published_at=pub.astimezone(timezone.utc).isoformat(),
        updated_at=upd.astimezone(timezone.utc).isoformat(),
        author=_author(), hero=_hero(article),
        category=(article.vertical.value if hasattr(article.vertical, "value") else article.vertical),
        primary_keyword=article.primary_keyword, related=related,
        from_author_story=article.from_author_story,
        is_draft=article.status != seo_enums.ArticleStatus.published.value,
    )


def _report(blocks, meta: ArticleMeta, result: RenderResult) -> BlocksReport:
    violations = validate.validate_article(blocks, meta, result)
    blocking = validate.blocking(violations)
    return BlocksReport(
        word_count=result.word_count, reading_minutes=result.reading_minutes,
        visuals=result.visuals, block_types=result.block_types, effects=result.effects,
        headings=[[lvl, text] for lvl, text in result.headings],
        violations=[ViolationOut(level=v.level, rule=v.rule, message=v.message, block_id=v.block_id)
                    for v in violations],
        blocking=len(blocking), warnings=len(violations) - len(blocking),
    )


def _parse_or_422(raw: Any):
    try:
        return parse_blocks(raw)
    except BlockError as exc:
        m = re.match(r"^block (\S+): (.*)$", str(exc))
        raise HTTPException(status_code=422, detail={
            "error": "invalid_block", "block_id": m.group(1) if m else None,
            "message": m.group(2) if m else str(exc)})


def _can(user: User, roles: List[str]) -> bool:
    return user.role in roles


def _latest_revision(db: Session, article_id) -> int:
    return db.query(func.coalesce(func.max(SeoArticleRevision.revision_number), 0)) \
        .filter(SeoArticleRevision.article_id == article_id).scalar() or 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
class EngineStatus(BaseModel):
    enabled: bool
    author_name: str
    engine_version: str


@router.get("/blog-engine/status", response_model=EngineStatus)
def engine_status(current_user: User = Depends(get_current_user)):
    """Not gated by the flag: the UI needs to know whether to show the block
    editor at all. Reveals nothing beyond a boolean and public config."""
    from app.blog_engine.render import ENGINE_VERSION
    return EngineStatus(enabled=settings.BLOG_ENGINE_V2, author_name=settings.BLOG_AUTHOR_NAME,
                        engine_version=ENGINE_VERSION)


@router.get("/articles/{article_id}/blocks", response_model=BlocksResponse)
def get_blocks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
               article: SeoArticle = Depends(get_article)):
    engine_on()
    from app.models import ROLE_ADMIN, ROLE_SEO_LEAD
    raw = article.content_blocks or []
    report = None
    if raw:
        try:
            blocks = parse_blocks(raw)
            meta = _meta(db, article)
            report = _report(blocks, meta, render_article(blocks))
        except BlockError:
            report = None
    return BlocksResponse(
        article_id=article.id, content_format=article.content_format or "legacy",
        blocks=raw, title=article.title, slug=article.slug, meta_title=article.meta_title,
        meta_description=article.meta_description, primary_keyword=article.primary_keyword,
        status=article.status.value if hasattr(article.status, "value") else str(article.status),
        revision_number=_latest_revision(db, article.id),
        can_edit=_can(current_user, ROLE_SEO_LEAD), can_publish=_can(current_user, ROLE_ADMIN),
        report=report, deferred_css_href=f"/static/blog/engine/{css.deferred_filename()}",
        author_name=settings.BLOG_AUTHOR_NAME,
    )


@router.put("/articles/{article_id}/blocks", response_model=BlocksSaveResponse)
def save_blocks(payload: BlocksSave, request: Request, current_user: User = Depends(seo_user),
                db: Session = Depends(get_db), article: SeoArticle = Depends(get_article)):
    engine_on()
    blocks = _parse_or_422(payload.blocks)

    if payload.slug and payload.slug != article.slug:
        if article.status == seo_enums.ArticleStatus.published.value:
            raise HTTPException(status_code=409, detail={
                "error": "slug_locked",
                "message": "This article is published, so its URL cannot be changed."})
        if not SLUG.match(payload.slug):
            raise HTTPException(status_code=422, detail={
                "error": "bad_slug", "message": "slug must be lowercase words joined by single hyphens"})
        clash = db.query(SeoArticle).filter(SeoArticle.slug == payload.slug,
                                            SeoArticle.id != article.id).first()
        if clash:
            raise HTTPException(status_code=409, detail={"error": "slug_taken", "message": "That URL is already used."})
        article.slug = payload.slug

    for field in ("title", "meta_title", "meta_description", "primary_keyword"):
        value = getattr(payload, field)
        if value is not None:
            setattr(article, field, value)

    changed = (article.content_blocks or []) != payload.blocks
    article.content_blocks = payload.blocks
    article.content_format = "blocks"

    # Markdown projection, so the existing scorer, Rank Math checks and the
    # legacy JSON fallback keep working without knowing about blocks.
    projection = convert.blocks_to_markdown(blocks)
    article.team_edit_md = projection
    article.author_draft_md = article.author_draft_md or projection

    # FAQ blocks are the source of truth for the FAQ table on block articles.
    faq_items = [item for b in blocks if b.type == "faq" for item in b.content]
    if faq_items:
        _replace_faqs(db, article, [
            ManualFaq(question=i.question, answer="".join(r.text for r in i.answer) or " ")
            for i in faq_items])

    revision_number = _latest_revision(db, article.id)
    if changed:
        revision_number += 1
        db.add(SeoArticleRevision(
            article_id=article.id, revision_number=revision_number,
            content_blocks=payload.blocks,
            meta={"title": article.title, "slug": article.slug, "meta_title": article.meta_title,
                  "meta_description": article.meta_description,
                  "primary_keyword": article.primary_keyword},
            note=payload.note, created_by=current_user.id))
        # Keep the last REVISIONS_KEPT.
        stale = (db.query(SeoArticleRevision)
                 .filter(SeoArticleRevision.article_id == article.id)
                 .order_by(SeoArticleRevision.revision_number.desc())
                 .offset(REVISIONS_KEPT).all())
        for row in stale:
            db.delete(row)

    log_event(db, "seo.article.blocks_saved", current_user, request,
              target_type="seo_article", target_id=article.id,
              detail=f"{len(blocks)} blocks, revision {revision_number}", commit=False)
    db.commit()
    db.refresh(article)

    meta = _meta(db, article)
    result = render_article(blocks)
    return BlocksSaveResponse(saved=True, revision_number=revision_number, changed=changed,
                              report=_report(blocks, meta, result),
                              markdown_words=len(projection.split()))


@router.post("/articles/{article_id}/blocks/preview", response_model=PreviewResponse)
def preview_blocks(payload: BlocksSave, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db), article: SeoArticle = Depends(get_article)):
    """The exact page the publish step would write, for the editor's iframe.
    Renders the unsaved blocks from the payload; nothing is stored."""
    engine_on()
    blocks = _parse_or_422(payload.blocks)
    meta = _meta(db, article)
    for field in ("title", "meta_title", "meta_description", "primary_keyword"):
        value = getattr(payload, field)
        if value is not None:
            setattr(meta, field, value)
    meta.is_draft = False   # preview the live page, not the draft banner
    html, result = render_page(blocks, meta, analytics=False, preferred_sources=False, csp=False, inline_all_css=True)
    return PreviewResponse(html=html, report=_report(blocks, meta, result))


@router.get("/articles/{article_id}/blocks/revisions", response_model=List[RevisionOut])
def list_revisions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
                   article: SeoArticle = Depends(get_article)):
    engine_on()
    rows = (db.query(SeoArticleRevision, User.full_name)
            .outerjoin(User, User.id == SeoArticleRevision.created_by)
            .filter(SeoArticleRevision.article_id == article.id)
            .order_by(SeoArticleRevision.revision_number.desc()).all())
    return [RevisionOut(revision_number=r.revision_number, created_at=r.created_at, created_by=name,
                        note=r.note, block_count=len(r.content_blocks or []),
                        title=(r.meta or {}).get("title")) for r, name in rows]


@router.post("/articles/{article_id}/blocks/revisions/{number}/restore", response_model=BlocksSaveResponse)
def restore_revision(number: int, request: Request, current_user: User = Depends(seo_user),
                     db: Session = Depends(get_db), article: SeoArticle = Depends(get_article)):
    engine_on()
    row = (db.query(SeoArticleRevision)
           .filter(SeoArticleRevision.article_id == article.id,
                   SeoArticleRevision.revision_number == number).first())
    if row is None:
        raise HTTPException(status_code=404, detail="Revision not found")
    meta = row.meta or {}
    return save_blocks(
        BlocksSave(blocks=row.content_blocks, title=meta.get("title"),
                   meta_title=meta.get("meta_title"), meta_description=meta.get("meta_description"),
                   primary_keyword=meta.get("primary_keyword"),
                   note=f"restored revision {number}"),
        request=request, current_user=current_user, db=db, article=article)


@router.post("/articles/{article_id}/blocks/publish", response_model=PublishBlocksResponse)
def publish_blocks(payload: PublishBlocks, request: Request, current_user: User = Depends(admin_user),
                   db: Session = Depends(get_db), article: SeoArticle = Depends(get_article)):
    """Render and publish a block article.

    The existing gates are unchanged: score >= PUBLISH_MIN_SCORE and no
    blocking issues from the legacy checks (featured image, alt, story).
    Block validators that block can be overridden by an admin with a reason,
    which is written to the audit log. The score gate cannot be overridden.
    """
    engine_on()
    if article.content_format != "blocks" or not article.content_blocks:
        raise HTTPException(status_code=409, detail={
            "error": "not_blocks", "message": "This article is not authored in the block editor."})
    if not article.slug:
        raise HTTPException(status_code=409, detail={"error": "no_slug", "message": "The article needs a URL slug."})

    blocks = _parse_or_422(article.content_blocks)
    score = article.current_score or 0
    if score < PUBLISH_MIN_SCORE:
        raise HTTPException(status_code=409, detail={
            "error": "score_below_threshold",
            "message": f"Score is {score}/100; publishing requires {PUBLISH_MIN_SCORE}. This gate cannot be overridden."})
    legacy_blockers = _blocking_issues(article, score)
    if legacy_blockers:
        raise HTTPException(status_code=409, detail={
            "error": "blocking_issues", "issues": legacy_blockers,
            "message": "; ".join(legacy_blockers)})

    if not article.published_at:
        article.published_at = datetime.now(timezone.utc)
    meta = _meta(db, article)
    meta.is_draft = False
    result = render_article(blocks)
    violations = validate.validate_article(blocks, meta, result)
    blocking = validate.blocking(violations)
    overridden: List[str] = []
    if blocking:
        if not payload.override_reason:
            raise HTTPException(status_code=409, detail={
                "error": "validators_blocking",
                "issues": [str(v) for v in blocking],
                "message": f"{len(blocking)} validator(s) block publishing. An admin can override with a reason."})
        overridden = [str(v) for v in blocking]
        log_event(db, "seo.article.validator_override", current_user, request,
                  target_type="seo_article", target_id=article.id,
                  detail=f"reason: {payload.override_reason} | overrode: {'; '.join(overridden)}",
                  commit=False)

    html, result = render_page(blocks, meta)
    try:
        css_path = publisher.publish_engine_css()
        page_path = publisher.publish_page(article.slug, html)
        faqs = [{"question": q, "answer": a} for q, a in result.faqs]
        published = publisher.publish(
            article_id=str(article.id), slug=article.slug,
            title=article.title or article.primary_keyword,
            html=result.body_html, meta_title=article.meta_title,
            meta_description=article.meta_description, primary_keyword=article.primary_keyword,
            faqs=faqs, featured_image_path=article.featured_image_path,
            featured_image_alt=article.featured_image_alt, author=settings.BLOG_AUTHOR_NAME,
            from_author_story=article.from_author_story, published_at=article.published_at,
            is_draft=False, extra={"content_format": "blocks", "engine_version": "1.0.0"})
    except ServiceUnavailable as exc:
        raise service_error(exc)

    article.status = seo_enums.ArticleStatus.published.value
    article.wp_published_url = published.url
    log_event(db, "seo.article.published", current_user, request,
              target_type="seo_article", target_id=article.id,
              detail=f"blocks: {page_path} ({len(html.encode('utf-8'))} bytes)", commit=False)
    db.commit()

    note = None
    if indexnow.configured():
        submission = indexnow.submit_one(published.url)
        note = "submitted" if submission.ok else f"not submitted: {submission.detail}"

    return PublishBlocksResponse(
        published=True, url=published.url, page_path=page_path, css_path=css_path,
        indexnow=note, overridden=overridden,
        message=f"Published live at {published.url}." + (f" IndexNow {note}." if note else ""))


# ---------------------------------------------------------------------------
# Media upload (the Phase 3 pipeline's first slice: enough for an image block)
# ---------------------------------------------------------------------------
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.post("/media/upload", response_model=MediaUploadResponse)
async def upload_media(file: UploadFile = File(...), current_user: User = Depends(seo_user)):
    """Store an image for use in a block. MIME is sniffed by decoding, not
    trusted from the header; EXIF is stripped by re-encoding; SVG is rejected."""
    engine_on()
    from PIL import Image, ImageOps

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image is over 10 MB.")
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except Exception:
        raise HTTPException(status_code=415, detail="Not an image we can read (JPEG, PNG or WebP).")
    fmt = (img.format or "").upper()
    if fmt not in ("JPEG", "PNG", "WEBP"):
        raise HTTPException(status_code=415, detail=f"{fmt or 'unknown'} is not accepted; use JPEG, PNG or WebP.")

    # Honour orientation, then drop every other EXIF field by re-encoding.
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if fmt == "PNG" and has_alpha:
        out_fmt, ext, mode = "PNG", ".png", "RGBA"
    else:
        out_fmt, ext, mode = "JPEG", ".jpg", "RGB"
    img = img.convert(mode)
    if img.width > 2400:
        img = img.resize((2400, round(img.height * 2400 / img.width)), Image.LANCZOS)

    buf = io.BytesIO()
    if out_fmt == "JPEG":
        img.save(buf, "JPEG", quality=84, optimize=True, progressive=True)
    else:
        img.save(buf, "PNG", optimize=True)
    data = buf.getvalue()

    stamp = datetime.now(timezone.utc).strftime("%Y%m")
    name = f"{uuid.uuid4().hex[:12]}{ext}"
    directory = os.path.join(settings.SITE_MEDIA_DIR, "uploads", stamp)
    try:
        os.makedirs(directory, exist_ok=True)
        publisher._write_atomic(os.path.join(directory, name), data)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Could not store the image: {exc}")

    return MediaUploadResponse(src=f"/static/blog/uploads/{stamp}/{name}", width=img.width,
                               height=img.height, bytes=len(data), format=out_fmt.lower())
