# PROJECT_STATE.md — AI Portfolio

**Проект:** ai-portfolio  
**Дата создания:** 2026-07-12  
**Последнее обновление:** 2026-08-25  
**Статус:** Главная страница обновлена до пилотной dual-theme версии с 13 карточками (12 проектов + Prompt Review placeholder). Production URL `https://ai.alex-n8n.site/` отдаёт новую страницу. `SPEC.md` v2.1, `TZ.md` v1.4 и `IMPLEMENTATION_PLAN.md` v3.2 актуализированы под расширенный состав портфеля. Каталог, отдельные страницы кейсов, AI-ассистент на новом корпусе и presale-аналитика ещё не завершены.

---

## 1. Project Summary

AI Portfolio — персональный публичный сайт AI-инженера с интегрированным AI-ассистентом. Платформа объединяет 12 реализованных AI-решений в единую витрину и сокращает путь потенциального заказчика до релевантного кейса, доказательств реализации и обращения к исполнителю.

**Утверждённый состав публичной витрины:** 13 управляемых карточек — 12 завершённых проектов + карточка-анонс **Prompt Review** на позиции 13.

**Ключевые параметры:**

| Параметр | Значение |
|----------|----------|
| Frontend | Vanilla HTML/CSS/JS (`src/`) |
| Backend | FastAPI + PostgreSQL + ChromaDB HTTP (`backend/`) |
| Admin Console | React + TypeScript + Vite (`admin/`) |
| LLM | OpenAI active + GigaChat fallback |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector store | ChromaDB HTTP server (`ai-portfolio-chroma`) |
| Auth | Bearer token (`ADMIN_API_TOKEN`) |
| Public URL | `https://ai.alex-n8n.site` |

---

## 2. Current Status

**Стадия:** Подготовка к production-ready release согласно `docs/TZ.md` v1.4 (утверждено) и `docs/IMPLEMENTATION_PLAN.md` v3.2 (утверждено). Целевой период: 19.08.2026 — 04.09.2026.

**Фактически реализовано (P1 + часть P2):**
- **Новая главная страница** (`src/index.html`): пилотная dual-theme версия с 13 карточками (12 проектов + Prompt Review placeholder), динамической загрузкой через `/project-cards`, переключателем темы и чат-виджетом.
- **Логика featured/archive:** первые три карточки по `display_order` отображаются как флагманы, позиции 4–12 — в архивной секции, позиция 13 — Prompt Review placeholder.
- **Deprecation `show_on_homepage`:** поле сохранено для обратной совместимости Admin Console, но публичный frontend использует только `is_visible` + `display_order`.
- Backend на FastAPI с PostgreSQL.
- `ProjectCard` в PostgreSQL — SOT карточек портфолио и главной; нумерация зафиксирована под новую главную.
- Admin Console v1 с пятью разделами (Dashboard, Content/KB, Logs, Conversations, Audit).
- GitHub Sync для Knowledge Base: 7 источников, 192 документа, ~5400 чанков.
- ChromaDB в production-режиме HTTP.
- Execution tracing и operational logs.
- Аудит входа в админку и посещений сайта.
- Production deploy на VPS.
- Актуализированы `SPEC.md` v2.1, `TZ.md` v1.4 и `IMPLEMENTATION_PLAN.md` v3.2 под 13 управляемыми карточками и новую логику главной страницы.

**Что ещё не реализовано (оставшиеся P2–P6):**
- Публичный каталог (`/portfolio.html`) — требует актуализации под 12 страниц проектов.
- 12 индивидуальных HTML-страниц проектов (`/cases/<project>.html`) — часть ссылок ведёт на существующие страницы, но витрина не полностью завершена.
- AI-ассистент `POST /chat` работает, но не настроен на обновлённый корпус всех 12 проектов; eval и latency-критерии не проверены.
- Presale-события и базовая presale-аналитика в Admin Console не добавлены.
- Deployment Validation AI Portfolio не пройдена.

**Что запланировано в текущей итерации (19.08–04.09.2026):**
- Разовая финализация 12 портфельных проектов + placeholder Prompt Review.
- Расширение GitHub Sync на все 12 проектов + собственный корпус AI Portfolio.
- Обновление публичного frontend: каталог, 12 страниц проектов, услуги, контакты.
- Настройка AI-ассистента на новый корпус (eval ≥90% / <5 сек).
- Добавление presale-событий и базовой presale-аналитики в Admin Console.
- Production release на VPS к 04.09.2026.

