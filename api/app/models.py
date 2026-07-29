from sqlalchemy import Column, Integer, String, Text, Date, TIMESTAMP, ForeignKey, CheckConstraint, Numeric, CHAR, SmallInteger, Boolean
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from app.database import Base

# 'owner'/'seo'/'writer' are the pre-SEO-module roles and are kept so existing
# accounts keep working; 'admin'/'seo_lead' are the roles the SEO module grants.
# ROLE_ADMIN / ROLE_SEO_LEAD below are the canonical sets to check against.
ALL_ROLES = ('owner', 'admin', 'seo', 'seo_lead', 'writer', 'viewer')

# 'owner' is legacy-equivalent to 'admin'; both get full access.
ROLE_ADMIN = ['owner', 'admin']
# Anyone who may create/edit articles. Cannot manage users.
ROLE_SEO_LEAD = ROLE_ADMIN + ['seo', 'seo_lead']


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(Text, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)
    role = Column(
        Text,
        CheckConstraint("role IN ('owner','admin','seo','seo_lead','writer','viewer')"),
        nullable=False,
    )
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # --- User management (SEO module) ---
    is_active = Column(Boolean, nullable=False, server_default='true')
    must_change_password = Column(Boolean, nullable=False, server_default='false')
    last_login_at = Column(TIMESTAMP(timezone=True))
    # Drives the 8-hour idle timeout; bumped at most once a minute per request.
    last_activity_at = Column(TIMESTAMP(timezone=True))
    # Scoping: empty/NULL means "all". Validated against the seo enums on write.
    assigned_verticals = Column(ARRAY(Text))
    assigned_countries = Column(ARRAY(Text))
    # TOTP enrolment. secret is set at enrolment, confirmed once a code verifies.
    totp_secret = Column(Text)
    totp_enabled = Column(Boolean, nullable=False, server_default='false')
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditEvent(Base):
    """Append-only record of user actions. Never updated, never deleted."""

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    # Denormalised so the trail survives the user being deleted.
    user_email = Column(Text)
    action = Column(Text, nullable=False, index=True)
    target_type = Column(Text)
    target_id = Column(Text)
    detail = Column(Text)
    ip = Column(Text)
    user_agent = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True)
    track = Column(CHAR(1), CheckConstraint("track IN ('A','B')"), nullable=False)
    pillar = Column(Text, nullable=False, index=True)
    keyword = Column(Text, nullable=False)
    intent = Column(Text)
    comp = Column(SmallInteger)
    fit = Column(SmallInteger)
    qw = Column(SmallInteger)
    score = Column(SmallInteger)
    ubersuggest_volume = Column(Integer)
    ubersuggest_kd = Column(SmallInteger)
    ubersuggest_cpc = Column(Numeric(6, 2))
    status = Column(Text, default='draft', index=True)
    assignee_id = Column(Integer, ForeignKey('users.id'))
    killed_reason = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(Text, unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    keyword_id = Column(Integer, ForeignKey('keywords.id'))
    track = Column(CHAR(1))
    vertical = Column(Text)
    country = Column(Text)
    article_type = Column(Text, CheckConstraint("article_type IN ('pillar','cluster','country')"), nullable=False)
    status = Column(Text, default='briefed', index=True)
    assignee_id = Column(Integer, ForeignKey('users.id'))
    publish_date = Column(Date)
    url = Column(Text)
    word_count = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    phase = Column(Text, nullable=False, index=True)
    task_code = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    owner_role = Column(Text)
    assignee_id = Column(Integer, ForeignKey('users.id'))
    status = Column(Text, default='open', index=True)
    due_date = Column(Date)
    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class ArticleMetric(Base):
    __tablename__ = "article_metrics"
    __table_args__ = (
        CheckConstraint("source IN ('manual','gsc','bing')"),
    )

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    metric_date = Column(Date, nullable=False)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    avg_position = Column(Numeric(4, 1))
    source = Column(Text, default='manual')
