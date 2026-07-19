# PROJECT_STATE.md

**Проект:** ai-portfolio
**Дата создания:** 2026-07-12
**Последнее обновление:** 2026-07-18
**Статус:** Завершён базовый продукт в объёме уроков Prompt Engineering. Реализована административная консоль v1. Параметры LLM-провайдеров перенесены в БД и управляются через Dashboard. Execution Tracing для панели «Логи» реализовано. Проект находится под управлением Git, репозиторий инициализирован.

---

## Project Summary

Персональный сайт AI-инженера с интегрированным AI-ассистентом. Платформа для демонстрации компетенций и привлечения заказчиков AI-автоматизации.

**Фактически реализовано:**
- Пользовательский интерфейс (4 страницы + 7 страниц кейсов)
- Backend на FastAPI с PostgreSQL
- AI-ассистент (POST /chat) с памятью диалога, RAG на ChromaDB и кешированием ответов
- Мультипровайдерная архитектура AI-провайдеров (OpenAI + GigaChat fallback)
- **База данных как единый Source of Truth для параметров LLM-провайдеров** (model, temperature, max_tokens, base_url, is_enabled, is_active, is_fallback)
- **Управление параметрами LLM-провайдеров через Dashboard административной консоли** (редактирование, выбор active/fallback, тест соединения)
- Логирование взаимодействий в PostgreSQL
- Docker-контейнеризация frontend и backend
- Продакшн-деплой на VPS: https://ai.alex-n8n.site
- Административная консоль v1 (Dashboard, Content / Knowledge Base, Logs / Conversations)
- Управление ProjectCard в PostgreSQL как единственным SOT карточек проектов
- Ручная синхронизация Knowledge Base → ChromaDB через `/admin/knowledge-base/sync`

---

## Current Status

**Статус:** Проект завершён в объёме уроков Prompt Engineering.

