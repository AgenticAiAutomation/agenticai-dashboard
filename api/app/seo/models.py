"""SQLAlchemy models for the SEO Operations module.

All tables are prefixed seo_ and live in the default (public) schema alongside
the existing dashboard tables, so foreign keys to users.id and the existing
Alembic history work without a search_path change.

Article ids are UUIDs per spec; users.id is an existing Integer PK, so every
FK to a user is Integer.
"""
import uuid

from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, Numeric, SmallInteger, Text,
    TIMESTAMP, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base
from app.seo import enums
from app.seo.pgtypes import pg_enum


def _uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                  server_default=func.gen_random_uuid())


class SeoArticle(Base):
    __tablename__ = "seo_articles"

    id = _uuid_pk()
    type = Column(pg_enum(enums.ArticleType), nullable=False)
    status = Column(pg_enum(enums.ArticleStatus), nullable=False,
                    server_default=enums.ArticleStatus.drafted_by_author.value, index=True)
    title = Column(Text)
    slug = Column(Text, unique=True, index=True)
    vertical = Column(pg_enum(enums.Vertical), nullable=False, index=True)
    # Required only when type = 'onpage'; validated against the approved matrix.
    country = Column(pg_enum(enums.Country), index=True)

    primary_keyword = Column(Text, nullable=False)
    keyword_difficulty = Column(Integer)
    monthly_search_volume = Column(Integer)
    buyer_intent = Column(pg_enum(enums.BuyerIntent))

    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)

    author_draft_md = Column(Text)   # what the author generated for the team to edit
    team_edit_md = Column(Text)      # what the team submitted after editing
    final_md = Column(Text)          # the version that will be published
    from_author_story = Column(Text)  # filled after team submits; replaces [FROM AUTHOR]

    current_score = Column(Integer)
    featured_image_path = Column(Text)   # MinIO object path
    featured_image_alt = Column(Text)    # author-generated from article context
    meta_title = Column(Text)
    meta_description = Column(Text)

    wp_post_id = Column(Integer)
    wp_published_url = Column(Text)

    # Ubersuggest has no API on the lifetime tier, so competitor URLs and raw
    # metrics arrive as a pasted blob from the article creation form.
    ubersuggest_raw = Column(Text)
    competitor_urls = Column(JSONB)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    published_at = Column(TIMESTAMP(timezone=True))


