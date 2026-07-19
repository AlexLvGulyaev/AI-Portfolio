# Административная консоль AI Portfolio — Техническая архитектура v1

**Проект:** ai-portfolio
**Дата:** 2026-07-15
**Статус:** Согласовано
**Версия:** 1.1

---

## 1. Контекст

### 1.1. Исходные документы (SOT)

| Документ | Назначение |
|----------|------------|
| `docs/PROJECT_STATE.md` | Решения владельца продукта, включая границы первой версии административной консоли и архитектуру Knowledge Base |
| `docs/SPEC.md` | Продуктовая спецификация, разделы об административной консоли |
| `docs/IMPLEMENTATION_PLAN.md` | Последовательность реализации административной консоли (раздел 11) |

### 1.2. Фактическое состояние системы

| Компонент | Технологии | Расположение |
|-----------|-----------|--------------|
| Public frontend | Vanilla HTML + CSS + JavaScript | `src/` |
| Backend | FastAPI + PostgreSQL + ChromaDB HTTP client | `backend/` |
| ChromaDB | Официальный сервер `chromadb/chroma:0.5.23` | `docker-compose.yml` сервис `ai-portfolio-chroma` |
| Reverse proxy / static server | nginx в Docker | `src/nginx.conf`, `src/Dockerfile` |
| Orchestration | Docker Compose v2 | `docker-compose.yml` |

### 1.3. Принципы архитектуры первой версии

| # | Принцип | Обоснование |
|---|---------|-------------|
| 1 | **Пять разделов навигации, сгруппированных по функциям** | Системные настройки, Контент / База знаний (3 подраздела: карточки, источники, синхронизация), Логи, Диалоги |
| 2 | **Public frontend остаётся без изменений** | Утверждено владельцем: vanilla HTML/CSS/JS |
| 3 | **Backend остаётся единым FastAPI** | Утверждено владельцем: admin endpoints расширяют существующее приложение |
| 4 | **Минимальная сложность сопровождения** | AI Portfolio — личный сайт, а не корпоративная платформа; избыточные абстракции не нужны |
| 5 | **ChromaDB — только поисковый индекс** | Утверждено владельцем: управляемые данные живут в PostgreSQL, документация — в GitHub |
| 6 | **Простая аутентификация, без RBAC** | v1 управляется одним владельцем; JWT/RBAC избыточны |
| 7 | **Переиспользовать только нужное** | Предпочтение — собственным сервисам AI Portfolio; каркас UI из Assistant Flow; специфика других продуктов не переносится |

---

## 2. Backend административной части

### 2.1. Структура

```
backend/app/
├── api/
│   ├── __init__.py
│   ├── chat.py                  # Существующий публичный API
│   ├── health.py                # Существующий health
│   └── admin/                   # Новый пакет административных endpoints
│       ├── __init__.py
│       ├── dependencies.py      # Аутентификация admin
│       ├── dashboard.py         # Dashboard: сводные метрики
│       ├── knowledge_base.py    # Content/KB: источники, карточки проектов, синхронизация
│       ├── logs.py              # Logs: operational logs (совместимость)
│       ├── conversations.py     # Conversations: сессии и сообщения
│       └── execution_sessions.py # Logs: execution tracing
├── services/
│   ├── ...                      # Существующие сервисы
│   │   ├── execution_tracing_service.py  # Execution tracing для ChatOrchestrator
│   └── admin/
│       ├── dashboard_service.py
│       ├── knowledge_base_service.py
│       ├── logs_conversations_service.py
│       └── execution_sessions_service.py
├── models/
│   └── entities.py              # Расширяется моделями ProjectCard, KnowledgeSource, KnowledgeSyncJob, ExecutionSession, ExecutionStep
└── main.py                      # Подключает admin routers с префиксом /admin
```

### 2.2. Admin endpoints

Все endpoints регистрируются в FastAPI с префиксом `/admin`. nginx проксирует `/api/admin/` → backend `/admin/`.

