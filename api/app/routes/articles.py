from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import Article, User
from app.schemas import ArticleCreate, ArticleUpdate, ArticleResponse
from app.auth import get_current_user, require_role

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=List[ArticleResponse])
def get_articles(
    status: Optional[str] = Query(None),
    track: Optional[str] = Query(None),
    assignee: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Article)

    if status:
        query = query.filter(Article.status == status)
    if track:
        query = query.filter(Article.track == track)
    if assignee:
        query = query.filter(Article.assignee_id == assignee)

    articles = query.all()
    return articles


@router.post("", response_model=ArticleResponse)
def create_article(
    article: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["owner", "seo"]))
):
    # Check slug uniqueness
    existing = db.query(Article).filter(Article.slug == article.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Article with this slug already exists")

    db_article = Article(**article.dict())
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    return db_article


@router.patch("/{article_id}", response_model=ArticleResponse)
def update_article(
    article_id: int,
    update: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Writers can only update their own assigned articles
    if current_user.role == "writer" and article.assignee_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only update your own assigned articles")

    # Update only provided fields
    for field, value in update.dict(exclude_unset=True).items():
        setattr(article, field, value)

    db.commit()
    db.refresh(article)
    return article
