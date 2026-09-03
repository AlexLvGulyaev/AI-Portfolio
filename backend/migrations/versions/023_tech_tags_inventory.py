"""Tech tags inventory: prompt-review += FastAPI, hr-assistant-lora += n8n

Revision ID: 023
Revises: 022
Create Date: 2026-09-03

Owner decision (03.09.2026, pre-release tech inventory): the landing's
technology filter (fastapi / n8n) did not know two flagship/research
stacks, so those cards were unreachable by filter:

- prompt-review is a production-ready FastAPI service (README: "FastAPI
  Service — полноценный сервис с Web UI, Telegram Bot и REST API") — tag
  FastAPI added;
- hr-assistant-lora lives in the hr-assistant pipeline (Telegram Bot →
  n8n Workflows → OpenAI API) — tag n8n added.

Data-only migration: existing tags lists are extended, no other fields
touched. Idempotent upgrade (skip if the tag is already present).
"""
import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None

# slug -> tag to append
TAG_FIXES = {
    'prompt-review': 'FastAPI',
    'hr-assistant-lora': 'n8n',
}


def _set_tag(conn, slug: str, tag: str, add: bool) -> None:
    row = conn.execute(
        sa.text("SELECT tags FROM project_cards WHERE slug = :slug"),
        {"slug": slug},
    ).fetchone()
    if not row or not row[0]:
        return
    tags = list(row[0])
    if add:
        if tag in tags:
            return  # idempotent: уже есть
        tags.append(tag)
    else:
        if tag not in tags:
            return
        tags.remove(tag)
    # tags — postgresql.JSON(): массив psycopg2 не кастится в json
    # неявно, поэтому передаём JSON-строку с явным CAST.
    conn.execute(
        sa.text(
            "UPDATE project_cards SET tags = CAST(:tags AS json) "
            "WHERE slug = :slug"
        ),
        {"slug": slug, "tags": json.dumps(tags, ensure_ascii=False)},
    )


def upgrade() -> None:
    conn = op.get_bind()
    for slug, tag in TAG_FIXES.items():
        _set_tag(conn, slug, tag, add=True)


def downgrade() -> None:
    conn = op.get_bind()
    for slug, tag in TAG_FIXES.items():
        _set_tag(conn, slug, tag, add=False)