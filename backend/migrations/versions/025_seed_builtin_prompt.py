"""Seed the builtin prompt as active managed version (decision B, plan 4a).

Revision ID: 025
Revises: 024
Create Date: 2026-09-09

Decision B (PROMPT_ARCHITECTURE §3, owner 09.09.2026): the managed
``system_prompts`` row is the single runtime SOT; the builtin text in
``prompt_assembly.py`` is the release-baseline seed. ChatOrchestrator
degrades honestly (503) when no active row can be loaded — so a clean
deployment with an empty table would start with the chat channel
unavailable. This migration seeds the builtin baseline as the active
managed version, so a fresh deployment is chat-ready out of the box
(the owner then manages versions via the Admin Console as usual).

Idempotent: no-op when an active row already exists (e.g. production
with v14-format-defense).

Rollback: deactivate the seeded builtin row (chat channel then degrades
honestly until a version is activated).
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.admin.system_prompt_service import body_hash
    from app.services.prompt_assembly import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION

    conn = op.get_bind()
    has_active = conn.execute(
        sa.text("SELECT 1 FROM system_prompts WHERE is_active = true LIMIT 1")
    ).first()
    if has_active:
        return
    digest = body_hash(SYSTEM_PROMPT)
    existing = conn.execute(
        sa.text(
            "SELECT id FROM system_prompts "
            "WHERE version = :v AND body_hash = :h LIMIT 1"
        ),
        {"v": SYSTEM_PROMPT_VERSION, "h": digest},
    ).first()
    if existing:
        conn.execute(
            sa.text("UPDATE system_prompts SET is_active = true WHERE id = :id"),
            {"id": existing[0]},
        )
        return
    conn.execute(
        sa.text(
            "INSERT INTO system_prompts "
            "(id, version, body, body_hash, note, is_active, is_builtin, created_at) "
            "VALUES (:id, :v, :b, :h, :note, true, true, now())"
        ),
        {
            "id": uuid.uuid4(),
            "v": SYSTEM_PROMPT_VERSION,
            "b": SYSTEM_PROMPT,
            "h": digest,
            "note": "Seed релизного базлайна (решение B, миграция 025)",
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE system_prompts SET is_active = false "
            "WHERE is_builtin = true AND is_active = true"
        )
    )