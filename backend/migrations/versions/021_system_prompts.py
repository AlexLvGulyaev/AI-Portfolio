"""System prompt managed storage for the AI settings console (task 2026-08-30).

Moves the system prompt out of the hardcoded ``prompt_assembly.py``:
``system_prompts`` stores prompt versions (body + version label) with a
single active row enforced by a partial unique index. An empty table means
"use the builtin prompt" (owner decision: hardcoded ``v4-compact-multi``
remains the fallback/reset source).

Rollback: drop the table (builtin prompt remains effective).
"""

import sqlalchemy as sa
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_prompts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.String(16), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_system_prompts_created_at",
        "system_prompts",
        ["created_at"],
    )
    # Единственный активный промпт (PostgreSQL partial unique index).
    op.create_index(
        "uq_system_prompts_single_active",
        "system_prompts",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_system_prompts_single_active", table_name="system_prompts")
    op.drop_index("ix_system_prompts_created_at", table_name="system_prompts")
    op.drop_table("system_prompts")