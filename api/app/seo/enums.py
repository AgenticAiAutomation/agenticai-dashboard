"""Enum vocabularies for the SEO Operations module.

Every one of these is backed by a native Postgres enum type (created in the
Alembic migration) so invalid values are rejected by the database as well as
by the API layer.
"""
from enum import Enum


class ArticleType(str, Enum):
    onpage = "onpage"      # country + vertical required, geo keyword, commercial CTA
    content = "content"    # general education, no country lock, informational CTA


class ArticleStatus(str, Enum):
    drafted_by_author = "drafted_by_author"
    in_team_review = "in_team_review"
    submitted_for_scoring = "submitted_for_scoring"
    author_review = "author_review"
    ready_to_publish = "ready_to_publish"
    published = "published"
    archived = "archived"


class Vertical(str, Enum):
    rpa = "rpa"
    n8n = "n8n"
    whatsapp = "whatsapp"
    agentic_ai = "agentic_ai"


class Country(str, Enum):
    india = "india"
    nz = "nz"
    ireland = "ireland"
    uk = "uk"


class BuyerIntent(str, Enum):
    informational = "informational"
    commercial = "commercial"
    transactional = "transactional"


class SourcePlatform(str, Enum):
    reddit = "reddit"
    quora = "quora"
    paa = "paa"
    answerthepublic = "answerthepublic"
    pull_request = "pull_request"
    other = "other"


class PullRequestPlatform(str, Enum):
    """Narrower than SourcePlatform — a captured question always has an origin."""
    reddit = "reddit"
    quora = "quora"
    paa = "paa"
    answerthepublic = "answerthepublic"


class BacklinkStatus(str, Enum):
    new = "new"
    verified = "verified"
    lost = "lost"


class AuditType(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class RecommendationPriority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class RecommendationCategory(str, Enum):
    technical = "technical"
    content = "content"
    backlink = "backlink"
    ranking = "ranking"


# Postgres type names. Kept here so models and the migration cannot drift.
PG_ENUM_NAMES = {
    ArticleType: "seo_article_type",
    ArticleStatus: "seo_article_status",
    Vertical: "seo_vertical",
    Country: "seo_country",
    BuyerIntent: "seo_buyer_intent",
    SourcePlatform: "seo_source_platform",
    PullRequestPlatform: "seo_pull_request_platform",
    BacklinkStatus: "seo_backlink_status",
    AuditType: "seo_audit_type",
    RecommendationPriority: "seo_recommendation_priority",
    RecommendationCategory: "seo_recommendation_category",
}
