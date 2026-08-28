"""Admission Console: preview artifacts, decision history, draft patterns

Revision ID: 015
Revises: 014
Create Date: 2026-08-28

§4.5а Admission Console:
- kb_admission_previews: immutable admission-preview artifacts (patterns,
  head commit SHA, per-file decisions) that approvals reference.
- kb_admission_events: admission decision history (audit log).
- knowledge_sources additions:
  - draft_include_patterns / draft_exclude_patterns: working copy of the
    selection rules; NULL means the draft equals the effective patterns.
    Effective include/exclude_patterns are consumed by the sync pipeline
    and change only through approval.
  - approved_preview_id / approved_at: approval references an immutable
    preview; the previous approved composition stays in force until a
    new approval.
  - display_name: human-readable project name (owner's naming).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'kb_admission_previews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('knowledge_sources.id'), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='ready'),
        sa.Column('commit_sha', sa.String(100), nullable=True),
        sa.Column('include_patterns', postgresql.JSON(), nullable=True),
        sa.Column('exclude_patterns', postgresql.JSON(), nullable=True),
        sa.Column('candidates_total', sa.Integer(), nullable=True),
        sa.Column('included_count', sa.Integer(), nullable=True),
        sa.Column('excluded_count', sa.Integer(), nullable=True),
        sa.Column('files', postgresql.JSON(), nullable=True),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'kb_admission_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('knowledge_sources.id'), nullable=False, index=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('summary', sa.String(500), nullable=True),
        sa.Column('details', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'knowledge_sources',
        sa.Column('draft_include_patterns', postgresql.JSON(), nullable=True),
    )
    op.add_column(
        'knowledge_sources',
        sa.Column('draft_exclude_patterns', postgresql.JSON(), nullable=True),
    )
    op.add_column(
        'knowledge_sources',
        sa.Column('approved_preview_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'knowledge_sources',
        sa.Column('approved_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'knowledge_sources',
        sa.Column('display_name', sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('knowledge_sources', 'display_name')
    op.drop_column('knowledge_sources', 'approved_at')
    op.drop_column('knowledge_sources', 'approved_preview_id')
    op.drop_column('knowledge_sources', 'draft_exclude_patterns')
    op.drop_column('knowledge_sources', 'draft_include_patterns')
    op.drop_table('kb_admission_events')
    op.drop_table('kb_admission_previews')