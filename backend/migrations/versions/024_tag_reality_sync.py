"""Tag reality sync: Telegram on 5 more cards, n8n on hr-assistant/retail-group

Revision ID: 024
Revises: 023
Create Date: 2026-09-03

Owner report (03.09.2026): the landing's technology filter disagreed
with reality. Verified against lab case docs:

- Telegram is involved in 9 of 13 cards, missing only on the three
  flagships (ai-curator, ai-data-assistant, review-flow) and
  retail-group. The DB carried it on only 4. Added here:
  - review-auto-responder: operator notifications via Telegram;
  - assistant-flow: Telegram-бот как основная оболочка;
  - lead-qualification: intake из Website/Telegram;
  - prompt-review: Telegram Bot — равноправный канал подачи;
  - hr-assistant-lora: живёт в Telegram-конвейере hr-assistant.
- hr-assistant pipeline is "Telegram Bot → n8n Workflows → OpenAI API"
  (README) — n8n added;
- retail-group stack is n8n-driven (README) — n8n added.

Data-only, idempotent: appends missing tags, keeps existing ones.
Naming follows the DB convention ("Telegram Bot", not the display
chip "Telegram" — the landing filter matches substrings).
"""
import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None

# slug -> tags to append
TAG_ADDITIONS = {
    'review-auto-responder': ['Telegram Bot'],
    'assistant-flow': ['Telegram Bot'],
    'lead-qualification': ['Telegram Bot'],
    'prompt-review': ['Telegram Bot'],
    'hr-assistant-lora': ['Telegram Bot'],
    'hr-assistant': ['n8n'],
    'retail-group': ['n8n'],
}


def _set_tags(conn, slug: str, add_tags: list, add: bool) -> None:
    row = conn.execute(
        sa.text("SELECT tags FROM project_cards WHERE slug = :slug"),
        {"slug": slug},
    ).fetchone()
    if not row or not row[0]:
        return
    tags = list(row[0])
    changed = False
    for tag in add_tags:
        if add:
            if tag in tags:
                continue  # idempotent: уже есть
            tags.append(tag)
            changed = True
        else:
            if tag not in tags:
                continue
            tags.remove(tag)
            changed = True
    if not changed:
        return
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
    for slug, add_tags in TAG_ADDITIONS.items():
        _set_tags(conn, slug, add_tags, add=True)


def downgrade() -> None:
    conn = op.get_bind()
    for slug, add_tags in TAG_ADDITIONS.items():
        _set_tags(conn, slug, add_tags, add=False)