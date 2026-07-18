"""Initialize created_at/updated_at for existing project cards

Revision ID: 006
Revises: 005
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use the creation date of migration 003 as a reasonable baseline for
    # project cards seeded by that migration.
    baseline = '2026-07-15 00:00:00+00'

    op.execute(
        sa.text(f"""
            UPDATE project_cards
            SET created_at = COALESCE(created_at, '{baseline}'::timestamptz),
                updated_at = COALESCE(updated_at, '{baseline}'::timestamptz)
            WHERE created_at IS NULL OR updated_at IS NULL
        """)
    )


def downgrade() -> None:
    pass
