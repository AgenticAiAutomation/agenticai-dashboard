from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import Keyword, User
from app.schemas import KeywordCreate, KeywordUpdate, KeywordResponse
from app.auth import get_current_user, require_role

router = APIRouter(prefix="/keywords", tags=["keywords"])


@router.get("", response_model=List[KeywordResponse])
def get_keywords(
    pillar: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    assignee: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Keyword)

    if pillar:
        query = query.filter(Keyword.pillar == pillar)
    if status:
        query = query.filter(Keyword.status == status)
    if assignee:
        query = query.filter(Keyword.assignee_id == assignee)

    keywords = query.all()
    return keywords


@router.patch("/{keyword_id}", response_model=KeywordResponse)
def update_keyword(
    keyword_id: int,
    update: KeywordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["owner", "seo"]))
):
    keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    # Update only provided fields
    for field, value in update.dict(exclude_unset=True).items():
        setattr(keyword, field, value)

    db.commit()
    db.refresh(keyword)
    return keyword


@router.post("/import")
def import_keywords_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["owner", "seo"]))
):
    # Placeholder for CSV import - v1 will do manual import via seed script
    return {"message": "CSV import endpoint - to be implemented"}