#### Dashboard

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/admin/dashboard` | Сводные метрики: провайдеры, KB, логи, диалоги, системный статус |

#### Content / Knowledge Base

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/admin/knowledge-base/status` | Статус ChromaDB: количество чанков, модель эмбеддингов, дата последней синхронизации |
| GET | `/admin/knowledge-base/sources` | Список подключённых источников |
| POST | `/admin/knowledge-base/sources` | Добавить источник |
| GET | `/admin/knowledge-base/sources/{id}` | Получить источник |
| PATCH | `/admin/knowledge-base/sources/{id}` | Обновить источник |
| DELETE | `/admin/knowledge-base/sources/{id}` | Удалить источник |
| POST | `/admin/knowledge-base/sync` | Запустить фоновую ручную синхронизацию источников → ChromaDB; возвращает `job_id` |
| GET | `/admin/knowledge-base/sync/{job_id}` | Статус фонового sync job |
| GET | `/admin/knowledge-base/project-cards` | Список управляемых карточек проектов |
| POST | `/admin/knowledge-base/project-cards` | Создать карточку проекта |
| GET | `/admin/knowledge-base/project-cards/{id}` | Получить карточку |
| PATCH | `/admin/knowledge-base/project-cards/{id}` | Обновить карточку |
| DELETE | `/admin/knowledge-base/project-cards/{id}` | Удалить карточку |
| GET | `/admin/knowledge-base/project-cards/{id}/chunks` | Чанки ChromaDB, относящиеся к карточке проекта |

#### Logs / Conversations

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/admin/logs` | Список operational logs с фильтрами (оставлен для совместимости) |
| GET | `/admin/execution-sessions` | Список execution-сессий с фильтрами и пагинацией |
| GET | `/admin/execution-sessions/{id}` | Детали execution-сессии + шаги pipeline + связанный operational log |
| GET | `/admin/conversations` | Список chat sessions с фильтрами (hours, route последнего execution, active_only, search), message_count, turns_approx, visitor_id, last_execution summary |
| GET | `/admin/conversations/{id}` | Детали сессии: параметры, сообщения, парные turns, параметры исполнения, memory budget, связанные execution-сессии со steps, JSON snapshot |

#### AI Providers (управляется из Dashboard)

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/admin/ai-providers` | Список провайдеров с параметрами из БД |
| PATCH | `/admin/ai-providers/{provider_key}` | Изменить model, temperature, max_tokens, base_url, enabled |
| POST | `/admin/ai-providers/{provider_key}/activate` | Сделать провайдер активным |
| POST | `/admin/ai-providers/{provider_key}/set-fallback` | Назначить fallback-провайдером |
| POST | `/admin/ai-providers/{provider_key}/test` | Проверить соединение с провайдером |

### 2.3. Аутентификация

```
ADMIN_API_TOKEN=<единый токен из .env>
```

- Backend-зависимость `require_admin` проверяет заголовок `Authorization: Bearer <token>`.
- Frontend хранит токен в `localStorage` для v1.
- Нет users table, RBAC, JWT refresh.

### 2.4. Conversations / Диалоги

Страница «Диалоги» (`/admin/conversations`) переработана по образцу операционной консоли Memory Assistant Flow: двухпанельный `logs-console` layout, фильтры, список сессий слева и детальная сводка справа.

#### Backend

| Endpoint | Назначение |
|----------|------------|
| `GET /admin/conversations` | Список `ChatSession` с пагинацией. Query params: `hours`, `route` (route последнего `ExecutionSession`), `active_only`, `search`. Поля ответа: `id`, `user_id`/`visitor_id`, `mode`, `is_active`, `created_at`, `updated_at`, `message_count`, `turns_approx`, `last_execution` (runtime context). |
| `GET /admin/conversations/{id}` | Детали сессии: параметры, полный список сообщений (лимит 500), `recent_turns` (парные user/assistant), связанные `ExecutionSession` со steps (лимит 20), `budget` из `MemoryBudgetPolicy`, `memory_source`. |

Сервис: `app/services/admin/logs_conversations_service.py`.

#### Frontend

| Компонент | Назначение |
|-----------|------------|
| `ConversationsPage.tsx` | Двухпанельный layout с фильтрами (окно времени, режим/route, активность, поиск), списком сессий, keyboard navigation, auto-select. |
| `OperationalModalityBadge` | Badge режима (mem/rag/text/...). |
| `OperationalPipelineStageIcon` | Иконка статуса шага pipeline. |
| `SessionJsonSnapshot` | Раскрывающийся JSON snapshot детализации. |

#### Параметры исполнения (last_execution)

