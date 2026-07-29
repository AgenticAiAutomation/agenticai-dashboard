"""Dashboard home: KPI cards, target projections, charts, scoreboard, activity."""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.models import AuditEvent, ROLE_SEO_LEAD, User
from app.seo import enums
from app.seo.deps import admin_user, seo_user
from app.seo.golive import check_go_live
from app.seo.models import (
    SeoArticle, SeoAudit, SeoBacklink, SeoGscDaily, SeoRecommendation,
)
from app.seo.schemas import (
    ActivityEntry, DashboardHomeResponse, KpiCard, ProjectionRequest,
    RecommendationResponse, SeriesPoint, SiteHealthResponse, TargetProjection,
    TeamMemberStat,
)
from app.seo.services.projection import daily_deltas, project_target_date

router = APIRouter(prefix="/api/seo", tags=["seo-dashboard"])

# Targets from the spec's definition of done.
WEEKLY_PUBLISH_TARGET = 6
WEEKLY_BACKLINK_TARGET = 3
DR_TARGET = 25
ARTICLE_TARGET = 60
ARTICLE_TARGET_DAYS = 90
TOP10_TARGET = 5

# The enum column sorts alphabetically, which would put 'low' first — order by
# actual urgency instead.
PRIORITY_ORDER = case(
    (SeoRecommendation.priority == enums.RecommendationPriority.high.value, 0),
    (SeoRecommendation.priority == enums.RecommendationPriority.medium.value, 1),
    else_=2,
)


def _week_start(today: Optional[date] = None) -> date:
    today = today or date.today()
    return today - timedelta(days=today.weekday())


def _direction(delta: Optional[float]) -> str:
    if delta is None or abs(delta) < 1e-9:
        return "flat"
    return "up" if delta > 0 else "down"


def _domain_rating_series(db: Session, days: int = 28) -> List[tuple]:
    """DR is entered manually (Ubersuggest lifetime tier has no API).

    Stored as daily audit rows carrying a domain_rating key.
    """
    since = date.today() - timedelta(days=days)
    rows = (db.query(SeoAudit.audit_date, SeoAudit.results_json)
            .filter(SeoAudit.audit_date >= since)
            .order_by(SeoAudit.audit_date.asc()).all())
    series = []
    for audit_date, results in rows:
        if isinstance(results, dict) and results.get("domain_rating") is not None:
            try:
                series.append((audit_date, float(results["domain_rating"])))
            except (TypeError, ValueError):
                continue
    return series


# --------------------------------------------------------------------------
# Projection helper (spec: /api/seo/helpers/projected-target-date)
# --------------------------------------------------------------------------
@router.post("/helpers/projected-target-date", response_model=TargetProjection)
def projected_target_date(
    payload: ProjectionRequest,
    current_user: User = Depends(seo_user),
):
    return project_target_date(
        label=payload.label,
        current_value=payload.current_value,
        target_value=payload.target_value,
        historical_daily_progress=payload.historical_daily_progress,
        amber_after_weeks=payload.amber_after_weeks,
        red_after_weeks=payload.red_after_weeks,
        deadline=payload.deadline,
    )


