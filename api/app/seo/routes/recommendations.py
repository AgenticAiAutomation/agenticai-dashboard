"""Prioritised audit output, audit history, and the backlink tracker."""
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.models import User
from app.seo import enums
from app.seo.deps import seo_user
from app.seo.models import SeoAudit, SeoBacklink, SeoRecommendation
from app.seo.schemas import AuditResponse, RecommendationResponse

router = APIRouter(prefix="/api/seo", tags=["seo-recommendations"])

PRIORITY_ORDER = case(
    (SeoRecommendation.priority == enums.RecommendationPriority.high.value, 0),
    (SeoRecommendation.priority == enums.RecommendationPriority.medium.value, 1),
    else_=2,
)


@router.get("/recommendations", response_model=List[RecommendationResponse])
def list_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
    priority: Optional[enums.RecommendationPriority] = None,
    category: Optional[enums.RecommendationCategory] = None,
    resolved: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
):
    query = db.query(SeoRecommendation)
    if priority is not None:
        query = query.filter(SeoRecommendation.priority == priority.value)
    if category is not None:
        query = query.filter(SeoRecommendation.category == category.value)
    query = query.filter(SeoRecommendation.resolved_at.isnot(None) if resolved
                         else SeoRecommendation.resolved_at.is_(None))
    return (query.order_by(PRIORITY_ORDER, SeoRecommendation.created_at.desc())
            .limit(limit).all())


@router.post("/recommendations/{recommendation_id}/resolve",
             response_model=RecommendationResponse)
def resolve_recommendation(
    recommendation_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    recommendation = db.query(SeoRecommendation).filter(
        SeoRecommendation.id == recommendation_id).first()
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    recommendation.resolved_at = datetime.now(timezone.utc)
    log_event(db, "seo.recommendation.resolved", current_user, request,
              target_type="seo_recommendation", target_id=recommendation_id,
              detail=recommendation.title, commit=False)
    db.commit()
    db.refresh(recommendation)
    return recommendation


@router.get("/audits", response_model=List[AuditResponse])
def list_audits(
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
    audit_type: Optional[enums.AuditType] = None,
    limit: int = Query(default=30, le=200),
):
    query = db.query(SeoAudit)
    if audit_type is not None:
        query = query.filter(SeoAudit.audit_type == audit_type.value)
    return (query.order_by(SeoAudit.audit_date.desc(), SeoAudit.created_at.desc())
            .limit(limit).all())


# --------------------------------------------------------------------------
# Backlinks
# --------------------------------------------------------------------------
@router.get("/backlinks")
def list_backlinks(
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
    status: Optional[enums.BacklinkStatus] = None,
    limit: int = Query(default=200, le=1000),
):
    query = db.query(SeoBacklink)
    if status is not None:
        query = query.filter(SeoBacklink.status == status.value)
    rows = query.order_by(SeoBacklink.discovered_at.desc()).limit(limit).all()
    return [
        {
            "id": str(row.id), "source_url": row.source_url,
            "source_domain": row.source_domain, "target_url": row.target_url,
            "anchor_text": row.anchor_text, "referring_dr": row.referring_dr,
            "status": row.status,
            "discovered_at": row.discovered_at.isoformat() if row.discovered_at else None,
        }
        for row in rows
    ]


@router.post("/backlinks", status_code=201)
def create_backlink(
    request: Request,
    source_url: str = Body(...),
    target_url: str = Body(...),
    anchor_text: Optional[str] = Body(default=None),
    referring_dr: Optional[int] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    """Manual entry. The Ubersuggest scrape and HARO parser feed the same table."""
    existing = (db.query(SeoBacklink)
                .filter(SeoBacklink.source_url == source_url,
                        SeoBacklink.target_url == target_url).first())
    if existing:
        raise HTTPException(status_code=409,
                            detail="That source/target pair is already tracked.")

    backlink = SeoBacklink(
        source_url=source_url,
        source_domain=urlparse(source_url).netloc or None,
        target_url=target_url,
        anchor_text=anchor_text,
        referring_dr=referring_dr,
        status=enums.BacklinkStatus.new.value,
    )
    db.add(backlink)
    log_event(db, "seo.backlink.added", current_user, request,
              target_type="seo_backlink", detail=source_url, commit=False)
    db.commit()
    db.refresh(backlink)
    return {"id": str(backlink.id), "source_domain": backlink.source_domain,
            "status": backlink.status}
