"""Seed project cards from public portfolio catalog

Revision ID: 003
Revises: 002
Create Date: 2026-07-15

"""
from alembic import op
import sqlalchemy as sa
import json

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


# Single source for initial project cards.
# Generated from src/portfolio.html via scripts/bootstrap_project_cards.py.
# After this migration PostgreSQL is the single Source of Truth for project cards.
PROJECT_CARDS = [
    {
        "slug": "assistant-flow",
        "title": "Assistant Flow",
        "short_description": "AI-ассистент для обработки входящих заявок. Классификация, маршрутизация и первичная обработка.",
        "category": "cases",
        "tags": ["n8n", "OpenAI", "Telegram"],
        "display_order": 1,
        "show_on_homepage": 1,
        "external_url": "/cases/assistant-flow.html",
    },
    {
        "slug": "review-flow",
        "title": "Review Flow",
        "short_description": "Автоматизация работы с отзывами. Анализ тональности и подготовка ответов.",
        "category": "cases",
        "tags": ["n8n", "AI Analysis", "Sentiment"],
        "display_order": 2,
        "show_on_homepage": 0,
        "external_url": "/cases/review-flow.html",
    },
    {
        "slug": "lead-qualification",
        "title": "Lead Qualification",
        "short_description": "AI-система квалификации лидов для отдела продаж.",
        "category": "cases",
        "tags": ["AI", "CRM", "Sales"],
        "display_order": 3,
        "show_on_homepage": 2,
        "external_url": "/cases/lead-qualification.html",
    },
    {
        "slug": "hr-assistant",
        "title": "HR Assistant",
        "short_description": "Telegram-бот для HR-автоматизации и работы с сотрудниками.",
        "category": "cases",
        "tags": ["Telegram Bot", "HR", "CRM"],
        "display_order": 4,
        "show_on_homepage": 3,
        "external_url": "/cases/hr-assistant.html",
    },
    {
        "slug": "prompt-review",
        "title": "Prompt Review",
        "short_description": "Автоматическая проверка промптов. Анализ качества и рекомендации.",
        "category": "cases",
        "tags": ["AI", "Prompts", "Quality"],
        "display_order": 5,
        "show_on_homepage": 4,
        "external_url": "/cases/prompt-review.html",
    },
    {
        "slug": "telegram-ai-gateway",
        "title": "Telegram AI Gateway",
        "short_description": "Шлюз для интеграции AI-моделей в Telegram. Единая точка входа.",
        "category": "cases",
        "tags": ["Telegram", "AI Gateway", "API"],
        "display_order": 6,
        "show_on_homepage": 0,
        "external_url": "/cases/telegram-ai-gateway.html",
    },
    {
        "slug": "competitor-monitor",
        "title": "Competitor Monitor AI",
        "short_description": "AI-система мониторинга конкурентов. Сбор, анализ и уведомления.",
        "category": "cases",
        "tags": ["AI", "Monitoring", "Analytics"],
        "display_order": 7,
        "show_on_homepage": 0,
        "external_url": "/cases/competitor-monitor.html",
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    # Idempotency guard: only seed if project_cards is empty.
    existing = conn.execute(sa.text("SELECT COUNT(*) FROM project_cards")).scalar()
    if existing and existing > 0:
        return

    for card in PROJECT_CARDS:
        conn.execute(
            sa.text("""
                INSERT INTO project_cards (
                    id, slug, title, short_description, category, tags,
                    display_order, show_on_homepage, is_visible, external_url
                ) VALUES (
                    gen_random_uuid(), :slug, :title, :short_description, :category, CAST(:tags AS json),
                    :display_order, :show_on_homepage, true, :external_url
                )
            """),
            {
                "slug": card["slug"],
                "title": card["title"],
                "short_description": card["short_description"],
                "category": card["category"],
                "tags": json.dumps(card["tags"]),
                "display_order": card["display_order"],
                "show_on_homepage": card["show_on_homepage"],
                "external_url": card["external_url"],
            },
        )


def downgrade() -> None:
    slugs = ", ".join(f"'{card['slug']}'" for card in PROJECT_CARDS)
    op.execute(f"DELETE FROM project_cards WHERE slug IN ({slugs})")