---

## 3. Market Validation

AI Portfolio создан как публичная витрина компетенций. Конкретные заказы и сделки на данном этапе не зафиксированы; после запуска устанавливается baseline конверсии посетителей в обращения.

---

## 4. Commercial Assessment

| Фактор | Оценка |
|--------|--------|
| Потенциал | Высокий — витрина закрывает типичный pain-point поиска исполнителя |
| Востребованность | Средне-высокая — заказчики AI-автоматизации оценивают портфолио |
| Риски | Низкая конверсия без чёткого позиционирования; зависимость от актуальности кейсов |

---

## 5. Key Technology Areas

| Область | Компетенция | Статус |
|---------|-------------|--------|
| FastAPI + PostgreSQL | Backend | ✅ |
| ChromaDB HTTP | Vector store | ✅ |
| OpenAI / GigaChat | Multi-provider LLM | ✅ |
| GitHub Sync | KB ingestion | ✅ |
| ProjectCard API | SOT карточек | ✅ |
| React Admin Console | Management UI | ✅ |
| Deployment on VPS | Production hosting | ✅ |
| Presale analytics | Conversion funnel | ⏳ Не реализовано |

---

## 6. Decision

**Принято:** довести AI Portfolio до production-ready состояния в период 19.08.2026 — 04.09.2026 в соответствии с `docs/TZ.md` v1.4 (утверждено) и `docs/IMPLEMENTATION_PLAN.md` v3.2 (утверждено).

**Утверждённые решения:**
- Итоговый проект курса — AI Portfolio.
- Целевой период реализации: 19.08.2026 — 04.09.2026.
- Целевая дата production-ready release: 04.09.2026.
- Финальный публичный состав AI Portfolio — **13 управляемых карточек**: 12 завершённых проектов + Prompt Review placeholder на позиции 13.
- AI Portfolio является итоговым метапроектом/витриной и не входит в состав этих 12 проектов.
- Prompt Review — карточка-анонс; полноценная страница, demo и GitHub-ссылки появятся после финализации материалов.
- Разовая финализация 12 проектов + подготовка материалов Prompt Review входит в единый `docs/IMPLEMENTATION_PLAN.md` v3.2.
- `docs/PORTFOLIO_CORPUS_AUDIT.md` v1.2 является baseline существующего технического долга.
- `docs/PEf05_RATING.md` v2.3 утверждён как внутренний аналитический артефакт (два рейтинга: 13 кандидатов и 12 проектов внутри портфеля).
- Шкала БЗ для внутреннего рейтинга: KB+RAG = 15, retrieval без RAG = 10, отсутствие = 0.
- Отсрочка Deployment Validation утверждена для: Telegram Intake Bot, Telegram Onboarding Bot, Review Flow, AI Portfolio.
- На старте реализации DEFER CANDIDATE отсутствуют. Полный scope выполняется по IMPLEMENTATION_PLAN до 04.09.2026.
- Production release выполняется на существующем VPS и домене `ai.alex-n8n.site`.

**Ожидающие решения владельца:**
- При фактической угрозе дедлайна 04.09.2026 — отдельное решение по DEFER CANDIDATE или другому сокращению scope.
- Что делать с кнопкой «Скачать портфолио» на главной странице (сейчас заглушка).

---

## 7. Next Steps

1. ✅ Утвердить ТЗ v1.4 (`docs/TZ.md`).
2. ✅ Утвердить IMPLEMENTATION_PLAN v3.2.
3. ✅ Утвердить PROJECT_STATE.
4. ✅ Актуализировать `SPEC.md` v2.1, `TZ.md` v1.4 и `IMPLEMENTATION_PLAN.md` v3.2 под 13 карточек и новую логику главной страницы.
5. ✅ Провести разовую финализацию 12 проектов (P0 плана) — завершена интеграция в главную страницу.
6. ✅ Актуализировать `ProjectCard` под 12 проектов + Prompt Review placeholder.
7. ⏳ Расширить GitHub Sync и перестроить ChromaDB.
8. ⏳ Обновить публичный frontend — главная страница развёрнута; каталог и страницы кейсов в работе.
9. ⏳ Настроить AI-ассистент на новый корпус.
10. ⏳ Добавить presale-аналитику в Admin Console.
11. ⏳ Пройти тестирование и production release к 04.09.2026.
12. ⏳ (отложено) Deployment Validation AI Portfolio.
13. ⏳ (отложено) Deployment Validation Telegram Intake Bot, Telegram Onboarding Bot, Review Flow.

