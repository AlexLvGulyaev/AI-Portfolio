"""Final portfolio project cards (12 projects)

Revision ID: 013
Revises: 012
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa
import json

# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


# Final 12 portfolio projects.
# Order matches IMPLEMENTATION_PLAN.md §2.
FINAL_CARDS = [
    {
        "slug": "review-auto-responder",
        "title": "Review Auto Responder",
        "short_description": "Автоматический ответчик на отзывы: мультипровайдерная генерация, операторская панель, demo-RBAC, Deployment Validation 17/17.",
        "category": "cases",
        "tags": ["FastAPI", "OpenAI", "GigaChat", "LLM", "Review Automation"],
        "display_order": 1,
        "show_on_homepage": 1,
        "external_url": "/cases/review-auto-responder.html",
    },
    {
        "slug": "ai-curator",
        "title": "AI Curator",
        "short_description": "AI-ассистент для студентов и преподавателей с KB+RAG, Admin Console и мультипровайдерной LLM-цепочкой.",
        "category": "cases",
        "tags": ["FastAPI", "RAG", "KB", "OpenAI", "Education"],
        "display_order": 2,
        "show_on_homepage": 2,
        "external_url": "/cases/ai-curator.html",
    },
    {
        "slug": "ai-data-assistant",
        "title": "AI Data Assistant",
        "short_description": "Data-ассистент с мультипровайдерным runtime-конфигом оператора, графиками, DOCX-отчётами и Docker E2E.",
        "category": "cases",
        "tags": ["FastAPI", "Data Analysis", "OpenAI", "GigaChat", "Docker E2E"],
        "display_order": 3,
        "show_on_homepage": 3,
        "external_url": "/cases/ai-data-assistant.html",
    },
    {
        "slug": "assistant-flow",
        "title": "Assistant Flow",
        "short_description": "Мультимодальная RAG-платформа для обработки входящих заявок клиентов.",
        "category": "cases",
        "tags": ["RAG", "React", "FastAPI", "PostgreSQL", "ChromaDB"],
        "display_order": 4,
        "show_on_homepage": 4,
        "external_url": "/cases/assistant-flow.html",
    },
    {
        "slug": "meeting-audit-bot",
        "title": "Meeting Audit Bot",
        "short_description": "Telegram-бот аудита встреч: транскрибация, мультипровайдерный анализ, веб-админка и execution-трейсы.",
        "category": "cases",
        "tags": ["Telegram Bot", "STT", "FastAPI", "OpenAI", "GigaChat"],
        "display_order": 5,
        "show_on_homepage": 0,
        "external_url": "/cases/meeting-audit-bot.html",
    },
    {
        "slug": "lead-qualification",
        "title": "Lead Qualification",
        "short_description": "AI-система квалификации лидов для отдела продаж: классификация, scoring, интеграция с CRM.",
        "category": "cases",
        "tags": ["n8n", "AI Classification", "CRM", "Sales"],
        "display_order": 6,
        "show_on_homepage": 0,
        "external_url": "/cases/lead-qualification.html",
    },
    {
        "slug": "review-flow",
        "title": "Review Flow",
        "short_description": "Автоматизация работы с отзывами и обращениями: Controlled Hybrid, LLM + RAG, staff-контур.",
        "category": "cases",
        "tags": ["FastAPI", "RAG", "React", "OpenAI", "Review Management"],
        "display_order": 7,
        "show_on_homepage": 0,
        "external_url": "/cases/review-flow.html",
    },
    {
        "slug": "hr-assistant",
        "title": "HR Assistant",
        "short_description": "Telegram-бот HR-автоматизации: обработка резюме, matching, multimedia-ответы.",
        "category": "cases",
        "tags": ["Telegram Bot", "HR", "Matching", "TTS", "Visual Generation"],
        "display_order": 8,
        "show_on_homepage": 0,
        "external_url": "/cases/hr-assistant.html",
    },
    {
        "slug": "hr-assistant-lora",
        "title": "HR Assistant — LoRA Fine-Tuning",
        "short_description": "Эксперименты LoRA-дообучения Qwen2.5 для matching-модели HR-ассистента.",
        "category": "cases",
        "tags": ["LoRA", "Qwen", "Fine-Tuning", "ML", "Matching"],
        "display_order": 9,
        "show_on_homepage": 0,
        "external_url": "/cases/hr-assistant-lora.html",
    },
    {
        "slug": "telegram-intake-bot",
        "title": "Telegram Intake Bot",
        "short_description": "Telegram-бот первичной поддержки с двумя сценариями: FAQ и сбор лидов.",
        "category": "cases",
        "tags": ["Telegram Bot", "Support", "FAQ", "Lead Capture"],
        "display_order": 10,
        "show_on_homepage": 0,
        "external_url": "/cases/telegram-intake-bot.html",
    },
    {
        "slug": "telegram-onboarding-bot",
        "title": "Telegram Onboarding Bot",
        "short_description": "Telegram-бот адаптации сотрудников: внешние темы, inline-редактор, RBAC на смену глобальной темы.",
        "category": "cases",
        "tags": ["Telegram Bot", "Onboarding", "HR", "FSM"],
        "display_order": 11,
        "show_on_homepage": 0,
        "external_url": "/cases/telegram-onboarding-bot.html",
    },
    {
        "slug": "retail-group",
        "title": "Retail Group",
        "short_description": "Пресейл-кейс голосового AI-ассистента первой линии поддержки: Case Story, пилотный план, экономика.",
        "category": "cases",
        "tags": ["Voice AI", "Presale", "Case Story", "Pilot"],
        "display_order": 12,
        "show_on_homepage": 0,
        "external_url": "/cases/retail-group.html",
    },
]

# Projects that should be hidden from the public portfolio.
HIDDEN_SLUGS = ["telegram-ai-gateway", "competitor-monitor"]


def _upsert_card(conn, card: dict) -> None:
    """Insert or update a project card by slug."""
    existing = conn.execute(
        sa.text("SELECT id FROM project_cards WHERE slug = :slug"),
        {"slug": card["slug"]},
    ).fetchone()

    params = {
        "slug": card["slug"],
        "title": card["title"],
        "short_description": card["short_description"],
        "category": card["category"],
        "tags": json.dumps(card["tags"]),
        "display_order": card["display_order"],
        "show_on_homepage": card["show_on_homepage"],
        "external_url": card["external_url"],
    }

    if existing:
        conn.execute(
            sa.text("""
                UPDATE project_cards
                SET title = :title,
                    short_description = :short_description,
                    category = :category,
                    tags = CAST(:tags AS json),
                    display_order = :display_order,
                    show_on_homepage = :show_on_homepage,
                    external_url = :external_url,
                    is_visible = true,
                    updated_at = NOW()
                WHERE slug = :slug
            """),
            params,
        )
    else:
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
            params,
        )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Hide excluded projects
    for slug in HIDDEN_SLUGS:
        conn.execute(
            sa.text("""
                UPDATE project_cards
                SET is_visible = false,
                    show_on_homepage = 0,
                    updated_at = NOW()
                WHERE slug = :slug
            """),
            {"slug": slug},
        )

    # 2. Upsert final 12 project cards
    for card in FINAL_CARDS:
        _upsert_card(conn, card)


# Pre-migration (seed 003) state for cards touched by this migration.
# Used by downgrade to restore a clean state.
LEGACY_CARD_STATE = {
    "assistant-flow": {
        "display_order": 1,
        "show_on_homepage": 1,
        "tags": ["n8n", "OpenAI", "Telegram"],
    },
    "review-flow": {
        "display_order": 2,
        "show_on_homepage": 0,
        "tags": ["n8n", "AI Analysis", "Sentiment"],
    },
    "lead-qualification": {
        "display_order": 3,
        "show_on_homepage": 2,
        "tags": ["AI", "CRM", "Sales"],
    },
    "hr-assistant": {
        "display_order": 4,
        "show_on_homepage": 3,
        "tags": ["Telegram Bot", "HR", "CRM"],
    },
    "hr-assistant-lora": {
        "display_order": 8,
        "show_on_homepage": 0,
        "tags": ["LoRA", "Qwen", "Fine-Tuning", "ML"],
    },
    "prompt-review": {
        "display_order": 5,
        "show_on_homepage": 4,
    },
    "telegram-ai-gateway": {
        "display_order": 6,
        "show_on_homepage": 0,
    },
    "competitor-monitor": {
        "display_order": 7,
        "show_on_homepage": 0,
    },
}


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Remove newly added project cards (those not present in seed 003)
    existing_seeded_slugs = {
        "assistant-flow", "review-flow", "lead-qualification", "hr-assistant", "hr-assistant-lora",
    }
    new_slugs = [card["slug"] for card in FINAL_CARDS if card["slug"] not in existing_seeded_slugs]
    if new_slugs:
        placeholders = ", ".join(f":slug_{i}" for i in range(len(new_slugs)))
        conn.execute(
            sa.text(f"DELETE FROM project_cards WHERE slug IN ({placeholders})"),
            {f"slug_{i}": slug for i, slug in enumerate(new_slugs)},
        )

    # 2. Restore legacy state for seeded cards that were modified or hidden
    for slug, legacy in LEGACY_CARD_STATE.items():
        params = {"slug": slug}
        set_clauses = ["is_visible = true", "updated_at = NOW()"]

        if "display_order" in legacy:
            set_clauses.append("display_order = :display_order")
            params["display_order"] = legacy["display_order"]
        if "show_on_homepage" in legacy:
            set_clauses.append("show_on_homepage = :show_on_homepage")
            params["show_on_homepage"] = legacy["show_on_homepage"]
        if "tags" in legacy:
            set_clauses.append("tags = CAST(:tags AS json)")
            params["tags"] = json.dumps(legacy["tags"])

        conn.execute(
            sa.text(f"""
                UPDATE project_cards
                SET {", ".join(set_clauses)}
                WHERE slug = :slug
            """),
            params,
        )