**Достижения:**
- Пользовательский интерфейс реализован (4 страницы + 7 страниц кейсов)
- Backend на FastAPI реализован и функционирует
- PostgreSQL используется как основная СУБД
- AI-ассистент отвечает на вопросы о кейсах и услугах
- Сайт развёрнут на VPS по адресу https://ai.alex-n8n.site
- SSL сертификат получен (Let's Encrypt)
- Docker-конфигурация приведена к единому Source of Truth (`docker-compose.yml`) и управляется через Docker Compose v2
- Административная консоль v1 реализована и развёрнута: три рабочих пространства (Dashboard, Content / Knowledge Base, Logs / Conversations)
- Управление карточками проектов вынесено в PostgreSQL; public frontend получает карточки через read-only API
- Параметры LLM-провайдеров вынесены в PostgreSQL и редактируются через Dashboard админки; API-ключи остаются в `.env`
- Аудит входа в административную консоль и посещений публичного сайта реализован: endpoints `POST /admin/login` и `POST /track-visit`, записи `admin_login` / `site_visit` в `operational_logs`, просмотр во вкладке «Аудит» панели «Логи»
- Архитектурное упрощение логирования chat pipeline: `chat_request` больше не дублируется в `operational_logs`; `execution_sessions` является единым SOT; добавлены `visitor_id`, `client_ip`, `user_agent` в `ExecutionSession`; публичный frontend передаёт `visitor_id` в `POST /chat`
- Переработана страница «Диалоги» в стиле Assistant Flow Memory Console: двухпанельный layout, фильтры, список сессий с runtime context, detail panel с парными turns, execution timeline и JSON snapshot. Панель диалога занимает основное пространство экрана; таблица диалога содержит колонки cache hit и response time на уровне turn; execution timeline по умолчанию свёрнут.
- Доводка страницы «Логи»: правая макропанель Execution-сессии разделена на «Параметры сессии» и «Параметры исполнения», убраны лишние строки статуса (время МСК, TEXT OK / RAG OK), унифицированы отступы между заголовками панелей и параметрами.

**Текущий этап:** Базовый продукт, административная консоль, operational console «Логи» и operational console «Диалоги» в стиле Assistant Flow завершены. Frontend использует `/admin/execution-sessions` и `/admin/execution-sessions/{id}` для отображения execution-сессий chat pipeline с visitor-реквизитами, а `/admin/conversations` и `/admin/conversations/{id}` для диалоговых сессий. Backfill'нутые сессии помечены флагом `is_backfilled`. Аудит входа в админку и посещений сайта реализован и доступен для просмотра во вкладке «Аудит». Ожидается Deployment Validation по решению владельца продукта перед финальной публикацией.

---

## Market Validation

_Не определено на данном этапе._

---

## Owner Decisions (SOT)

> Решения владельца продукта, принятые и не подлежащие изменению без веских оснований.

### Продукт

**Главный продукт первой версии — персональный сайт AI-инженера.**

AI-ассистент, RAG, Telegram и другие компоненты рассматриваются исключительно как функции сайта, а не самостоятельные продукты.

### Целевая аудитория

**Основная:** Потенциальные заказчики AI-автоматизации малого и среднего бизнеса.

**Дополнительная:**
- Работодатели
- Коллеги
- Преподаватели и проверяющие

### Портфолио

На сайте представлены зрелые кейсы APL:

1. Assistant Flow
2. Review Flow
3. Lead Qualification
4. HR Assistant
5. Prompt Review
6. Telegram AI Gateway
7. Competitor Monitor AI

С возможностью последующего расширения.

### Информация об услугах

**Не публиковать прайс-лист.**

Показывать:
- Решаемые задачи
- Используемые технологии
- Получаемую бизнес-ценность
- Реализованные проекты

Стоимость обсуждается индивидуально.

### Основной призыв к действию

Использовать формат:
- «Обсудить проект»
- или «Связаться со мной»

Не использовать маркетинговые формулировки вроде «Оставьте заявку».

### Telegram

Telegram является одним из каналов связи и поддерживается проектом.

Однако сайт остаётся основной точкой входа.

### Эксплуатация

Проект ориентирован на постоянную работу на существующем VPS.

Поддержку осуществляет владелец проекта.

### AI-провайдер

**Фактически реализована мультипровайдерная архитектура:**
- OpenAI — основной провайдер
- GigaChat — fallback-провайдер
- Mock-провайдер для тестирования

**Параметры провайдеров (model_name, temperature, max_tokens, base_url, is_enabled, is_active, is_fallback) хранятся в PostgreSQL и управляются через административную консоль.** API-ключи остаются в переменных окружения и не хранятся в БД.

Архитектура допускает замену и добавление провайдеров через таблицу `ai_provider_settings`.

### База знаний

База знаний является частью личного бренда и поддерживается владельцем проекта.

### Визуальный стиль

Использовать существующие материалы из `attachments/branding/` как основу визуальной идентичности проекта.

Не копировать учебные материалы преподавателя.

### Стиль сайта

Современный инженерный минимализм.

Не использовать шаблонный «AI-футуризм» и перегруженные лендинги.

### Архитектура представления проектов

**Каждый кейс AI Portfolio обязан иметь собственный Narrative Blueprint.**

Narrative Blueprint является артефактом уровня кейса. Он определяет индивидуальную драматургию проекта. Narrative Blueprint не является шаблоном.

**Presentation Patterns являются переиспользуемой библиотекой уровня APL.**

Presentation Patterns содержат проверенные способы представления информации. Presentation Patterns не определяют Narrative конкретного проекта.

**Порядок разработки:**

При разработке нового кейса сначала разрабатывается Narrative Blueprint. После этого Narrative реализуется посредством выбора и применения Presentation Patterns.

**Lead Qualification является первым проектом, полностью реализованным по данной архитектуре.**

Narrative Blueprint Lead Qualification считается эталонной реализацией артефакта уровня кейса. Все последующие кейсы также обязаны иметь собственный Narrative Blueprint.

---

## Commercial Assessment

_Не определено на данном этапе._

---

## Административная консоль

**Административная консоль v1 реализована и развёрнута.**

Первоначально консоль планировалась как следующий этап развития продукта, но в рамках текущей итерации она была реализована и интегрирована в production-контур. Реализация охватывает три согласованных рабочих пространства.

Deployment Validation будет проведён по решению владельца проекта перед финальной публикацией.

### Реализованная функциональность v1

Первая версия административной консоли содержит **пять разделов навигации**, сгруппированных по функциям:

| Раздел | Назначение | Границы |
|--------|------------|---------|
| **Системные настройки (Dashboard)** | Единая сводная картина состояния AI Portfolio, включая управление параметрами LLM-провайдеров и выбор active/fallback | Мониторинг + управление LLM-провайдерами. Не управляет остальным содержимым |
| **Контент / База знаний** | Управление карточками проектов, источниками KB, запуск синхронизации | Не редактирует Narrative Blueprint и Presentation Patterns; не является визуальным конструктором страниц |
| **Логи** | Operational console в стиле Assistant Flow: журнал execution-сессий chat pipeline с preview запроса, visitor_id, client_ip, user_agent, summary grid, цепочкой этапов, вопросом/ответом в двух колонках, timeline pipeline с дельтами и JSON snapshot. Frontend использует `/admin/execution-sessions` и `/admin/execution-sessions/{id}`. Backfill'нутые сессии (из миграции 008) помечены флагом `is_backfilled` и отображаются с меткой "приблизительный". Вкладка «Аудит» показывает только системные operational logs (`admin_login`, `site_visit`, `provider_switch`) через `/admin/logs` | — |
| **Аудит** | Вход в административную консоль логируется через `POST /admin/login` (`event_type='admin_login'`). Посещения публичного сайта логируются через `POST /track-visit` (`event_type='site_visit'`). `chat_request` больше не дублируется здесь — он покрывается execution-сессиями. Данные обезличены: фиксируются только `visitor_id` / IP / user_agent | — |
| **Диалоги** | Operational console в стиле Assistant Flow Memory Console: двухпанельный layout, фильтры по времени/режиму/активности/поиску, список сессий с runtime context, detail panel с парными turns, execution timeline и JSON snapshot | — |

### Технологический стек v1

| Компонент | Технология | Решение |
|-----------|------------|---------|
| Frontend | React + TypeScript + Vite | Отдельный SPA в каталоге `admin/`, `base: '/admin/'` |
| Backend | FastAPI | Единое приложение с префиксом `/admin` |
| Аутентификация | Bearer token | Единый `ADMIN_API_TOKEN` из переменных окружения |
| Routing | React Router | `BrowserRouter basename="/admin"` |

---

## Управляемые карточки проектов (ProjectCard)

**ProjectCard в PostgreSQL является единственным Source of Truth карточек проектов.**

### Правила

| Правило | Смысл |
|---------|-------|
| **ProjectCard в PostgreSQL — единственный SOT карточек проектов** | Канонические данные карточек (заголовки, описания, категории, видимость, порядок отображения в портфолио и на главной странице) хранятся исключительно в PostgreSQL |
| **Публичный frontend не является SOT** | Public сайт отображает карточки, но не определяет их содержание |
| **Статический HTML не хранит канонические данные карточек** | HTML-страницы портфолио не являются источником правды для карточек в каталоге |
| **Public frontend получает карточки через read-only API backend** | Vanilla frontend загружает список карточек с backend при открытии страницы. Каталог портфолио и главная страница используют один endpoint, но разные поля сортировки |
| **Административная консоль — единственный интерфейс управления** | Создание, редактирование и удаление карточек выполняются только через `/admin/knowledge-base/project-cards` |
| **Изменения отображаются автоматически** | После сохранения карточки в админке public сайт отображает актуальные данные без ручного редактирования HTML |
| **`display_order` управляет порядком в каталоге портфолио** | Поле `display_order` определяет порядок всех видимых карточек на странице `portfolio.html` |
| **`show_on_homepage` управляет отображением на главной** | Поле `show_on_homepage` принимает значения `0..4`. `0` — не отображать на главной; `1..4` — порядок отображения на `index.html` слева направо |

### Границы

- Правило относится **только к карточкам проектов и их отображению в публичной части сайта**.
- **Public frontend остаётся на Vanilla HTML/CSS/JavaScript.**
- **Страницы отдельных кейсов остаются статическими HTML-страницами.** Они содержат Narrative Blueprint и не управляются через карточки.
- **Каталог портфолио и главная страница отображают карточки из одного read-only API, но используют разные поля сортировки:** `display_order` для портфолио, `show_on_homepage` для главной.
- ProjectCard не заменяет и не редактирует Narrative Blueprint и Presentation Patterns.

---

## Архитектура Knowledge Base

### Источники данных

AI Portfolio использует три уровня источников данных с чётким разделением ролей.

| Источник | Роль | Source of Truth |
|----------|------|-----------------|
| **GitHub** | Проектная документация | ✅ Да. Основной источник знаний для AI-ассистента |
| **PostgreSQL** | Управляемые данные сайта, эксплуатационные данные, журналы, диалоги, параметры LLM-провайдеров | ✅ Да |
| **ChromaDB** | Векторный поисковый индекс | ❌ Нет. Может быть полностью перестроена из актуальных источников |

### Правила первой версии административной консоли

- GitHub остаётся Source of Truth для проектной документации.
- **Временное техническое решение v1:** локальный файл `knowledge_base/knowledge.json` используется как источник для ручной синхронизации в ChromaDB, пока не реализован GitHub Sync.
- Административная консоль управляет перечнем подключённых источников и инициирует их синхронизацию вручную.
- Автоматическая синхронизация по webhook **не входит в первую версию**.
- PostgreSQL не является основным хранилищем проектной документации.
- ChromaDB остаётся только производным индексом и может быть полностью перестроена из актуальных источников.

---

## Narrative Blueprint и Presentation Patterns

### Разделение ролей

| Артефакт | Отвечает за |
|----------|------------|
| **Narrative Blueprint** | Что рассказывает страница проекта, порядок раскрытия материала, драматургию проекта |
| **Presentation Patterns** | Как эта информация отображается пользователю |

### Границы административной консоли

- Административная консоль **не редактирует Narrative Blueprint**.
- Административная консоль **не редактирует библиотеку Presentation Patterns**.
- Административная консоль работает только с управляемым контентом внутри уже утверждённой структуры.

### Порядок разработки кейсов

При разработке нового кейса сначала разрабатывается Narrative Blueprint. После этого Narrative реализуется посредством выбора и применения Presentation Patterns.

---

## Key Technology Areas

### Подтверждённые технологии

| Область | Решение |
|---------|---------|
| **AI-провайдер** | OpenAI (основной), GigaChat (fallback) |
| **Backend Framework** | FastAPI |
| **База данных** | PostgreSQL |
| **RAG-движок** | ChromaDB |
| **Embeddings** | OpenAI text-embedding-3-small |
| **LLM Provider** | OpenAI GPT-4.1-mini |
| **Хостинг** | Существующий VPS |
| **Поддержка** | Владелец проекта |

### Требующие определения

| Область | Статус |
|---------|--------|
| **Frontend** | ✅ Vanilla HTML/CSS/JS (инженерный минимализм) |
| **Admin Console** | ✅ Архитектура определена и реализована (Stage 4 завершён) |

### Backend (AI Assistant)

| Компонент | Технология | Решение |
|-----------|------------|---------|
| **Web Framework** | FastAPI | Адаптировано из PEcf11, Review Flow |
| **RAG Engine** | ChromaDB | Адаптировано из PEcf09 |
| **Embeddings** | OpenAI text-embedding-3-small | Адаптировано из PEcf09, PEcf11 |
| **LLM Provider** | OpenAI GPT-4.1-mini | Адаптировано из Review Flow |
| **Memory** | PostgreSQL | Адаптировано из Assistant Flow |
| **Knowledge Base v1** | `knowledge_base/knowledge.json` + ChromaDB | Временный источник (`knowledge.json`) до реализации GitHub Sync; ChromaDB — производный индекс |
| **Logging** | PostgreSQL | Адаптировано из PEcf09, Assistant Flow, Review Flow |
| **Cache** | JSON-файл | Адаптировано из PEcf09 |
| **LLM Provider Settings** | PostgreSQL (`ai_provider_settings`) | Source of Truth для параметров провайдеров; API keys только в `.env` |

---

## Decision

**Принято:** Персональный сайт AI-инженера с AI-ассистентом как функцией сайта.

**Основные решения:**
- Сайт — главная точка входа
- Telegram — вспомогательный канал связи
- OpenAI — основной AI-провайдер
- GigaChat — fallback AI-провайдер
- PostgreSQL — основная СУБД, включая Source of Truth для параметров LLM-провайдеров
- VPS — платформа для эксплуатации
- Владелец — ответственный за поддержку и базу знаний

---

## Next Steps

1. ~~Аудит входных материалов~~ — ✅ Выполнено
2. ~~Получение решений владельца~~ — ✅ Выполнено
3. ~~Создание PROJECT_STATE.md~~ — ✅ Выполнено
4. ~~Аудит branding-материалов~~ — ✅ Выполнено
5. ~~Создание SPEC.md~~ — ✅ Выполнено
6. ~~Решение открытых вопросов~~ — ✅ Выполнено
7. ~~Создание IMPLEMENTATION_PLAN.md~~ — ✅ Выполнено
8. ~~Согласование плана с владельцем~~ — ✅ Выполнено
9. ~~Этап 0: Подготовка~~ — ✅ Выполнено
10. ~~Этап 1: Пользовательский интерфейс~~ — ✅ Выполнено
11. ~~Этап 2: Деплой пользовательского интерфейса~~ — ✅ Выполнено
12. ~~Этап 3: Серверный компонент~~ — ✅ Выполнено
13. ~~Этап 4: Интеграция~~ — ✅ Выполнено
14. ~~Этап 5: Публикация в Git~~ — ✅ Выполнено. Проект находится под управлением Git.
15. **Актуализация Source of Truth административной консоли** — ✅ Выполнено
16. **Административная консоль (Stage 4)** — ✅ Реализована и развёрнута: Dashboard, Content / Knowledge Base, Logs / Conversations
17. **Управление параметрами LLM-провайдеров через админку** — ✅ Реализовано (2026-07-18). БД — единый SOT для model, temperature, max_tokens, base_url, enabled, active, fallback.
18. **Execution Tracing для панели «Логи»** — ✅ Реализовано (2026-07-18). Таблицы `execution_sessions`/`execution_steps`, миграции 007/008/009 (+ флаг `is_backfilled`), сервис `ExecutionTracingService`, endpoints `/admin/execution-sessions`. Operational console «Логи» в стиле Assistant Flow использует `/admin/execution-sessions` и `/admin/execution-sessions/{id}`. `PAGE_SIZE=7`, query preview для backfill'нутых сессий, компактная метка "приблизительный" для backfill'нутых сессий. Прошёл production smoke-test.
19. **Аудит входа в админку и посещений сайта** — ✅ Реализовано (2026-07-19). Endpoints `POST /admin/login` и `POST /track-visit`, записи `admin_login` / `site_visit` в `operational_logs`, миграция 010 (индекс `event_type` + `status`), вкладка «Аудит» в `LogsPage.tsx`, интеграция трекинга в публичный frontend. `npm run build` и `python -m py_compile` проходят.
20. **Архитектурное упрощение логирования chat pipeline** — ✅ Реализовано (2026-07-19). `chat_request` больше не дублируется в `operational_logs`; `execution_sessions` — единый SOT для chat pipeline. Добавлены `visitor_id`, `client_ip`, `user_agent` в `ExecutionSession` (миграция 011). Публичный frontend передаёт `visitor_id` в `POST /chat`. Вкладка «Execution-сессии» отображает visitor-реквизиты; вкладка «Аудит» содержит только системные события (`admin_login`, `site_visit`, `provider_switch`).
21. **Переработка страницы «Диалоги» в стиле Assistant Flow Memory Console** — ✅ Реализовано (2026-07-19). Backend: расширены `GET /admin/conversations` и `GET /admin/conversations/{id}` в `LogsConversationsService` (фильтры, runtime context, turns, executions, budget). Frontend: полностью заменён `ConversationsPage.tsx` на двухпанельный operational layout. `npm run build` и `python -m py_compile` проходят; остаётся production deploy и smoke-test.
22. **Deployment Validation** — ⏳ Будет проведён по решению владельца проекта перед финальной публикацией

---

## Status History

| Дата | Статус | Примечание |
|------|--------|----------|
| 2026-07-12 | Input Materials Audit | Аудит и нормализация входных материалов |
| 2026-07-12 | SOT Received | Получены решения владельца продукта |
| 2026-07-12 | SPEC Phase | Начало подготовки продуктовой спецификации |
| 2026-07-12 | PROJECT_STATE Created | Зафиксированы решения SOT |
| 2026-07-12 | SPEC Created | Создана продуктовая спецификация |
| 2026-07-12 | All Questions Resolved | Все открытые вопросы закрыты решениями владельца |
| 2026-07-12 | IMPLEMENTATION_PLAN Created | Создан план реализации |
| 2026-07-12 | Ready for Implementation | Готов к реализации |
| 2026-07-13 | UI Implementation Complete | Пользовательский интерфейс реализован |
| 2026-07-13 | Deployed to Production | Сайт развёрнут на VPS по адресу https://ai.alex-n8n.site |
| 2026-07-13 | Stage 1 Complete | Этап 1 завершён |
| 2026-07-13 | Architecture Defined | Зафиксирована архитектура представления проектов: Narrative Blueprint (уровень кейса) + Presentation Patterns (уровень APL) |
| 2026-07-14 | Backend Architecture Defined | Архитектурная инвентаризация завершена. Приняты решения: FastAPI (PEcf11), ChromaDB (PEcf09), OpenAI GPT-4.1-mini, PostgreSQL для MVP. |
| 2026-07-14 | Admin Console Architecture Defined | Архитектурное решение: admin как отдельный React-модуль внутри AI Portfolio по маршруту /admin/. |
| 2026-07-14 | Backend & Chat Complete | Backend, RAG, кеширование, чат-ассистент и интеграция с frontend завершены. Сайт работает с AI-ассистентом. |
| 2026-07-15 | Engineering Preparation Complete | Актуализированы PROJECT_STATE.md, IMPLEMENTATION_PLAN.md, README.md. Docker-конфигурация приведена к единому виду. Репозиторий инициализирован. |
| 2026-07-15 | Admin Console Concept SOT | В Source of Truth зафиксированы границы первой версии административной консоли, архитектура Knowledge Base и роль Narrative Blueprint / Presentation Patterns. |
| 2026-07-15 | Admin Console Architecture Finalized | Утверждена и зафиксирована окончательная техническая архитектура первой версии административной консоли в `docs/ADMIN_CONSOLE_ARCHITECTURE.md`. |
| 2026-07-15 | Admin Console Implementation Plan Fixed | Технический план реализации административной консоли зафиксирован в `docs/IMPLEMENTATION_PLAN.md`. |
| 2026-07-15 | ProjectCard SOT Defined | В Source of Truth зафиксировано, что `ProjectCard` в PostgreSQL является единственным Source of Truth карточек проектов; public frontend получает карточки через read-only API. |
| 2026-07-15 | Admin Console Stage 4 Complete | Реализованы три рабочих пространства административной консоли: Dashboard, Content / Knowledge Base, Logs / Conversations. Production smoke-test пройден без регрессий. |
| 2026-07-18 | LLM Provider Settings SOT | Параметры LLM-провайдеров перенесены в PostgreSQL (`ai_provider_settings`) и управляются через Dashboard административной консоли. API-ключи остаются в `.env`. |
| 2026-07-18 | ProjectCards Operational Panel | Страница управления карточками проектов превращена в операционную панель (двухпанельный layout, toolbar в шапке страницы, макропанели, чанки ChromaDB). Добавлен endpoint `/admin/knowledge-base/project-cards/{id}/chunks` и миграция 006 с `created_at`/`updated_at`. `ADMIN_CONSOLE_ARCHITECTURE.md` и `IMPLEMENTATION_PLAN.md` актуализированы. |
| 2026-07-18 | Execution Tracing Implemented | Реализовано и развёрнуто execution tracing для панели «Логи»: модели `ExecutionSession`/`ExecutionStep`, миграции 007, 008 и 009 (backfill 38 сессий / 328 шагов + флаг `is_backfilled`), сервис `ExecutionTracingService`, интеграция в `ChatOrchestrator`, endpoints `/admin/execution-sessions`. Operational console «Логи» в стиле Assistant Flow использует `/admin/execution-sessions` и `/admin/execution-sessions/{id}`. Query preview для backfill'нутых сессий; компактная метка "приблизительный" для backfill'нутых сессий. `PAGE_SIZE=7`. Прошёл production smoke-test: chat запросы создают execution-сессии с 11 шагами; cache hit корректно отмечает skipped шаги. |
| 2026-07-19 | Audit Logging Implemented | Реализован аудит входа в административную консоль и посещений публичного сайта: endpoints `POST /admin/login` и `POST /track-visit`, записи `admin_login` / `site_visit` в `operational_logs`, миграция 010 (индекс `event_type` + `status`), вкладка «Аудит» в `LogsPage.tsx`, интеграция трекинга в публичный frontend. `npm run build` и `python -m py_compile` проходят. |
| 2026-07-19 | Chat Logging Simplified | Архитектурное упрощение логирования chat pipeline: `chat_request` больше не дублируется в `operational_logs`; `execution_sessions` — единый SOT. Добавлены `visitor_id`, `client_ip`, `user_agent` в `ExecutionSession` (миграция 011). Публичный frontend передаёт `visitor_id` в `POST /chat`. Вкладка «Execution-сессии» отображает visitor-реквизиты; вкладка «Аудит» содержит только системные события (`admin_login`, `site_visit`, `provider_switch`). |
| 2026-07-19 | Conversations Page Redesign | Переработана страница «Диалоги» в стиле Assistant Flow Memory Console: двухпанельный layout, фильтры по времени/режиму/активности/поиску, список сессий с runtime context, detail panel с парными turns, execution timeline и JSON snapshot. Backend: расширены `GET /admin/conversations` и `GET /admin/conversations/{id}`. Frontend: полностью заменён `ConversationsPage.tsx`. `npm run build` и `python -m py_compile` проходят. |
| 2026-07-19 | Conversations UI Finalization | Доводка UI страницы «Диалоги»: убрана лишняя строка статуса над макропанелями; панель диалога занимает основное пространство правой панели; заголовок сводки изменён на «Сводка диалоговой сессии»; панель «Runtime memory context» переименована в «Параметры исполнения»; cache hit и response time отображаются в таблице диалога как колонки на уровне turn; execution timeline по умолчанию свёрнут; исправлен backend-баг чтения cache_hit из execution_metadata. `npm run build` и `python -m py_compile` проходят. |
| 2026-07-19 | Logs UI Finalization | Доводка UI страницы «Логи»: правая макропанель Execution-сессии разделена на «Параметры сессии» и «Параметры исполнения»; убраны лишние строки статуса (время МСК, TEXT OK / RAG OK); унифицированы отступы между заголовками панелей и параметрами. |