`last_execution` берётся из последнего `ExecutionSession` для сессии и дополняется:
- `rag_used` — `route == 'rag'` или флаг из `execution_metadata`;
- `provider_key` / `model_name` / `status` — прямые поля `ExecutionSession`;
- `cache_hit` — из `OperationalLog.from_cache` для этого execution, либо из `execution_metadata.cache_hit`;
- `response_time_ms` — `ExecutionSession.duration_ms` или `execution_metadata.response_time_ms`.

Cache hit и response time — это свойства конкретного execution (запуска обработки запроса), а не диалоговой сессии в целом. Поэтому в сводке сессии они вынесены из верхних макропанелей и показаны в таблице диалога как дополнительные колонки для каждого turn (по execution-сессии, связанной с ответом ассистента).

В правой макропанели «Диалоги» три блока:
- **Параметры сессии** — session_id, visitor IP, режим, активность, сообщения, turns, обновлена;
- **Параметры исполнения** — RAG, provider/model, source, response time последнего запуска;
- **Memory policy / limits** — max_recent_messages, max_message_chars, total_memory_chars_budget.

Заголовок правой макропанели: «Сводка диалоговой сессии».

#### Memory policy

Лимиты возвращаются из `MemoryBudgetPolicy` (`app/services/memory/base.py`):
- `max_recent_messages` — 50;
- `max_message_chars` — 8000;
- `total_memory_chars_budget` — 32000.

`memory_source` всегда `"PostgreSQL"`, т.к. в AI Portfolio нет in-memory fallback для диалогов.

### 2.4. Модели данных

#### ProjectCard

| Поле | Тип | Назначение |
|------|-----|------------|
| id | UUID, PK | Идентификатор |
| slug | string, unique | machine id: assistant-flow, review-flow и т.п. |
| title | string | Заголовок |
| short_description | text | Краткое описание |
| category | string | cases / services / technologies |
| tags | JSON/array | Теги |
| display_order | int | Порядок отображения в каталоге портфолио |
| show_on_homepage | int | Порядок отображения на главной странице; `0` — не отображать |
| is_visible | bool | Видимость на сайте |
| knowledge_content | text | Полный текст для индексации в ChromaDB |
| external_url | string | Ссылка на страницу кейса |
| created_at / updated_at | datetime | Служебные |

**ProjectCard является единственным Source of Truth карточек проектов.** Публичный frontend не хранит канонические данные карточек в статическом HTML и получает их через read-only API backend.

#### KnowledgeSource

| Поле | Тип | Назначение |
|------|-----|------------|
| id | UUID, PK | Идентификатор |
| source_type | enum | github_repo / local_directory / local_file |
| identifier | string | owner/repo или путь |
| branch | string, nullable | Для github_repo |
| base_path | string, nullable | Подпуть внутри репозитория |
| is_enabled | bool | Активен ли источник |
| last_sync_at | datetime, nullable | Время последней синхронизации |
| last_sync_status | string | pending / success / error |
| last_sync_error | text, nullable | Ошибка последней синхронизации |
| created_at / updated_at | datetime | Служебные |

#### KnowledgeSyncJob (опционально, но рекомендуется)

| Поле | Тип | Назначение |
|------|-----|------------|
| id | UUID, PK | Идентификатор |
| triggered_by | string | manual / future_scheduler |
| status | string | Статус выполнения |
| started_at / finished_at | datetime | Время |
| stats | JSON | documents_processed, chunks_created, errors |
| error_message | text, nullable | Ошибка |

### 2.5. Execution Tracing

Execution Tracing — реализованная подсистема детального наблюдения за прохождением запроса через pipeline `ChatOrchestrator`. Поддерживает operational console «Логи» в стиле Assistant Flow.

#### Назначение

- Фиксировать каждый этап обработки chat-запроса с таймстемпами и статусом.
- Связывать сводный `operational_logs` с детальной трассировкой.
- Показывать в админке таймлайн pipeline, запрос/ответ и метаданные.

#### Модель данных

| Таблица | Назначение | Source of Truth |
|---------|-----------|-----------------|
| `operational_logs` | Сводное событие (query, response, provider, latency, status) | ✅ Да |
| `execution_sessions` | Одна обработка запроса: route, status, duration, provider/model, metadata | ✅ Да |
| `execution_steps` | Шаги pipeline внутри execution_sessions | ✅ Да |

