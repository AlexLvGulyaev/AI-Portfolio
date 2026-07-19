"""Add visitor context to execution_sessions

Revision ID: 011
Revises: 010
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add visitor context columns to execution_sessions.
    op.add_column('execution_sessions', sa.Column('visitor_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('execution_sessions', sa.Column('client_ip', sa.String(100), nullable=True))
    op.add_column('execution_sessions', sa.Column('user_agent', sa.Text(), nullable=True))

    # Indexes for fast filtering by visitor.
    op.create_index('ix_execution_sessions_visitor_id', 'execution_sessions', ['visitor_id'])
    op.create_index('ix_execution_sessions_client_ip', 'execution_sessions', ['client_ip'])


def downgrade() -> None:
    op.drop_index('ix_execution_sessions_visitor_id', table_name='execution_sessions')
    op.drop_index('ix_execution_sessions_client_ip', table_name='execution_sessions')
    op.drop_column('execution_sessions', 'user_agent')
    op.drop_column('execution_sessions', 'client_ip')
    op.drop_column('execution_sessions', 'visitor_id')
