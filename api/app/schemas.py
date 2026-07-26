from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


# Auth schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# User schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# Keyword schemas
class KeywordCreate(BaseModel):
    track: str
    pillar: str
    keyword: str
    intent: Optional[str] = None
    comp: Optional[int] = None
    fit: Optional[int] = None
    qw: Optional[int] = None
    score: Optional[int] = None
    ubersuggest_volume: Optional[int] = None
    ubersuggest_kd: Optional[int] = None
    ubersuggest_cpc: Optional[Decimal] = None
    status: str = 'draft'
    assignee_id: Optional[int] = None
    killed_reason: Optional[str] = None


class KeywordUpdate(BaseModel):
    track: Optional[str] = None
    pillar: Optional[str] = None
    keyword: Optional[str] = None
    intent: Optional[str] = None
    comp: Optional[int] = None
    fit: Optional[int] = None
    qw: Optional[int] = None
    score: Optional[int] = None
    ubersuggest_volume: Optional[int] = None
    ubersuggest_kd: Optional[int] = None
    ubersuggest_cpc: Optional[Decimal] = None
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    killed_reason: Optional[str] = None


class KeywordResponse(BaseModel):
    id: int
    track: str
    pillar: str
    keyword: str
    intent: Optional[str]
    comp: Optional[int]
    fit: Optional[int]
    qw: Optional[int]
    score: Optional[int]
    ubersuggest_volume: Optional[int]
    ubersuggest_kd: Optional[int]
    ubersuggest_cpc: Optional[Decimal]
    status: str
    assignee_id: Optional[int]
    killed_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Article schemas
class ArticleCreate(BaseModel):
    slug: str
    title: str
    keyword_id: Optional[int] = None
    track: Optional[str] = None
    vertical: Optional[str] = None
    country: Optional[str] = None
    article_type: str
    status: str = 'briefed'
    assignee_id: Optional[int] = None
    publish_date: Optional[date] = None
    url: Optional[str] = None
    word_count: Optional[int] = None


class ArticleUpdate(BaseModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    keyword_id: Optional[int] = None
    track: Optional[str] = None
    vertical: Optional[str] = None
    country: Optional[str] = None
    article_type: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    publish_date: Optional[date] = None
    url: Optional[str] = None
    word_count: Optional[int] = None


class ArticleResponse(BaseModel):
    id: int
    slug: str
    title: str
    keyword_id: Optional[int]
    track: Optional[str]
    vertical: Optional[str]
    country: Optional[str]
    article_type: str
    status: str
    assignee_id: Optional[int]
    publish_date: Optional[date]
    url: Optional[str]
    word_count: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Task schemas
class TaskCreate(BaseModel):
    phase: str
    task_code: str
    title: str
    description: Optional[str] = None
    owner_role: Optional[str] = None
    assignee_id: Optional[int] = None
    status: str = 'open'
    due_date: Optional[date] = None
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    phase: Optional[str] = None
    task_code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    owner_role: Optional[str] = None
    assignee_id: Optional[int] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class TaskResponse(BaseModel):
    id: int
    phase: str
    task_code: str
    title: str
    description: Optional[str]
    owner_role: Optional[str]
    assignee_id: Optional[int]
    status: str
    due_date: Optional[date]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Metric schemas
class MetricCreate(BaseModel):
    article_id: int
    metric_date: date
    impressions: int = 0
    clicks: int = 0
    avg_position: Optional[Decimal] = None
    source: str = 'manual'


class MetricResponse(BaseModel):
    id: int
    article_id: int
    metric_date: date
    impressions: int
    clicks: int
    avg_position: Optional[Decimal]
    source: str

    class Config:
        from_attributes = True


class DashboardSummary(BaseModel):
    total_keywords: int
    total_articles: int
    published_articles: int
    tasks_open: int
    tasks_done: int
    phase_progress: dict