Связи:
- `operational_logs.execution_id` → `execution_sessions.id` (nullable, 0..1)
- `execution_sessions.session_id` → `chat_sessions.id` (nullable)
- `execution_steps.execution_session_id` → `execution_sessions.id` (one-to-many)

#### Шаги pipeline (execution_steps)

| Порядок | stage_name | Условие |
|---------|-----------|---------|
| 1 | `session_resolve` | Всегда |
| 2 | `memory_load` | Всегда |
| 3 | `cache_check` | Всегда |
| 4 | `rag_search` | Только если выполнялся поиск в Knowledge Base |
| 5 | `prompt_build` | Всегда, кроме cache hit |
| 6 | `provider_select` | Всегда, кроме cache hit |
| 7 | `provider_switch` | Только если использовался fallback |
| 8 | `llm_call` | Если ответ не из кеша |
| 9 | `memory_save` | Всегда |
| 10 | `log_write` | Всегда |
| 11 | `response_return` | Всегда |

#### Route-маппинг

| Route | Источник |
|-------|----------|
| `text` | `chat_request` без `rag_used` |
| `rag` | `chat_request` с `rag_used=true`, либо отдельный `rag_query` |
| `log` | `provider_switch` |
| `image` / `audio` | Зарезервировано для будущих мультимодальных сценариев |

#### Миграция backfill

Миграция `008_backfill_execution_sessions` для существующих записей `operational_logs` без `execution_id` создаёт `execution_sessions` и базовые `execution_steps` на основе сохранённых metadata.

Миграция `009_add_is_backfilled` добавляет в `execution_sessions` поле `is_backfilled` и помечает `TRUE` все сессии, созданные в рамках backfill'а. Граница backfill'а определяется последней backfill'нутой сессией (`2960349e-48ed-4af6-9a48-344b9c27a4d5`). В frontend backfill'нутые сессии отображаются с меткой "приблизительный" у заголовка таймлайна: их `duration_ms` и дельты между шагами не отражают реальное время выполнения.

#### Интеграция с ChatOrchestrator

- `ExecutionTracingService` передаётся в `ChatOrchestrator` как опциональная зависимость.
- Каждый проход `process_request` создаёт одну `execution_session`.
- Каждый этап pipeline оборачивается в `start_step` / `finish_step`.
- Cache hit фиксирует шаги `rag_search`, `prompt_build`, `provider_select`, `provider_switch`, `llm_call` как `skipped`.
- Fallback фиксирует шаг `provider_switch` как `ok`.
- С 2026-07-18 шаги pipeline обогащаются `step_metadata` (`query`, `response`, `provider`, `model`, `latency_ms`, `rag_used`, `sources` и др.) для построения operational console в стиле Assistant Flow.
- С 2026-07-19 `chat_request` больше не дублируется в `operational_logs`. Execution-сессия является единым SOT для chat pipeline: `execution_metadata` содержит query, response, provider, model, rag_used, sources, error, response_time_ms. `ExecutionSession` хранит `visitor_id`, `client_ip`, `user_agent` для сквозной идентификации посетителя.
- `POST /chat` принимает `visitor_id` из публичного frontend и передаёт его в `ChatOrchestrator`.

#### Frontend operational console

`LogsPage.tsx` содержит две вкладки без дублирования:

- **Execution-сессии** — использует `/admin/execution-sessions` для списка сессий и `/admin/execution-sessions/{id}` для детального просмотра. Отображает только chat pipeline: паспорт сессии, visitor_id, client_ip, user_agent, цепочка этапов, таймлайн шагов pipeline, запрос/ответ из `execution_metadata`, JSON snapshot. Правая макропанель разделена на «Параметры сессии» и «Параметры исполнения»; лишние строки статуса (время МСК, TEXT OK / RAG OK) убраны.
- **Аудит** — использует `/admin/logs` для списка operational logs с фильтрами по `event_type` и `status`. Отображает только системные события без pipeline: `admin_login`, `site_visit`, `provider_switch`. `chat_request` и `rag_query` больше не отображаются здесь, потому что они полностью покрыты execution-сессиями.

