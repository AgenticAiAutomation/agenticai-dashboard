"""Blog Visual Engine — block content and revisions

Additive only. seo_articles gains content_blocks (the block array) and
content_format ('legacy' for every existing row, 'blocks' once an article is
authored in the new editor). The existing markdown columns are not touched,
never dropped, and keep rendering every legacy article exactly as before.

seo_article_revisions holds autosave history for block articles: one row per
saved change, last 50 kept per article (trimmed in code), one-click restore.

Rollback: scripts/rollback_blocks.py or `alembic downgrade 002` — drops only
what this revision added.

Revision ID: 003
Revises: 002
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('seo_articles', sa.Column('content_blocks', postgresql.JSONB(), nullable=True))
    op.add_column('seo_articles', sa.Column(
        'content_format', sa.Text(), nullable=False, server_default='legacy'))
    op.create_check_constraint(
        'ck_seo_articles_content_format', 'seo_articles',
        "content_format IN ('legacy', 'blocks')")

    op.create_table(
        'seo_article_revisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('content_blocks', postgresql.JSONB(), nullable=False),
        # Title, slug, meta title/description, keyword at the time of saving, so
        # a restore brings the whole article back, not just the body.
        sa.Column('meta', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['article_id'], ['seo_articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_id', 'revision_number', name='uq_seo_article_revision'),
    )
    op.create_index('ix_seo_article_revisions_article_id', 'seo_article_revisions',
                    ['article_id', 'revision_number'])


def downgrade() -> None:
    op.drop_index('ix_seo_article_revisions_article_id', table_name='seo_article_revisions')
    op.drop_table('seo_article_revisions')
    op.drop_constraint('ck_seo_articles_content_format', 'seo_articles', type_='check')
    op.drop_column('seo_articles', 'content_format')
    op.drop_column('seo_articles', 'content_blocks')
