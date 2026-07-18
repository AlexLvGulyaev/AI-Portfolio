# Административная консоль AI Portfolio — Техническая архитектура v1

**Проект:** ai-portfolio
**Дата:** 2026-07-15
**Статус:** Согласовано
**Версия:** 1.0

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
| Backend | FastAPI + PostgreSQL + ChromaDB | `backend/` |
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
| POST | `/admin/knowledge-base/sync` | Запустить ручную синхронизацию источников → ChromaDB |
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
| GET | `/admin/conversations` | Список chat sessions с фильтрами |
| GET | `/admin/conversations/{id}` | Детали сессии + сообщения |

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

#### Интеграция с ChatOrchestrator

- `ExecutionTracingService` передаётся в `ChatOrchestrator` как опциональная зависимость.
- Каждый проход `process_request` создаёт одну `execution_session`.
- Каждый этап pipeline оборачивается в `start_step` / `finish_step`.
- Cache hit фиксирует шаги `rag_search`, `prompt_build`, `provider_select`, `provider_switch`, `llm_call` как `skipped`.
- Fallback фиксирует шаг `provider_switch` как `ok`.
- После записи `operational_log` выполняется `link_operational_log`.
- С 2026-07-18 шаги pipeline обогащаются `step_metadata` (`query`, `response`, `provider`, `model`, `latency_ms`, `rag_used`, `sources` и др.) для построения operational console в стиле Assistant Flow.

#### Admin endpoints

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/admin/logs/recent` | Плоские строки execution tracing для operational console (limit/offset/since_hours) |
| GET | `/admin/execution-sessions` | (legacy) Список execution-сессий с фильтрами route/status/date/search и пагинацией |
| GET | `/admin/execution-sessions/{id}` | (legacy) Детали сессии + шаги pipeline + связанный operational log |

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
  │  fetch по API (GitHub Sync — планируется)
  ▼
KnowledgeBaseService
  │
  ├──► ProjectCard / KnowledgeSource ──► PostgreSQL (SOT управляемых данных)
  │
  └──► KnowledgeBaseIndexer
            │
            ├── чанкинг
            ├── embeddings (OpenAI)
            └── запись в ChromaDB (поисковый индекс, не SOT)
```

**Текущее техническое решение v1:**

Поскольку GitHub Sync ещё не реализован, ручная синхронизация `POST /admin/knowledge-base/sync` использует локальный файл `knowledge_base/knowledge.json` как временный источник документации для индексации в ChromaDB. Поле `knowledge_content` карточек `ProjectCard` также участвует в индексации. GitHub остаётся архитектурным Source of Truth для проектной документации; `knowledge.json` — временный источник до появления GitHub Sync.

**Правила:**
- GitHub остаётся Source of Truth для проектной документации.
- **Временное техническое решение v1:** локальный `knowledge_base/knowledge.json` используется как источник для ручной синхронизации в ChromaDB, пока не реализован GitHub Sync.
- `ProjectCard` в PostgreSQL — **единственный Source of Truth карточек проектов**.
- Публичный frontend получает карточки проектов через **read-only API backend** и не хранит канонические данные в статическом HTML.
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
| 2026-07-18 | 1.2 | Execution Tracing для панели «Логи» реализовано и развёрнуто в production: модели `ExecutionSession` / `ExecutionStep`, миграции 007 и 008 (backfill 38 сессий / 328 шагов), сервис `ExecutionTracingService`, интеграция с `ChatOrchestrator`, endpoints `/admin/execution-sessions`, двухпанельный operational layout в `LogsPage`. Прошёл production smoke-test. Актуализирована структура навигации админки: Dashboard, Content (3 подраздела), Логи, Диалоги. |
