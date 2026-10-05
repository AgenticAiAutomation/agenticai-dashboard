"""Blog Playbook: nullable seo_articles.playbook_blocks

Additive only. The column holds the Playbook writer's structured form of an
article so the builder can reopen it; body_md (author_draft_md/team_edit_md)
is still the article. It is read and written with plain SQL in
app/seo/playbook.py and is not mapped on SeoArticle, so the API runs the same
with or without it — downgrade is safe at any time.

Note for feat/blog-engine-v2: that branch also carries a 003 revising 002.
Whichever lands second must change its down_revision to the other's id.

Revision ID: 003_playbook_blocks
Revises: 002
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '003_playbook_blocks'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('seo_articles',
                  sa.Column('playbook_blocks', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('seo_articles', 'playbook_blocks')
