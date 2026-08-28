"""Add KB admission gate fields to knowledge_sources

Revision ID: 014
Revises: 013
Create Date: 2026-08-28

KB admission gate (fail-closed):
- admission_status: pending / approved / blocked; server_default 'pending'
  puts all existing sources into the safe, non-indexed state without
  approving them automatically.
- include_patterns / exclude_patterns: explicit path allow/deny globs
  (JSON lists). NULL/empty include list means "index nothing".
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'knowledge_sources',
        sa.Column('admission_status', sa.String(20), nullable=False, server_default='pending'),
    )
    op.add_column(
        'knowledge_sources',
        sa.Column('include_patterns', postgresql.JSON(), nullable=True),
    )
    op.add_column(
        'knowledge_sources',
        sa.Column('exclude_patterns', postgresql.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('knowledge_sources', 'exclude_patterns')
    op.drop_column('knowledge_sources', 'include_patterns')
    op.drop_column('knowledge_sources', 'admission_status')