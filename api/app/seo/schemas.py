"""Pydantic schemas for the SEO Operations module."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.seo import enums


# --------------------------------------------------------------------------
# Articles
# --------------------------------------------------------------------------
class ArticleGenerateRequest(BaseModel):
    """POST /api/seo/articles/generate — author-triggered draft generation."""
    type: enums.ArticleType
    vertical: enums.Vertical
    country: Optional[enums.Country] = None
    primary_keyword: str = Field(min_length=2)
    title_hint: Optional[str] = None
    source_platform: Optional[enums.SourcePlatform] = None
    source_url: Optional[str] = None
    captured_question: Optional[str] = None
    keyword_difficulty: Optional[int] = None
    monthly_search_volume: Optional[int] = None
    buyer_intent: Optional[enums.BuyerIntent] = None
    ubersuggest_raw: Optional[str] = None
    competitor_urls: Optional[List[str]] = None
    assigned_to: Optional[int] = None
    # Set when the draft originated from a captured pull request.
    pull_request_id: Optional[UUID] = None


class ArticleTeamEdit(BaseModel):
    team_edit_md: str
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    slug: Optional[str] = None


class FromAuthorStoryRequest(BaseModel):
    from_author_story: str = Field(min_length=1)


class ValidateCountryRequest(BaseModel):
    """Optional override so the UI can test a pair before saving it."""
    vertical: Optional[enums.Vertical] = None
    country: Optional[enums.Country] = None
    type: Optional[enums.ArticleType] = None


class ArticleResponse(BaseModel):
    id: UUID
    type: enums.ArticleType
    status: enums.ArticleStatus
    title: Optional[str]
    slug: Optional[str]
    vertical: enums.Vertical
    country: Optional[enums.Country]
    primary_keyword: str
    keyword_difficulty: Optional[int]
    monthly_search_volume: Optional[int]
    buyer_intent: Optional[enums.BuyerIntent]
    assigned_to: Optional[int]
    current_score: Optional[int]
    featured_image_path: Optional[str]
    featured_image_alt: Optional[str]
    meta_title: Optional[str]
    meta_description: Optional[str]
    wp_post_id: Optional[int]
    wp_published_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


class ArticleDetailResponse(ArticleResponse):
    author_draft_md: Optional[str]
    team_edit_md: Optional[str]
    final_md: Optional[str]
    from_author_story: Optional[str]
    ubersuggest_raw: Optional[str]
    competitor_urls: Optional[Any]
    sources: List["ArticleSourceResponse"] = []
    faqs: List["ArticleFaqResponse"] = []


class ArticleSourceResponse(BaseModel):
    id: UUID
    source_url: Optional[str]
    source_platform: Optional[enums.SourcePlatform]
    question_or_prompt: Optional[str]
    captured_at: Optional[datetime]

    class Config:
        from_attributes = True


class ArticleFaqResponse(BaseModel):
    id: UUID
    question: str
    answer: Optional[str]
    source_url: Optional[str]
    source_platform: Optional[enums.SourcePlatform]
    position_in_article: Optional[int]

    class Config:
        from_attributes = True


class PublishResponse(BaseModel):
    article_id: UUID
    wp_post_id: Optional[int]
    wp_published_url: Optional[str]
    wp_status: str
    go_live_approved: bool
    message: str


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
class ScoreComment(BaseModel):
    line_number: int
    current_text: str
    suggested_fix: str
    impact_points: float
    parameter: Optional[str] = None


class ScoreParameter(BaseModel):
    key: str
    label: str
    group: str
    points_available: float
    points_earned: float
    detail: Optional[str] = None
    implemented: bool = True


class ScoreResponse(BaseModel):
    article_id: UUID
    version_number: int
    total_score: int
    max_score: int
    groups: Dict[str, Dict[str, float]]
    parameters: List[ScoreParameter]
    comments: List[ScoreComment]
    scored_at: datetime
    blocking_issues: List[str] = []


# --------------------------------------------------------------------------
# Pull requests
# --------------------------------------------------------------------------
class PullRequestCreate(BaseModel):
    source_platform: enums.PullRequestPlatform
    source_url: Optional[str] = None
    question_captured: str = Field(min_length=5)
    suggested_vertical: Optional[enums.Vertical] = None
    suggested_country: Optional[enums.Country] = None


class PullRequestResponse(BaseModel):
    id: UUID
    source_platform: enums.PullRequestPlatform
    source_url: Optional[str]
    question_captured: str
    suggested_vertical: Optional[enums.Vertical]
    suggested_country: Optional[enums.Country]
    captured_at: Optional[datetime]
    converted_to_article_id: Optional[UUID]

    class Config:
        from_attributes = True


class PullRequestConvert(BaseModel):
    type: enums.ArticleType
    vertical: enums.Vertical
    country: Optional[enums.Country] = None
    primary_keyword: str
    assigned_to: Optional[int] = None
    generate_draft: bool = False


# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------
class CalendarRowResponse(BaseModel):
    id: UUID
    week_number: Optional[int]
    article_type: enums.ArticleType
    vertical: enums.Vertical
    country: Optional[enums.Country]
    title: Optional[str]
    primary_keyword: Optional[str]
    kd: Optional[int]
    volume: Optional[int]
    buyer_intent: Optional[enums.BuyerIntent]
    assigned_to: Optional[int]
    article_id: Optional[UUID]

    class Config:
        from_attributes = True


class CalendarImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[Dict[str, Any]]


# --------------------------------------------------------------------------
# Recommendations / audits
# --------------------------------------------------------------------------
class RecommendationResponse(BaseModel):
    id: UUID
    priority: enums.RecommendationPriority
    category: enums.RecommendationCategory
    title: str
    description: Optional[str]
    action_required: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class AuditResponse(BaseModel):
    id: UUID
    audit_type: enums.AuditType
    audit_date: date
    results_json: Optional[Any]
    created_at: datetime

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
class TargetProjection(BaseModel):
    label: str
    current_value: float
    target_value: float
    avg_daily_gain: Optional[float]
    projected_date: Optional[date]
    confidence_days: Optional[int]
    days_remaining: Optional[int]
    status: str            # on_track | slipping | at_risk | on_hold | achieved
    message: str


class ProjectionRequest(BaseModel):
    label: str = "target"
    current_value: float
    target_value: float
    historical_daily_progress: List[float]
    # Weeks of slip before the card turns amber, then red.
    amber_after_weeks: int = 1
    red_after_weeks: int = 2
    deadline: Optional[date] = None


class KpiCard(BaseModel):
    key: str
    label: str
    value: float
    unit: Optional[str] = None
    delta: Optional[float] = None
    delta_label: Optional[str] = None
    target: Optional[float] = None
    percent_of_target: Optional[float] = None
    direction: str = "flat"   # up | down | flat
    healthy: Optional[bool] = None


class TeamMemberStat(BaseModel):
    user_id: int
    full_name: str
    email: str
    role: str
    articles_this_week: int
    articles_published: int
    avg_score: Optional[float]
    backlinks_earned: int
    streak_days: int
    last_login_at: Optional[datetime]


class ActivityEntry(BaseModel):
    id: int
    user_email: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    detail: Optional[str]
    created_at: datetime


class SeriesPoint(BaseModel):
    date: date
    value: float
    secondary: Optional[float] = None


class DashboardHomeResponse(BaseModel):
    kpis: List[KpiCard]
    projections: List[TargetProjection]
    publish_velocity: List[SeriesPoint]
    publish_velocity_weekly_avg: float
    gsc_series: List[SeriesPoint]
    team: List[TeamMemberStat]
    recommendations: List[RecommendationResponse]
    activity: List[ActivityEntry]
    go_live_approved: bool
    go_live_message: str


class SiteHealthResponse(BaseModel):
    latest_audit: Optional[AuditResponse]
    open_recommendations: Dict[str, int]
    published_articles: int
    indexed_pages: Optional[int]
    avg_position: Optional[float]
    total_backlinks: int
    verified_backlinks: int
    go_live_approved: bool


ArticleDetailResponse.model_rebuild()
