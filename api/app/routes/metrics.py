from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import ArticleMetric, Article, Keyword, Task, User
from app.schemas import MetricCreate, MetricResponse, DashboardSummary
from app.auth import get_current_user, require_role

router = APIRouter(tags=["metrics"])


@router.get("/metrics/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    total_keywords = db.query(Keyword).count()
    total_articles = db.query(Article).count()
    published_articles = db.query(Article).filter(Article.status == 'published').count()
    tasks_open = db.query(Task).filter(Task.status == 'open').count()
    tasks_done = db.query(Task).filter(Task.status == 'done').count()

    # Phase progress (count tasks by phase)
    phase_counts = db.query(Task.phase, func.count(Task.id)).group_by(Task.phase).all()
    phase_progress = {phase: count for phase, count in phase_counts}

    return {
        "total_keywords": total_keywords,
        "total_articles": total_articles,
        "published_articles": published_articles,
        "tasks_open": tasks_open,
        "tasks_done": tasks_done,
        "phase_progress": phase_progress
    }


@router.post("/metrics", response_model=MetricResponse)
def create_metric(
    metric: MetricCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["owner", "seo"]))
):
    # Verify article exists
    article = db.query(Article).filter(Article.id == metric.article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    db_metric = ArticleMetric(**metric.dict())
    db.add(db_metric)
    db.commit()
    db.refresh(db_metric)
    return db_metric
