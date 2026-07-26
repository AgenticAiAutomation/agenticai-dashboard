"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-26

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('full_name', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("role IN ('owner','seo','writer','viewer')", name='users_role_check'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)

    # Create keywords table
    op.create_table(
        'keywords',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track', sa.CHAR(length=1), nullable=False),
        sa.Column('pillar', sa.Text(), nullable=False),
        sa.Column('keyword', sa.Text(), nullable=False),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('comp', sa.SmallInteger(), nullable=True),
        sa.Column('fit', sa.SmallInteger(), nullable=True),
        sa.Column('qw', sa.SmallInteger(), nullable=True),
        sa.Column('score', sa.SmallInteger(), nullable=True),
        sa.Column('ubersuggest_volume', sa.Integer(), nullable=True),
        sa.Column('ubersuggest_kd', sa.SmallInteger(), nullable=True),
        sa.Column('ubersuggest_cpc', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('assignee_id', sa.Integer(), nullable=True),
        sa.Column('killed_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("track IN ('A','B')", name='keywords_track_check'),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_keywords_pillar'), 'keywords', ['pillar'], unique=False)
    op.create_index(op.f('ix_keywords_status'), 'keywords', ['status'], unique=False)

    # Create articles table
    op.create_table(
        'articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('keyword_id', sa.Integer(), nullable=True),
        sa.Column('track', sa.CHAR(length=1), nullable=True),
        sa.Column('vertical', sa.Text(), nullable=True),
        sa.Column('country', sa.Text(), nullable=True),
        sa.Column('article_type', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('assignee_id', sa.Integer(), nullable=True),
        sa.Column('publish_date', sa.Date(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("article_type IN ('pillar','cluster','country')", name='articles_article_type_check'),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['keyword_id'], ['keywords.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_articles_slug'), 'articles', ['slug'], unique=False)
    op.create_index(op.f('ix_articles_status'), 'articles', ['status'], unique=False)

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('phase', sa.Text(), nullable=False),
        sa.Column('task_code', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_role', sa.Text(), nullable=True),
        sa.Column('assignee_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_phase'), 'tasks', ['phase'], unique=False)
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)

    # Create article_metrics table
    op.create_table(
        'article_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('impressions', sa.Integer(), nullable=True),
        sa.Column('clicks', sa.Integer(), nullable=True),
        sa.Column('avg_position', sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column('source', sa.Text(), nullable=True),
        sa.CheckConstraint("source IN ('manual','gsc','bing')", name='article_metrics_source_check'),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_id', 'metric_date', 'source', name='_article_date_source_uc')
    )


def downgrade() -> None:
    op.drop_table('article_metrics')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_phase'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index(op.f('ix_articles_status'), table_name='articles')
    op.drop_index(op.f('ix_articles_slug'), table_name='articles')
    op.drop_table('articles')
    op.drop_index(op.f('ix_keywords_status'), table_name='keywords')
    op.drop_index(op.f('ix_keywords_pillar'), table_name='keywords')
    op.drop_table('keywords')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