# --------------------------------------------------------------------------
# Dashboard home
# --------------------------------------------------------------------------
@router.get("/dashboard/home", response_model=DashboardHomeResponse)
def dashboard_home(
    db: Session = Depends(get_db),
    current_user: User = Depends(seo_user),
):
    today = date.today()
    week_start = _week_start(today)
    previous_week_start = week_start - timedelta(days=7)

    published = SeoArticle.status == enums.ArticleStatus.published.value

    # --- KPI 1: articles published this week ---
    this_week = (db.query(func.count(SeoArticle.id))
                 .filter(published, SeoArticle.published_at >= week_start).scalar()) or 0
    last_week = (db.query(func.count(SeoArticle.id))
                 .filter(published,
                         SeoArticle.published_at >= previous_week_start,
                         SeoArticle.published_at < week_start).scalar()) or 0

    # --- KPI 2: domain rating ---
    dr_series = _domain_rating_series(db, days=28)
    current_dr = dr_series[-1][1] if dr_series else 0.0
    dr_7d_ago = next(
        (value for day, value in reversed(dr_series) if day <= today - timedelta(days=7)),
        dr_series[0][1] if dr_series else 0.0,
    )

    # --- KPI 3: organic clicks, last 7 days vs prior 7 ---
    clicks_7 = _gsc_sum(db, today - timedelta(days=7), today)
    clicks_prior = _gsc_sum(db, today - timedelta(days=14), today - timedelta(days=7))

    # --- KPI 4: backlinks this week ---
    backlinks_week = (db.query(func.count(SeoBacklink.id))
                      .filter(SeoBacklink.discovered_at >= week_start).scalar()) or 0
    backlinks_total = db.query(func.count(SeoBacklink.id)).scalar() or 0

    kpis = [
        KpiCard(
            key="articles_this_week", label="Articles published this week",
            value=this_week, target=WEEKLY_PUBLISH_TARGET,
            percent_of_target=round(this_week / WEEKLY_PUBLISH_TARGET * 100, 1),
            delta=this_week - last_week, delta_label="vs last week",
            direction=_direction(this_week - last_week),
            healthy=this_week >= WEEKLY_PUBLISH_TARGET,
        ),
        KpiCard(
            key="domain_rating", label="Domain rating",
            value=current_dr, target=DR_TARGET,
            delta=round(current_dr - dr_7d_ago, 1), delta_label="vs 7 days ago",
            direction=_direction(current_dr - dr_7d_ago),
            healthy=current_dr >= dr_7d_ago,
        ),
        KpiCard(
            key="organic_clicks_7d", label="Organic clicks, last 7 days",
            value=clicks_7,
            delta=clicks_7 - clicks_prior, delta_label="vs prior week",
            direction=_direction(clicks_7 - clicks_prior),
            healthy=clicks_7 >= clicks_prior,
        ),
        KpiCard(
            key="backlinks_this_week", label="Backlinks earned this week",
            value=backlinks_week, target=WEEKLY_BACKLINK_TARGET,
            percent_of_target=round(backlinks_week / WEEKLY_BACKLINK_TARGET * 100, 1),
            delta=backlinks_total, delta_label="running total",
            direction=_direction(backlinks_week),
            healthy=backlinks_week >= WEEKLY_BACKLINK_TARGET,
        ),
    ]

    projections = [
        _dr_projection(dr_series, current_dr),
        _article_projection(db, today),
        _top10_projection(db, today),
    ]

    velocity, weekly_avg = _publish_velocity(db, today, days=30)
    gsc_series = _gsc_series(db, today, days=90)

    recommendations = (db.query(SeoRecommendation)
                       .filter(SeoRecommendation.resolved_at.is_(None))
                       .order_by(PRIORITY_ORDER, SeoRecommendation.created_at.desc())
                       .limit(3).all())

    go_live = check_go_live()

    return DashboardHomeResponse(
        kpis=kpis,
        projections=projections,
        publish_velocity=velocity,
        publish_velocity_weekly_avg=weekly_avg,
        gsc_series=gsc_series,
        team=_team_stats(db, week_start),
        recommendations=[RecommendationResponse.model_validate(r, from_attributes=True)
                         for r in recommendations],
        activity=_activity(db, limit=20),
        go_live_approved=go_live.approved,
        go_live_message=go_live.reason,
    )


def _gsc_sum(db: Session, start: date, end: date) -> int:
    return int((db.query(func.coalesce(func.sum(SeoGscDaily.clicks), 0))
                .filter(SeoGscDaily.date >= start, SeoGscDaily.date < end)
                .scalar()) or 0)


def _publish_velocity(db: Session, today: date, days: int = 30):
    since = today - timedelta(days=days - 1)
    rows = (db.query(func.date(SeoArticle.published_at), func.count(SeoArticle.id))
            .filter(SeoArticle.status == enums.ArticleStatus.published.value)
            .filter(SeoArticle.published_at >= since)
            .group_by(func.date(SeoArticle.published_at)).all())
    counts = {row[0]: int(row[1]) for row in rows}

    series = [SeriesPoint(date=since + timedelta(days=offset),
                          value=float(counts.get(since + timedelta(days=offset), 0)))
              for offset in range(days)]
    weekly_avg = round(sum(p.value for p in series) / days * 7, 2)
    return series, weekly_avg


