"""Add audit event type indices for admin_login and site_visit

Revision ID: 010
Revises: 009
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # operational_logs.event_type is String(100) without a CHECK constraint,
    # so no schema change is required to support 'admin_login' or 'site_visit'.
    # Add a dedicated index to keep audit-event lookups fast as the table grows.
    op.create_index(
        'ix_operational_logs_event_type_status',
        'operational_logs',
        ['event_type', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_operational_logs_event_type_status', table_name='operational_logs')
