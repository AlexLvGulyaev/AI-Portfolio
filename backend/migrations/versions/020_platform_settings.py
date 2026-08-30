"""Platform settings key-value store for retrieval console (task 2026-08-29).

Retrieval Settings console (recreated from Assistant Flow): PostgreSQL stores
partial overrides on top of env bootstrap defaults — ``retrieval_tuning``
(JSON dict of tuning fields) and ``active_rag_backend`` (backend name).
Keys omitted from the JSON mean "use env default" (AF pattern P6.12).

Rollback: drop the table (env defaults remain effective).
"""

import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")