class SeoArticleSource(Base):
    __tablename__ = "seo_article_sources"

    id = _uuid_pk()
    article_id = Column(UUID(as_uuid=True), ForeignKey("seo_articles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    source_url = Column(Text)
    source_platform = Column(pg_enum(enums.SourcePlatform))
    question_or_prompt = Column(Text)
    captured_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class SeoArticleFaq(Base):
    __tablename__ = "seo_article_faqs"

    id = _uuid_pk()
    article_id = Column(UUID(as_uuid=True), ForeignKey("seo_articles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text)
    source_url = Column(Text)
    source_platform = Column(pg_enum(enums.SourcePlatform))
    position_in_article = Column(Integer)


class SeoArticleVersion(Base):
    __tablename__ = "seo_article_versions"
    __table_args__ = (
        UniqueConstraint("article_id", "version_number", name="uq_seo_article_version"),
    )

    id = _uuid_pk()
    article_id = Column(UUID(as_uuid=True), ForeignKey("seo_articles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    snapshot_md = Column(Text)
    score_json = Column(JSONB)
    saved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    saved_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class SeoScore(Base):
    __tablename__ = "seo_scores"

    id = _uuid_pk()
    article_id = Column(UUID(as_uuid=True), ForeignKey("seo_articles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    version_number = Column(Integer)
    total_score = Column(Integer)
    breakdown_json = Column(JSONB)   # per-parameter points earned / available
    comments_json = Column(JSONB)    # line-by-line comments
    scored_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class SeoCalendar(Base):
    __tablename__ = "seo_calendar"

    id = _uuid_pk()
    week_number = Column(Integer, index=True)
    article_type = Column(pg_enum(enums.ArticleType), nullable=False)
    vertical = Column(pg_enum(enums.Vertical), nullable=False)
    country = Column(pg_enum(enums.Country))
    title = Column(Text)
    primary_keyword = Column(Text)
    kd = Column(Integer)
    volume = Column(Integer)
    buyer_intent = Column(pg_enum(enums.BuyerIntent))
    brief_json = Column(JSONB)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    # Set once the calendar row has been turned into a real article.
    article_id = Column(UUID(as_uuid=True), ForeignKey("seo_articles.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class SeoBacklink(Base):
    __tablename__ = "seo_backlinks"
    __table_args__ = (
        UniqueConstraint("source_url", "target_url", name="uq_seo_backlink_pair"),
    )

    id = _uuid_pk()
    source_url = Column(Text, nullable=False)
    source_domain = Column(Text, index=True)
    target_url = Column(Text, nullable=False)
    anchor_text = Column(Text)
    referring_dr = Column(Integer)
    discovered_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    status = Column(pg_enum(enums.BacklinkStatus), nullable=False,
                    server_default=enums.BacklinkStatus.new.value)


class SeoAudit(Base):
    __tablename__ = "seo_audits"

    id = _uuid_pk()
    audit_type = Column(pg_enum(enums.AuditType), nullable=False, index=True)
    audit_date = Column(Date, nullable=False, index=True)
    results_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class SeoGscDaily(Base):
    __tablename__ = "seo_gsc_daily"
    __table_args__ = (
        UniqueConstraint("date", "query", "page_url", name="uq_seo_gsc_daily_row"),
        Index("ix_seo_gsc_daily_date", "date"),
    )

    id = _uuid_pk()
    date = Column(Date, nullable=False)
    query = Column(Text, nullable=False, server_default="")
    page_url = Column(Text, nullable=False, server_default="")
    impressions = Column(Integer, server_default="0")
    clicks = Column(Integer, server_default="0")
    avg_position = Column(Numeric(6, 2))
    ctr = Column(Numeric(6, 4))


class SeoTeamStat(Base):
    __tablename__ = "seo_team_stats"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_seo_team_stat_day"),
    )

    id = _uuid_pk()
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    articles_reviewed = Column(Integer, server_default="0")
    articles_submitted = Column(Integer, server_default="0")
    articles_published = Column(Integer, server_default="0")
    avg_score = Column(Numeric(5, 2))
    backlinks_earned = Column(Integer, server_default="0")


class SeoRecommendation(Base):
    __tablename__ = "seo_recommendations"

    id = _uuid_pk()
    priority = Column(pg_enum(enums.RecommendationPriority), nullable=False, index=True)
    category = Column(pg_enum(enums.RecommendationCategory), nullable=False, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    action_required = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    resolved_at = Column(TIMESTAMP(timezone=True))


class SeoPullRequest(Base):
    """A question captured from Reddit/Quora/PAA that is worth answering."""

    __tablename__ = "seo_pull_requests"
    __table_args__ = (
        UniqueConstraint("source_url", "question_captured", name="uq_seo_pull_request_question"),
    )

    id = _uuid_pk()
    source_platform = Column(pg_enum(enums.PullRequestPlatform), nullable=False, index=True)
    source_url = Column(Text)
    question_captured = Column(Text, nullable=False)
    # Best-guess routing filled by the scraper; the team confirms on convert.
    suggested_vertical = Column(pg_enum(enums.Vertical))
    suggested_country = Column(pg_enum(enums.Country))
    captured_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    converted_to_article_id = Column(UUID(as_uuid=True),
                                     ForeignKey("seo_articles.id", ondelete="SET NULL"))


class CountryVerticalMatrix(Base):
    __tablename__ = "seo_country_vertical_matrix"
    __table_args__ = (
        UniqueConstraint("vertical", "country", name="uq_seo_matrix_pair"),
    )

    id = Column(Integer, primary_key=True)
    vertical = Column(pg_enum(enums.Vertical), nullable=False)
    country = Column(pg_enum(enums.Country), nullable=False)
    approved = Column(Boolean, nullable=False, server_default="false")


class SeoApiUsage(Base):
    """Per-call cost ledger, so the daily Claude budget cap is enforceable."""

    __tablename__ = "seo_api_usage"

    id = _uuid_pk()
    date = Column(Date, nullable=False, index=True)
    provider = Column(Text, nullable=False)
    operation = Column(Text)
    input_tokens = Column(Integer, server_default="0")
    output_tokens = Column(Integer, server_default="0")
    cost_inr = Column(Numeric(10, 4), server_default="0")
    article_id = Column(UUID(as_uuid=True), ForeignKey("seo_articles.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