---

## 8. Dependencies

| Зависимость | Описание | Влияние |
|-------------|----------|---------|
| VPS + домен | Production hosting | Блокирует публичный доступ |
| PostgreSQL | ProjectCard, logs, sessions | Блокирует backend |
| ChromaDB HTTP | Векторный поиск | Блокирует AI-ассистента |
| OpenAI API | Основной LLM | Блокирует AI-ассистента |
| GigaChat API | Fallback LLM | Деградация при недоступности OpenAI |
| GitHub API | Синхронизация KB | Блокирует актуализацию знаний |
| Согласование SOT | Утверждение плана и scope | Блокирует старт массовой реализации |

---

## 9. Risks

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Не успеть к 04.09.2026 | Средняя | Высокое | Перепланирование, параллелизация, анализ критического пути; возможное сокращение scope — только через отдельное решение владельца |
| Финализация 12 проектов + Prompt Review затягивается | Средняя | Высокое | Перепланирование зависимостей и параллельных потоков; при фактической угрозе дедлайну — формирование DEFER CANDIDATE на решение владельца |
| ChromaDB reindex медленный | Средняя | Среднее | Инкрементальная синхронизация; ночной запуск |
| LLM eval <90% | Средняя | Высокое | Докрутка промпта/ретривала |
| Устаревшие ссылки | Высокая | Среднее | Автопроверка, placeholder-страницы |
| Расхождение документации и реализации | Средняя | Среднее | Регулярная синхронизация SPEC/TZ/IMPLEMENTATION_PLAN при изменении scope |

---

## 10. Status History

| Дата | Статус | Комментарий |
|------|--------|-------------|
| 2026-07-12 | Создан проект | Первый PROJECT_STATE, SPEC, IMPLEMENTATION_PLAN |
| 2026-07-13 | UI реализован | 4 страницы + страницы кейсов |
| 2026-07-14 | Backend v1 | FastAPI + PostgreSQL + chat endpoint |
| 2026-07-15 | Admin Console v1 | Dashboard, Content/KB, Logs |
| 2026-07-19 | GitHub Sync | 7 источников, 192 документа, ~5400 чанков |
| 2026-08-18 | Финальное планирование | TZ v1.2, IMPLEMENTATION_PLAN v3.1, PEf05_RATING v2.3, PORTFOLIO_CORPUS_AUDIT v1.2 утверждены; релиз 04.09.2026 (status quo ante) |
| 2026-08-25 | Новая главная страница + расширение до 13 карточек | Развёрнута пилотная dual-theme главная с 13 карточками; нумерация ProjectCard зафиксирована; чат-виджет и темы работают; production URL `https://ai.alex-n8n.site/`; `SPEC.md` v2.1, `TZ.md` v1.4 и `IMPLEMENTATION_PLAN.md` v3.2 актуализированы под 13 карточек и логику featured/archive; каталог, страницы кейсов, AI-ассистент и presale-аналитика ещё не завершены |

---

## 11. Связанные документы

- [`README.md`](../README.md) — главная страница проекта.
- [`docs/SPEC.md`](SPEC.md) — продуктовая спецификация v2.1 (as-built baseline).
- [`docs/TZ.md`](TZ.md) — техническое задание v1.4 (утверждено).
- [`docs/IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — технический план v3.2 (утверждено).
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура.
- [`docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание.
- [`docs/PEf05_RATING.md`](PEf05_RATING.md) — рейтинг 13 кандидатов + 12 проектов в портфеле (v2.3, утверждено как внутренний аналитический артефакт).
- [`docs/PORTFOLIO_CORPUS_AUDIT.md`](PORTFOLIO_CORPUS_AUDIT.md) — аудит корпуса и технического долга (v1.2, утверждено как baseline).