#### Admin endpoints

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/admin/login` | Проверка `ADMIN_API_TOKEN` и запись `operational_log` с `event_type='admin_login'` |
| GET | `/admin/logs` | Список системных operational logs с фильтрами (event_type, status, date) |
| GET | `/admin/execution-sessions` | **Основной API для operational console «Логи»:** список execution-сессий chat pipeline с фильтрами route/status/date/search и пагинацией |
| GET | `/admin/execution-sessions/{id}` | Детали execution-сессии chat pipeline + шаги pipeline + запрос/ответ из `execution_metadata` |

#### Аудит входа в админку

Аутентификация остаётся stateless по единому `ADMIN_API_TOKEN`. Для фиксации факта входа добавлен `POST /admin/login`:

- `LoginPage.tsx` вызывает `POST /admin/login` до сохранения токена в `localStorage`.
- При валидном токене создаётся `operational_log` с `event_type='admin_login'`, `status='ok'`.
- При невалидном токене — `event_type='admin_login'`, `status='error'`, `error_message='Invalid admin token'`.
- Запрос фиксирует обезличенный `ip` и `user_agent` в `log_metadata`.

#### Аудит посещений публичного сайта

Для отслеживания посещений публичного сайта добавлен публичный endpoint `POST /track-visit`:

- Frontend публичного сайта (`src/js/api-client.js` + `src/js/main.js`) при загрузке каждой страницы вызывает `POST /track-visit` с `visitor_id` из `localStorage`.
- Если `visitor_id` отсутствует — генерируется UUID v4 и сохраняется.
- Endpoint пишет `operational_log` с `event_type='site_visit'`, `status='ok'`, `query=path`, `response=referrer`, `log_metadata={visitor_id, ip, user_agent}`.
- `nginx.conf` проксирует `/track-visit` на backend.
- В админке вкладка **Аудит** позволяет фильтровать и просматривать `site_visit` записи.

### 2.6. Переиспользуемые backend-компоненты

Уже существуют в AI Portfolio и не требуют копирования:

| Компонент | Путь | Использование в админке |
|-----------|------|--------------------------|
| AIProviderSettingsService | `services/ai_provider_settings_service.py` | Dashboard: статус провайдеров |
| OperationalLogService | `services/operational_log_service.py` | Logs workspace |
| ChatSessionService + SessionRepository | `services/chat_session_service.py`, `repositories/session_repository.py` | Conversations workspace |
| RAGService | `services/rag/rag_service.py` | KB status, ChromaDB stats, поиск чанков по метаданным |
| KnowledgeBaseService | `services/admin/knowledge_base_service.py` | ProjectCard chunks, статус KB |
| KnowledgeBaseIndexer | `services/rag/knowledge_base_indexer.py` | Ручная синхронизация KB |

### 2.6. Компоненты, которые не переносятся

| Компонент AF/RF | Почему не переносим |
|-----------------|---------------------|
| RBAC / `require_permission` / `PrincipalContext` (AF) | Избыточно для одного владельца |
| JWT auth из AF | Требует users table, refresh tokens, криптографию |
| AF `DocumentRepository` / хранение документов в БД | AI Portfolio не хранит документацию в PostgreSQL |
| AF `AdminService` с readiness/config checks | Завязан на конфигурацию Assistant Flow |
| AF `MemoryObservabilityService` | Покрывается существующими сессиями |
| AF assets / evaluation / retrieval endpoints | Специфика AF |
| RF candidate_admin, ch_analytics, reports, prompts | Специфика Review Flow |
| RF `settings_ai_providers.py` как отдельный API | Функциональность уже есть в `AIProviderSettingsService` |

---

## 3. Frontend административной части

### 3.1. Общее решение

- Отдельный React + TypeScript + Vite SPA в каталоге `admin/`.
- Не смешивается с public frontend `src/`.
- Каркас Layout, Navigation, ProtectedRoute, LoginPage и базовые UI-компоненты берутся из **Assistant Flow admin-ui**.
- Страницы под 3 рабочих пространства v1 реализуются заново.
- **Review Flow frontend не используется**: его компоненты ориентированы на provider/analytics/moderation, которые не входят в v1.

### 3.2. Структура

```
admin/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api/
    │   └── client.ts              # API client с Bearer-token
    ├── auth/
    │   └── auth.ts                # Хранение и проверка токена
    ├── components/                # Reusable UI
    │   ├── AdminLayout.tsx
    │   ├── Navigation.tsx
    │   ├── ProtectedRoute.tsx
    │   ├── StatusBadge.tsx
    │   ├── MetricCard.tsx
    │   ├── SectionCard.tsx
    │   ├── EmptyState.tsx
    │   ├── LoadingState.tsx
    │   └── OperationalList.tsx
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── DashboardPage.tsx
    │   ├── KnowledgeBasePage.tsx
    │   └── LogsConversationsPage.tsx
    ├── styles/
    │   └── globals.css            # Дизайн-система AI Portfolio
    └── utils/
        └── formatters.ts
