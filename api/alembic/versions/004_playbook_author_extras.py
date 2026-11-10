"""Blog Playbook v2: nullable author extras on seo_articles

Additive only: author_best_pick (JSONB {option, reason}), author_notice (TEXT),
author_must_do (JSONB list). Like playbook_blocks, they are read and written
with plain SQL in app/seo/playbook.py and are not mapped on SeoArticle, so the
API runs the same with or without them and downgrade is safe at any time
(only these three columns go; no other data is touched).

Revision ID: 004_playbook_author_extras
Revises: 003_playbook_blocks
Create Date: 2026-11-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '004_playbook_author_extras'
down_revision: Union[str, None] = '003_playbook_blocks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('seo_articles', sa.Column('author_best_pick', postgresql.JSONB(), nullable=True))
    op.add_column('seo_articles', sa.Column('author_notice', sa.Text(), nullable=True))
    op.add_column('seo_articles', sa.Column('author_must_do', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('seo_articles', 'author_must_do')
    op.drop_column('seo_articles', 'author_notice')
    op.drop_column('seo_articles', 'author_best_pick')
