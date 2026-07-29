"""SEO Operations module + user management

Creates every seo_ table, the native enum types they depend on, the
audit_events trail, and the user-management columns on users. Seeds the
approved country x vertical matrix.

Revision ID: 002
Revises: 001
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- enum definitions -------------------------------------------------------
# Kept in lockstep with app/seo/enums.py.
ENUMS = {
    'seo_article_type': ['onpage', 'content'],
    'seo_article_status': [
        'drafted_by_author', 'in_team_review', 'submitted_for_scoring',
        'author_review', 'ready_to_publish', 'published', 'archived',
    ],
    'seo_vertical': ['rpa', 'n8n', 'whatsapp', 'agentic_ai'],
    'seo_country': ['india', 'nz', 'ireland', 'uk'],
    'seo_buyer_intent': ['informational', 'commercial', 'transactional'],
    'seo_source_platform': [
        'reddit', 'quora', 'paa', 'answerthepublic', 'pull_request', 'other',
    ],
    'seo_pull_request_platform': ['reddit', 'quora', 'paa', 'answerthepublic'],
    'seo_backlink_status': ['new', 'verified', 'lost'],
    'seo_audit_type': ['daily', 'weekly', 'monthly'],
    'seo_recommendation_priority': ['high', 'medium', 'low'],
    'seo_recommendation_category': ['technical', 'content', 'backlink', 'ranking'],
}

APPROVED_MATRIX = {
    'whatsapp': ['india'],
    'rpa': ['nz', 'ireland', 'uk'],
    'n8n': ['nz', 'ireland', 'uk', 'india'],
    'agentic_ai': ['india', 'nz', 'ireland', 'uk'],
}


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type; never emit CREATE TYPE from a column."""
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _uuid_pk():
    return sa.Column(
        'id', postgresql.UUID(as_uuid=True),
        server_default=sa.text('gen_random_uuid()'), nullable=False,
    )