```

### 3.3. Маршруты

| Путь | Страница | Тип |
|------|----------|-----|
| `/admin/login` | LoginPage | Публичная |
| `/admin/system` | DashboardPage | Защищённая |
| `/admin/content/cards` | ProjectCardsPage | Защищённая |
| `/admin/content/sources` | KnowledgeSourcesPage | Защищённая |
| `/admin/content/sync` | KnowledgeSyncPage | Защищённая |
| `/admin/logs` | LogsPage | Защищённая: operational console execution tracing |
| `/admin/conversations` | ConversationsPage | Защищённая |
| `/admin/` | redirect → `/admin/system` | — |

### 3.4. Компоненты новой разработки

| Компонент | Назначение |
|-----------|------------|
| `DashboardPage.tsx` | Метрики и настройки LLM-провайдеров |
| `ProjectCardsPage.tsx` | Операционная панель карточек проектов: список + детали |
| `KnowledgeSourcesPage.tsx` | CRUD источников Knowledge Base |
| `KnowledgeSyncPage.tsx` | Ручная синхронизация и статус ChromaDB |
| `LogsPage.tsx` | Operational logs с фильтрами |
| `ConversationsPage.tsx` | История диалогов |
| `Page.tsx` | Обёртка страницы; поддерживает `renderHeader` для кастомной шапки |
| `Modal.tsx` | Модальное окно создания/редактирования |
| `ConfirmDialog.tsx` | Диалог подтверждения удаления |
| `ProjectCardForm.tsx` | Форма карточки проекта |
| `globals.css` | Дизайн-система AI Portfolio |

---

## 4. Интеграция с Docker-инфраструктурой

### 4.1. Рекомендуемое решение

Единый nginx-контейнер, собирающий public frontend и admin frontend вместе.

### 4.2. Фактически внедрённое решение

Единый frontend-контейнер собирается из `src/Dockerfile` с build context в корне проекта.

| Файл | Изменение |
|------|-----------|
| `src/Dockerfile` | Multi-stage Dockerfile: Stage 1 собирает `admin/` через Node.js, Stage 2 копирует admin build в `/usr/share/nginx/html/admin/` и public static files в `/usr/share/nginx/html/` |
| `docker-compose.yml` | `ai-portfolio-frontend` собирается из корня проекта: `context: .`, `dockerfile: src/Dockerfile` |
| `src/nginx.conf` | Добавлены `location /admin/` (static SPA с fallback на `index.html`) и `location /api/admin/` (proxy_pass на `http://ai-portfolio-backend:8000/admin/`) |
| `admin/src/main.tsx` | `BrowserRouter` получил `basename="/admin"` для корректного роутинга SPA по маршруту `/admin/` |

### 4.3. Подтверждённая работоспособность

| Проверка | Результат |
|----------|-----------|
| `docker compose build ai-portfolio-frontend` | ✅ Успешно |
| `GET /admin/` через nginx | ✅ Возвращает admin `index.html` |
| `GET /admin/system` (обновление страницы) | ✅ Fallback на `index.html`, SPA маршрутизация работает |
| `GET /admin/content/cards` (обновление страницы) | ✅ Fallback на `index.html`, SPA маршрутизация работает |
| `GET /admin/assets/...` | ✅ Статика отдаётся |
| `GET /api/admin/dashboard` с токеном | ✅ Проксируется на backend `/admin/dashboard` |
| `GET /api/admin/dashboard` без токена | ✅ 403 |
| Публичные маршруты (`/`, `/chat`, `/health`, `/project-cards`) | ✅ Сохранены |

### 4.4. Отклонённая альтернатива

Отдельный Docker-сервис для admin frontend.

**Причина:** два nginx-контейнера усложняют маршрутизацию, деплой и Deployment Validation.

