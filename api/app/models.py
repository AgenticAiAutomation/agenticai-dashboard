from sqlalchemy import Column, Integer, String, Text, Date, TIMESTAMP, ForeignKey, CheckConstraint, Numeric, CHAR, SmallInteger
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(Text, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)
    role = Column(Text, CheckConstraint("role IN ('owner','seo','writer','viewer')"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


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