def _gsc_series(db: Session, today: date, days: int = 90) -> List[SeriesPoint]:
    since = today - timedelta(days=days - 1)
    rows = (db.query(SeoGscDaily.date,
                     func.sum(SeoGscDaily.clicks),
                     func.sum(SeoGscDaily.impressions))
            .filter(SeoGscDaily.date >= since)
            .group_by(SeoGscDaily.date).order_by(SeoGscDaily.date).all())
    return [SeriesPoint(date=row[0], value=float(row[1] or 0),
                        secondary=float(row[2] or 0)) for row in rows]


def _dr_projection(dr_series: List[tuple], current_dr: float) -> TargetProjection:
    values = [value for _, value in dr_series]
    return project_target_date(
        label=f"DR {DR_TARGET} target",
        current_value=current_dr,
        target_value=DR_TARGET,
        historical_daily_progress=daily_deltas(values) if len(values) > 1 else [],
    )


def _article_projection(db: Session, today: date) -> TargetProjection:
    published_total = (db.query(func.count(SeoArticle.id))
                       .filter(SeoArticle.status == enums.ArticleStatus.published.value)
                       .scalar()) or 0

    # Last 14 days of per-day publish counts, zero-filled.
    since = today - timedelta(days=13)
    rows = (db.query(func.date(SeoArticle.published_at), func.count(SeoArticle.id))
            .filter(SeoArticle.status == enums.ArticleStatus.published.value)
            .filter(SeoArticle.published_at >= since)
            .group_by(func.date(SeoArticle.published_at)).all())
    counts = {row[0]: float(row[1]) for row in rows}
    daily = [counts.get(since + timedelta(days=offset), 0.0) for offset in range(14)]

    first_published = (db.query(func.min(SeoArticle.published_at))
                       .filter(SeoArticle.status == enums.ArticleStatus.published.value)
                       .scalar())
    deadline = ((first_published.date() if first_published else today)
                + timedelta(days=ARTICLE_TARGET_DAYS))

    return project_target_date(
        label=f"{ARTICLE_TARGET} published articles ({ARTICLE_TARGET_DAYS} days)",
        current_value=published_total,
        target_value=ARTICLE_TARGET,
        historical_daily_progress=daily,
        deadline=deadline,
    )


def _top10_projection(db: Session, today: date) -> TargetProjection:
    """Count distinct pages sitting in the top 10, day by day, over the last 14."""
    since = today - timedelta(days=13)
    rows = (db.query(SeoGscDaily.date,
                     func.count(func.distinct(SeoGscDaily.page_url)))
            .filter(SeoGscDaily.date >= since, SeoGscDaily.avg_position <= 10)
            .group_by(SeoGscDaily.date).order_by(SeoGscDaily.date).all())
    counts = [float(row[1]) for row in rows]
    current = counts[-1] if counts else 0.0

    return project_target_date(
        label=f"First {TOP10_TARGET} top-10 rankings",
        current_value=current,
        target_value=TOP10_TARGET,
        historical_daily_progress=daily_deltas(counts) if len(counts) > 1 else [],
    )


def _team_stats(db: Session, week_start: date) -> List[TeamMemberStat]:
    members = (db.query(User)
               .filter(User.role.in_(ROLE_SEO_LEAD), User.is_active.is_(True))
               .order_by(User.full_name).all())
    stats = []
    for user in members:
        this_week = (db.query(func.count(SeoArticle.id))
                     .filter(SeoArticle.assigned_to == user.id,
                             SeoArticle.updated_at >= week_start).scalar()) or 0
        published = (db.query(func.count(SeoArticle.id))
                     .filter(SeoArticle.assigned_to == user.id,
                             SeoArticle.status == enums.ArticleStatus.published.value)
                     .scalar()) or 0
        avg_score = (db.query(func.avg(SeoArticle.current_score))
                     .filter(SeoArticle.assigned_to == user.id,
                             SeoArticle.current_score.isnot(None)).scalar())
        stats.append(TeamMemberStat(
            user_id=user.id, full_name=user.full_name, email=user.email, role=user.role,
            articles_this_week=this_week, articles_published=published,
            avg_score=round(float(avg_score), 1) if avg_score is not None else None,
            backlinks_earned=0,
            streak_days=_streak_days(db, user.id),
            last_login_at=user.last_login_at,
        ))
    return stats