---

## 5. Взаимодействие GitHub / PostgreSQL / ChromaDB

```
GitHub (SOT проектной документации)
  │
  │  fetch по API (GitHub REST API, auth: token)
  ▼
GitHubKnowledgeSourceService
  │
  ├──► KnowledgeDocument / KnowledgeSyncError ──► PostgreSQL (SOT сырых документов)
  │
  └──► KnowledgeBaseService
            │
            ├──► ProjectCard / KnowledgeSource ──► PostgreSQL (SOT управляемых данных)
            │
            └──► KnowledgeBaseIndexer
                      │
                      ├── чанкинг
                      ├── embeddings (OpenAI)
                      └── запись в ChromaDB HTTP-сервер (поисковый индекс, не SOT)
```

**Фактическое техническое решение v1 (2026-07-19):**

GitHub Sync реализован. Ручная синхронизация `POST /admin/knowledge-base/sync` выполняется в фоновом thread:
1. Загружает `README.md` и `docs/**/*.md` из включённых источников `source_type=github_repo`.
2. Сохраняет сырые markdown-документы в `knowledge_documents` и ошибки в `knowledge_sync_errors`.
3. Конвертирует markdown → plain text через библиотеку `markdown`.
4. Перед индексацией каждого документа удаляет его старые чанки по `document_id`.
5. Индексирует GitHub-документы + `ProjectCard.knowledge_content` в ChromaDB.
6. Возвращает `job_id` для polling статуса через `GET /admin/knowledge-base/sync/{job_id}`.

**ChromaDB deployment:**
- Производственный контур использует отдельный сервис `ai-portfolio-chroma` (официальный образ `chromadb/chroma:0.5.23`).
- Backend подключается через `chromadb.HttpClient`.
- Причина перехода: embedded `PersistentClient` в backend-контейнере не выдерживает concurrent доступа из main thread (`/chat`) и фонового thread (sync), что приводит к повреждению индекса.

**Правила:**
- GitHub — Source of Truth для проектной документации.
- `knowledge_base/knowledge.json` больше не используется как источник.
- `ProjectCard` в PostgreSQL — **единственный Source of Truth карточек проектов**.
- ChromaDB перестраивается из актуальных источников и не является SOT.
- Автоматическая webhook-синхронизация не входит в v1.

---

## 6. Спорные места и компромиссы

| Место | Решение | Обоснование |
|-------|---------|-------------|
| ProjectCard в PostgreSQL vs статический HTML | `ProjectCard` в PostgreSQL, public frontend загружает карточки через read-only API | Соответствует SOT об управляемых данных. Public frontend не хранит канонические данные карточек в статическом HTML. |
| Ручная синхронизация | Запуск кнопкой в админке | Webhook вынесен за рамки v1 по SOT. |
| Простая auth по env-token | Единый `ADMIN_API_TOKEN` | v1 — один владелец; JWT/RBAC не окупаются. |
| React SPA для admin при vanilla public | Отдельный `admin/` | Сохраняем vanilla public frontend по SOT; получаем ускорение за счёт каркаса AF. |
| Отказ от RF frontend | Не используем компоненты RF | RF компоненты ориентированы на provider/analytics/moderation, не входящие в v1. |

---

## 7. Границы первой версии

### Входит

- Dashboard (Системные настройки): сводка + управление LLM-провайдерами.
- Content / Knowledge Base: управление карточками проектов, источниками KB, ручная синхронизация.
- Логи: operational console с execution tracing.
- Диалоги: история chat-сессий и сообщений.
- Управление карточками проектов.
- Управление источниками KB.
- Ручная синхронизация KB.
- **Execution Tracing для панели «Логи»: двухпанельный operational layout, таймлайн pipeline, фильтры по route/status/date/search.**

### Не входит

- Редактирование Narrative Blueprint.
- Редактирование Presentation Patterns.
- Визуальный конструктор страниц кейсов.
- Автоматическая webhook-синхронизация.
- Analytics как отдельное пространство (базовые метрики в Dashboard).
- Cache management как отдельное пространство.
- Health monitoring как отдельное пространство.
- RBAC / пользователи / JWT.

---

## 8. Рекомендации по порядку реализации

См. `docs/IMPLEMENTATION_PLAN.md`, раздел 11.

