"""Add is_backfilled flag to execution_sessions

Revision ID: 009
Revises: 008
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql

# Import models via the path configured by env.py
from app.models.entities import ExecutionSession

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    session = Session(bind=conn)

    # Add column with default FALSE.
    op.add_column(
        'execution_sessions',
        sa.Column('is_backfilled', sa.Boolean(), nullable=False, server_default='false')
    )

    # Mark all existing execution_sessions as backfilled.
    # The last operational log in the old format has id 2960349e-48ed-4af6-9a48-344b9c27a4d5.
    # All execution_sessions created before or at the same time as this boundary are synthetic.
    boundary_row = session.execute(
        sa.select(ExecutionSession.created_at)
        .where(ExecutionSession.id == sa.cast(
            '2960349e-48ed-4af6-9a48-344b9c27a4d5', postgresql.UUID
        ))
    ).scalar_one_or_none()

    if boundary_row:
        session.execute(
            sa.update(ExecutionSession)
            .where(ExecutionSession.created_at <= boundary_row)
            .values(is_backfilled=True)
        )
        session.commit()


def downgrade() -> None:
    op.drop_column('execution_sessions', 'is_backfilled')