def _streak_days(db: Session, user_id: int, max_days: int = 60) -> int:
    """Consecutive days ending today on which the user did something auditable."""
    since = date.today() - timedelta(days=max_days)
    rows = (db.query(func.distinct(func.date(AuditEvent.created_at)))
            .filter(AuditEvent.user_id == user_id, AuditEvent.created_at >= since).all())
    active = {row[0] for row in rows}
    streak, cursor = 0, date.today()
    while cursor in active:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _activity(db: Session, limit: int = 20) -> List[ActivityEntry]:
    rows = (db.query(AuditEvent).order_by(AuditEvent.created_at.desc())
            .limit(limit).all())
    return [ActivityEntry(
        id=row.id, user_email=row.user_email, action=row.action,
        target_type=row.target_type, target_id=row.target_id, detail=row.detail,
        created_at=row.created_at,
    ) for row in rows]


# --------------------------------------------------------------------------
# Team stats + site health (spec endpoints)
# --------------------------------------------------------------------------
@router.get("/dashboard/team-stats", response_model=List[TeamMemberStat])
def team_stats(db: Session = Depends(get_db), current_user: User = Depends(seo_user)):
    return _team_stats(db, _week_start())


@router.get("/dashboard/site-health", response_model=SiteHealthResponse)
def site_health(db: Session = Depends(get_db), current_user: User = Depends(seo_user)):
    latest = (db.query(SeoAudit).order_by(SeoAudit.audit_date.desc(),
                                          SeoAudit.created_at.desc()).first())
    open_counts = dict(
        db.query(SeoRecommendation.priority, func.count(SeoRecommendation.id))
        .filter(SeoRecommendation.resolved_at.is_(None))
        .group_by(SeoRecommendation.priority).all()
    )
    since = date.today() - timedelta(days=28)
    avg_position = (db.query(func.avg(SeoGscDaily.avg_position))
                    .filter(SeoGscDaily.date >= since).scalar())
    indexed = (db.query(func.count(func.distinct(SeoGscDaily.page_url)))
               .filter(SeoGscDaily.date >= since).scalar())

    return SiteHealthResponse(
        latest_audit=latest,
        open_recommendations={str(k): int(v) for k, v in open_counts.items()},
        published_articles=(db.query(func.count(SeoArticle.id))
                            .filter(SeoArticle.status == enums.ArticleStatus.published.value)
                            .scalar()) or 0,
        indexed_pages=int(indexed) if indexed else 0,
        avg_position=round(float(avg_position), 2) if avg_position is not None else None,
        total_backlinks=db.query(func.count(SeoBacklink.id)).scalar() or 0,
        verified_backlinks=(db.query(func.count(SeoBacklink.id))
                            .filter(SeoBacklink.status ==
                                    enums.BacklinkStatus.verified.value).scalar()) or 0,
        go_live_approved=check_go_live().approved,
    )


@router.post("/metrics/domain-rating")
def record_domain_rating(
    request: Request,
    domain_rating: float = Body(..., embed=True, ge=0, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_user),
):
    """Manual DR entry — Ubersuggest has no API on the lifetime tier."""
    today = date.today()
    existing = (db.query(SeoAudit)
                .filter(SeoAudit.audit_date == today,
                        SeoAudit.audit_type == enums.AuditType.daily.value).first())
    if existing:
        results = dict(existing.results_json or {})
        results["domain_rating"] = domain_rating
        results["domain_rating_source"] = "manual"
        existing.results_json = results
    else:
        db.add(SeoAudit(
            audit_type=enums.AuditType.daily.value, audit_date=today,
            results_json={"domain_rating": domain_rating,
                          "domain_rating_source": "manual"},
        ))
    log_event(db, "seo.metrics.domain_rating", current_user, request,
              detail=str(domain_rating), commit=False)
    db.commit()
    return {"date": today.isoformat(), "domain_rating": domain_rating}
