---
name: project-card-postgresql-sot
description: ProjectCard в PostgreSQL является единственным Source of Truth карточек проектов ai-portfolio.
metadata:
  type: project
---

# ProjectCard в PostgreSQL — единственный SOT карточек проектов

**Проект:** ai-portfolio
**Дата утверждения:** 2026-07-15
**Статус:** Согласовано владельцем проекта, зафиксировано в Source of Truth

## Суть решения

Карточки проектов в каталоге портфолио — это управляемый контент. Их единственный Source of Truth — таблица `ProjectCard` в PostgreSQL.

## Обязательные правила

| Правило | Следствие |
|---------|-----------|
| ProjectCard в PostgreSQL — единственный SOT карточек | Все канонические данные карточек (заголовок, описание, категория, видимость, порядок) живут в БД |
| Публичный frontend не является SOT | Public сайт только отображает карточки |
| Статический HTML не хранит канонические данные карточек | HTML-страницы портфолио не являются источником правды для карточек в каталоге |
| Public frontend получает карточки через read-only API backend | Vanilla frontend загружает карточки с backend |
| Административная консоль — единственный интерфейс управления | CRUD карточек только через `/admin/knowledge-base/project-cards` |
| Изменения отображаются автоматически | После сохранения в админке public сайт показывает актуальные данные без правки HTML |

## Границы

- Решение относится **только к карточкам проектов в каталоге портфолио**.
- **Public frontend остаётся Vanilla HTML/CSS/JS.**
- **Страницы отдельных кейсов остаются статическими HTML.** Они содержат [[narrative-blueprint-case-level|Narrative Blueprint]] и не управляются карточками.
- ProjectCard не заменяет и не редактирует Narrative Blueprint и Presentation Patterns.

## Где зафиксировано

- `docs/PROJECT_STATE.md` — раздел «Управляемые карточки проектов (ProjectCard)»
- `docs/SPEC.md` — раздел 4 «Информационная архитектура» → «Портфолио: состав кейсов»
- `docs/ADMIN_CONSOLE_ARCHITECTURE.md` — раздел 2.4 «Модели данных» и раздел 5 «Взаимодействие GitHub / PostgreSQL / ChromaDB»

## Why

Решение согласовано владельцем проекта для разделения управляемого контента (ProjectCard) и инженерных артефактов (Narrative Blueprint / Presentation Patterns). Оно позволяет административной консоли управлять портфолио без превращения статических страниц кейсов в визуальный конструктор.

## How to apply

- При реализации backend административной консоли создавать модель `ProjectCard` в `backend/app/models/entities.py`.
- Публичный frontend должен загружать карточки через read-only endpoint (например, `GET /api/project-cards`).
- Статические страницы кейсов оставить без изменений; они ссылаются на тот же slug, что и `ProjectCard.external_url`.
- При синхронизации Knowledge Base `ProjectCard.knowledge_content` индексируется в ChromaDB.