def upgrade() -> None:
    # gen_random_uuid() is core in PG13+, but the extension makes this work on 11/12 too.
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')

    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)

    # ---------------- users: roles + management columns ----------------
    op.drop_constraint('users_role_check', 'users', type_='check')
    op.create_check_constraint(
        'users_role_check', 'users',
        "role IN ('owner','admin','seo','seo_lead','writer','viewer')",
    )
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('last_login_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('last_activity_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('assigned_verticals', postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column('users', sa.Column('assigned_countries', postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column('users', sa.Column('totp_secret', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column(
        'updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True))

    # ---------------- audit trail ----------------
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_email', sa.Text(), nullable=True),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('target_type', sa.Text(), nullable=True),
        sa.Column('target_id', sa.Text(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('ip', sa.Text(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_events_user_id', 'audit_events', ['user_id'])
    op.create_index('ix_audit_events_action', 'audit_events', ['action'])
    op.create_index('ix_audit_events_created_at', 'audit_events', ['created_at'])

    # ---------------- seo_articles ----------------
    op.create_table(
        'seo_articles',
        _uuid_pk(),
        sa.Column('type', _enum('seo_article_type'), nullable=False),
        sa.Column('status', _enum('seo_article_status'), nullable=False,
                  server_default='drafted_by_author'),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('slug', sa.Text(), nullable=True),
        sa.Column('vertical', _enum('seo_vertical'), nullable=False),
        sa.Column('country', _enum('seo_country'), nullable=True),
        sa.Column('primary_keyword', sa.Text(), nullable=False),
        sa.Column('keyword_difficulty', sa.Integer(), nullable=True),
        sa.Column('monthly_search_volume', sa.Integer(), nullable=True),
        sa.Column('buyer_intent', _enum('seo_buyer_intent'), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('author_draft_md', sa.Text(), nullable=True),
        sa.Column('team_edit_md', sa.Text(), nullable=True),
        sa.Column('final_md', sa.Text(), nullable=True),
        sa.Column('from_author_story', sa.Text(), nullable=True),
        sa.Column('current_score', sa.Integer(), nullable=True),
        sa.Column('featured_image_path', sa.Text(), nullable=True),
        sa.Column('featured_image_alt', sa.Text(), nullable=True),
        sa.Column('meta_title', sa.Text(), nullable=True),
        sa.Column('meta_description', sa.Text(), nullable=True),
        sa.Column('wp_post_id', sa.Integer(), nullable=True),
        sa.Column('wp_published_url', sa.Text(), nullable=True),
        sa.Column('ubersuggest_raw', sa.Text(), nullable=True),
        sa.Column('competitor_urls', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('published_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
        # Enforcement rule 1, at the storage layer: onpage always carries a
        # country, content never does. The approved-pair check lives in the API
        # because the matrix is editable data, not a constant.
        sa.CheckConstraint(
            "(type = 'onpage' AND country IS NOT NULL) OR (type = 'content' AND country IS NULL)",
            name='seo_articles_country_required_for_onpage',
        ),
    )
    op.create_index('ix_seo_articles_status', 'seo_articles', ['status'])
    op.create_index('ix_seo_articles_vertical', 'seo_articles', ['vertical'])
    op.create_index('ix_seo_articles_country', 'seo_articles', ['country'])
    op.create_index('ix_seo_articles_assigned_to', 'seo_articles', ['assigned_to'])
    op.create_index('ix_seo_articles_slug', 'seo_articles', ['slug'])

    # ---------------- child tables ----------------
    op.create_table(
        'seo_article_sources',
        _uuid_pk(),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('source_platform', _enum('seo_source_platform'), nullable=True),
        sa.Column('question_or_prompt', sa.Text(), nullable=True),
        sa.Column('captured_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['article_id'], ['seo_articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seo_article_sources_article_id', 'seo_article_sources', ['article_id'])

    op.create_table(
        'seo_article_faqs',
        _uuid_pk(),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('source_platform', _enum('seo_source_platform'), nullable=True),
        sa.Column('position_in_article', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['article_id'], ['seo_articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seo_article_faqs_article_id', 'seo_article_faqs', ['article_id'])

    op.create_table(
        'seo_article_versions',
        _uuid_pk(),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('snapshot_md', sa.Text(), nullable=True),
        sa.Column('score_json', postgresql.JSONB(), nullable=True),
        sa.Column('saved_by', sa.Integer(), nullable=True),
        sa.Column('saved_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['article_id'], ['seo_articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['saved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_id', 'version_number', name='uq_seo_article_version'),
    )
    op.create_index('ix_seo_article_versions_article_id', 'seo_article_versions', ['article_id'])

    op.create_table(
        'seo_scores',
        _uuid_pk(),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=True),
        sa.Column('total_score', sa.Integer(), nullable=True),
        sa.Column('breakdown_json', postgresql.JSONB(), nullable=True),
        sa.Column('comments_json', postgresql.JSONB(), nullable=True),
        sa.Column('scored_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['article_id'], ['seo_articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seo_scores_article_id', 'seo_scores', ['article_id'])

    op.create_table(
        'seo_calendar',
        _uuid_pk(),
        sa.Column('week_number', sa.Integer(), nullable=True),
        sa.Column('article_type', _enum('seo_article_type'), nullable=False),
        sa.Column('vertical', _enum('seo_vertical'), nullable=False),
        sa.Column('country', _enum('seo_country'), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('primary_keyword', sa.Text(), nullable=True),
        sa.Column('kd', sa.Integer(), nullable=True),
        sa.Column('volume', sa.Integer(), nullable=True),
        sa.Column('buyer_intent', _enum('seo_buyer_intent'), nullable=True),
        sa.Column('brief_json', postgresql.JSONB(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['article_id'], ['seo_articles.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seo_calendar_week_number', 'seo_calendar', ['week_number'])

    op.create_table(
        'seo_backlinks',
        _uuid_pk(),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('source_domain', sa.Text(), nullable=True),
        sa.Column('target_url', sa.Text(), nullable=False),
        sa.Column('anchor_text', sa.Text(), nullable=True),
        sa.Column('referring_dr', sa.Integer(), nullable=True),
        sa.Column('discovered_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('status', _enum('seo_backlink_status'), nullable=False, server_default='new'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_url', 'target_url', name='uq_seo_backlink_pair'),
    )
    op.create_index('ix_seo_backlinks_source_domain', 'seo_backlinks', ['source_domain'])
    op.create_index('ix_seo_backlinks_discovered_at', 'seo_backlinks', ['discovered_at'])

    op.create_table(
        'seo_audits',
        _uuid_pk(),
        sa.Column('audit_type', _enum('seo_audit_type'), nullable=False),
        sa.Column('audit_date', sa.Date(), nullable=False),
        sa.Column('results_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seo_audits_audit_type', 'seo_audits', ['audit_type'])
    op.create_index('ix_seo_audits_audit_date', 'seo_audits', ['audit_date'])

    op.create_table(
        'seo_gsc_daily',
        _uuid_pk(),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False, server_default=''),
        sa.Column('page_url', sa.Text(), nullable=False, server_default=''),
        sa.Column('impressions', sa.Integer(), server_default='0'),
        sa.Column('clicks', sa.Integer(), server_default='0'),
        sa.Column('avg_position', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('ctr', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', 'query', 'page_url', name='uq_seo_gsc_daily_row'),
    )
    op.create_index('ix_seo_gsc_daily_date', 'seo_gsc_daily', ['date'])

    op.create_table(
        'seo_team_stats',
        _uuid_pk(),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('articles_reviewed', sa.Integer(), server_default='0'),
        sa.Column('articles_submitted', sa.Integer(), server_default='0'),
        sa.Column('articles_published', sa.Integer(), server_default='0'),
        sa.Column('avg_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('backlinks_earned', sa.Integer(), server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uq_seo_team_stat_day'),
    )
    op.create_index('ix_seo_team_stats_user_id', 'seo_team_stats', ['user_id'])
    op.create_index('ix_seo_team_stats_date', 'seo_team_stats', ['date'])

    op.create_table(
        'seo_recommendations',
        _uuid_pk(),
        sa.Column('priority', _enum('seo_recommendation_priority'), nullable=False),
        sa.Column('category', _enum('seo_recommendation_category'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('action_required', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seo_recommendations_priority', 'seo_recommendations', ['priority'])
    op.create_index('ix_seo_recommendations_category', 'seo_recommendations', ['category'])
    op.create_index('ix_seo_recommendations_created_at', 'seo_recommendations', ['created_at'])

    op.create_table(
        'seo_pull_requests',
        _uuid_pk(),
        sa.Column('source_platform', _enum('seo_pull_request_platform'), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('question_captured', sa.Text(), nullable=False),
        sa.Column('suggested_vertical', _enum('seo_vertical'), nullable=True),
        sa.Column('suggested_country', _enum('seo_country'), nullable=True),
        sa.Column('captured_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('converted_to_article_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['converted_to_article_id'], ['seo_articles.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_url', 'question_captured', name='uq_seo_pull_request_question'),
    )
    op.create_index('ix_seo_pull_requests_source_platform', 'seo_pull_requests', ['source_platform'])
    op.create_index('ix_seo_pull_requests_captured_at', 'seo_pull_requests', ['captured_at'])

    op.create_table(
        'seo_country_vertical_matrix',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vertical', _enum('seo_vertical'), nullable=False),
        sa.Column('country', _enum('seo_country'), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('vertical', 'country', name='uq_seo_matrix_pair'),
    )

    op.create_table(
        'seo_api_usage',
        _uuid_pk(),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('operation', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), server_default='0'),
        sa.Column('output_tokens', sa.Integer(), server_default='0'),
        sa.Column('cost_inr', sa.Numeric(precision=10, scale=4), server_default='0'),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['article_id'], ['seo_articles.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seo_api_usage_date', 'seo_api_usage', ['date'])

    # ---------------- seed the approved matrix ----------------
    matrix_table = sa.table(
        'seo_country_vertical_matrix',
        sa.column('vertical', _enum('seo_vertical')),
        sa.column('country', _enum('seo_country')),
        sa.column('approved', sa.Boolean()),
    )
    # Every pair is stored, approved or not, so the UI can render the full grid
    # and show which combinations are deliberately closed.
    rows = [
        {'vertical': vertical, 'country': country,
         'approved': country in APPROVED_MATRIX[vertical]}
        for vertical in ENUMS['seo_vertical']
        for country in ENUMS['seo_country']
    ]
    op.bulk_insert(matrix_table, rows)


def downgrade() -> None:
    for table in [
        'seo_api_usage', 'seo_country_vertical_matrix', 'seo_pull_requests',
        'seo_recommendations', 'seo_team_stats', 'seo_gsc_daily', 'seo_audits',
        'seo_backlinks', 'seo_calendar', 'seo_scores', 'seo_article_versions',
        'seo_article_faqs', 'seo_article_sources', 'seo_articles', 'audit_events',
    ]:
        op.drop_table(table)

    for column in [
        'updated_at', 'totp_enabled', 'totp_secret', 'assigned_countries',
        'assigned_verticals', 'last_activity_at', 'last_login_at',
        'must_change_password', 'is_active',
    ]:
        op.drop_column('users', column)

    op.drop_constraint('users_role_check', 'users', type_='check')
    op.create_check_constraint(
        'users_role_check', 'users', "role IN ('owner','seo','writer','viewer')")

    for name in ENUMS:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