Кратко:
1. Backend Foundation — модели, миграции, auth, каркас routers.
2. Admin Frontend Foundation — Vite + React + TS каркас, Layout, Navigation, Login, ProtectedRoute.
3. Infrastructure Integration — Docker, nginx, `/admin/` и `/api/admin/`.
4. Реализация трёх рабочих пространств — Dashboard, Content/KB, Logs/Conversations.
5. Интеграция и тестирование — E2E, обновление документации.

Deployment Validation проводится отдельно по решению владельца проекта после завершения разработки.

---

## 9. История изменений

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2026-07-14 | 0.9 | Первый технический черновик на основе компонентов Assistant Flow и Review Flow. Содержал 9 рабочих пространств и неутверждённые технические детали. |
| 2026-07-15 | 1.0 | Актуализация под согласованную продуктовую концепцию: 3 рабочих пространства, минимальная сложность, единый env-token, отказ от RBAC/JWT, переход от Review Flow к собственным сервисам AI Portfolio + каркас AF. |
| 2026-07-18 | 1.1 | Расширение Dashboard управлением параметрами LLM-провайдеров (model, temperature, max_tokens, base_url, active/fallback) через новый admin endpoint `/admin/ai-providers`. Параметры провайдеров стали храниться в БД как Source of Truth. |
| 2026-07-18 | 1.2 | Execution Tracing для панели «Логи» реализовано и развёрнуто в production: модели `ExecutionSession` / `ExecutionStep`, миграции 007, 008 и 009 (backfill 38 сессий / 328 шагов + флаг `is_backfilled`), сервис `ExecutionTracingService`, интеграция с `ChatOrchestrator`, endpoints `/admin/execution-sessions`. Operational console «Логи» в стиле Assistant Flow использует `/admin/execution-sessions` и `/admin/execution-sessions/{id}`. Query preview для backfill'нутых сессий; компактная метка "приблизительный" для backfill'нутых сессий. Прошёл production smoke-test. Актуализирована структура навигации админки: Dashboard, Content (3 подраздела), Логи, Диалоги. |
| 2026-07-19 | 1.3 | Аудит входа в административную консоль и посещений публичного сайта: endpoints `POST /admin/login` и `POST /track-visit`, запись `admin_login` / `site_visit` в `operational_logs`, миграция 010 (индекс `event_type` + `status`), вкладка «Аудит» в `LogsPage.tsx`, интеграция трекинга в публичный frontend. |
| 2026-07-19 | 1.4 | Архитектурное упрощение логирования: `chat_request` больше не дублируется в `operational_logs`; `execution_sessions` является единым SOT для chat pipeline. Добавлены `visitor_id`, `client_ip`, `user_agent` в `ExecutionSession` (миграция 011). Публичный frontend передаёт `visitor_id` в `POST /chat`. Вкладки UI разделены без пересечения: «Execution-сессии» — chat pipeline, «Аудит» — системные события (`admin_login`, `site_visit`, `provider_switch`). |
| 2026-07-19 | 1.5 | Переработана страница «Диалоги» (`/admin/conversations`) по образцу Assistant Flow Memory Console: двухпанельный layout, фильтры по времени/режиму/активности/поиску, список сессий с runtime context, detail panel с парными turns, execution timeline и JSON snapshot. Backend: расширены `GET /admin/conversations` и `GET /admin/conversations/{id}` в `LogsConversationsService`. Frontend: полностью заменён `ConversationsPage.tsx`. `npm run build` и `python -m py_compile` проходят. |
| 2026-07-19 | 1.6 | Раздел 5 дополнен планом реализации GitHub Sync (Этап 11.11 IMPLEMENTATION_PLAN.md): загрузка `README.md` и `docs/*.md` из репозиториев APL на GitHub, промежуточное хранение в PostgreSQL, индексация в ChromaDB, UI в админке. |
| 2026-07-19 | 1.7 | GitHub Sync реализован и развёрнут в production: 7 источников, 192 документа, 5400 чанков. Раздел 5 переработан под фактическую архитектуру: `GitHubKnowledgeSourceService`, `KnowledgeDocument`, фоновый sync с `job_id`, инкрементальная очистка чанков по `document_id`. ChromaDB переведена на отдельный HTTP-сервис `ai-portfolio-chroma` для thread-safe concurrent доступа. |
