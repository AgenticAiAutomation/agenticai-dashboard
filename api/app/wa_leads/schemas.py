"""Request and response shapes for the leads desk."""
from typing import List, Optional

from pydantic import BaseModel, Field


class StatusEvent(BaseModel):
    created_at: str
    from_status: str
    to_status: str
    note: str
    actor: str


class Lead(BaseModel):
    id: int
    created_at: str
    name: str
    whatsapp: str
    email: str
    language: str
    need_type: str
    industry: str
    subtype: str
    pain_points: List[str]
    auto_services: List[str]
    organic_channels: List[str]
    inorganic_channels: List[str]
    website_status: str
    fit_score: int
    qualified: bool
    consent_at: Optional[str]
    utm_source: str
    utm_medium: str
    utm_campaign: str
    referrer: str
    notified_at: Optional[str]
    status: str
    status_note: str
    status_by: str
    status_at: Optional[str]


class LeadDetail(Lead):
    history: List[StatusEvent]


class LeadPage(BaseModel):
    leads: List[Lead]
    total: int
    page: int
    pages: int
    page_size: int


class StatusUpdate(BaseModel):
    status: str = Field(..., description="One of the pipeline statuses")
    note: str = Field("", max_length=1000)


class StatusCount(BaseModel):
    status: str
    count: int


class Stats(BaseModel):
    total: int
    by_status: List[StatusCount]
    open_leads: int
    converted: int
    rejected: int
    # Of the leads someone has actually finished with, how many converted.
    # Leads still in the pipeline are excluded: counting them as "not yet
    # converted" makes the rate look worse the more new leads arrive.
    conversion_rate: Optional[float]
    qualified_total: int
    qualified_converted: int
    last_7_days: int
    average_fit_score: Optional[float]


class Meta(BaseModel):
    statuses: List[str]
    open_statuses: List[str]
    industries: List[str]
    can_write: bool
    db_ok: bool


class NotificationLead(BaseModel):
    id: int
    created_at: str
    name: str
    industry: str
    subtype: str
    fit_score: int
    qualified: bool
    status: str


class Notifications(BaseModel):
    latest_id: int
    unseen: int
    leads: List[NotificationLead]
