# IMPLEMENTATION_PLAN.md — План реализации первой версии

**Проект:** ai-portfolio
**Версия:** 1.0
**Дата:** 2026-07-12
**Статус:** Завершён в объёме уроков Prompt Engineering. Проект находится под управлением Git, репозиторий инициализирован.

---

## 1. Обзор плана

### Исходные документы (SSOT)

| Документ | Назначение |
|----------|------------|
| `docs/PROJECT_STATE.md` | Решения владельца продукта |
| `docs/SPEC.md` | Продуктовая спецификация |

### Продукт первой версии

Персональный сайт AI-инженера с интегрированным AI-ассистентом и административной консолью v1.

**Состав:**
- Сайт-портфолио (4 страницы)
- 7 страниц кейсов
- AI-ассистент (интеграция с сайтом)
- База знаний о кейсах и услугах
- Каналы связи (Telegram, Email)
- Административная консоль v1 (Dashboard, Content / Knowledge Base, Logs / Conversations)

**Не входит:**
- Страница «О себе» (представление на главной)
- Форма обратной связи
- Telegram-бот
- Расширенные рабочие пространства админ-консоли (Providers, Analytics, Cache, Health)
- GitHub Sync как автоматическая синхронизация (webhook)

### Существующая инфраструктура APL

| Ресурс | Описание | Использование |
|--------|----------|---------------|
| **VPS** | Существующий сервер | Деплой проекта |
| **PostgreSQL** | База данных | Основное серверное хранилище проекта |
| **Домены** | Управление доменами | Привязка домена к проекту |
| **GitHub** | Репозитории кейсов | Публикация проекта |
| **Deployment Validation** | Отлаженный процесс | Валидация деплоя |
| **Существующие кейсы** | 7 production-ready проектов | Контент для портфолио |

---

## 2. Этапы реализации

### Диаграмма этапов

```mermaid
flowchart LR
    E0[Этап 0: Подготовка] --> E1[Этап 1: Пользовательский интерфейс]
    E1 --> E2[Этап 2: Деплой пользовательского интерфейса]
    E2 --> E7[Этап 7: Архитектура представления]
    E2 --> E3[Этап 3: Серверный компонент]
    E7 --> E4[Этап 4: Интеграция]
    E3 --> E4
    E4 --> E5[Этап 5: Deployment Validation]
    E5 -.-> E6[Этап 6: Административная консоль v1]
    E6 -.-> E7B[Этап 7+: Следующее развитие]
```

**Примечание:** Административная консоль v1 была реализована в рамках текущей итерации после завершения базового продукта. Пунктирные линии показывают, что это развитие, а не часть первоначального критического пути.

---

## 3. Этап 0: Подготовка

**Статус:** ✅ Завершён

### Цель

Подготовить все необходимые материалы для начала разработки: контент, дизайн, базу знаний.

### Результат

| Артефакт | Содержание | Статус |
|----------|------------|--------|
| Тексты главной | Представление владельца, призыв к действию | ✅ |
| Описания кейсов | 7 файлов с описаниями | ✅ |
| Описание услуг | Текст для раздела «Услуги» | ✅ |
| Контакты | Telegram username, Email | ✅ |
| База знаний | JSON-файл для AI-ассистента | ✅ |
| Стилевая концепция | Цвета, шрифты, компоновка | ✅ |

---

## 4. Этап 1: Пользовательский интерфейс

**Статус:** ✅ Завершён (2026-07-13)

### Цель

Реализовать пользовательский интерфейс сайта-портфолио.

### Результат

| Артефакт | Содержание |
|----------|------------|
| Пользовательский интерфейс | 4 страницы + 7 страниц кейсов = 11 страниц |
| Исходный код | `src/` — vanilla HTML/CSS/JS |
| Локальная версия | Работающий сайт на localhost |
| Продакшн версия | Работающий сайт на VPS по адресу https://ai.alex-n8n.site |

### Критерии завершения

- [x] Главная страница отображается корректно
- [x] Все 7 кейсов отображаются в каталоге
- [x] Каждая страница кейса открывается и отображает полную информацию
- [x] Страница «Услуги» отображается
- [x] Страница «Контакты» отображается с рабочими ссылками
- [x] Навигация работает между всеми страницами
- [x] Сайт отображается корректно на desktop и mobile
- [x] Визуальный стиль соответствует инженерному минимализму

---

## 5. Этап 2: Деплой пользовательского интерфейса

**Статус:** ✅ Завершён (2026-07-13)

### Цель

Развернуть пользовательский интерфейс на существующем VPS и обеспечить доступность по домену.

### Результат

| Артефакт | Содержание |
|----------|------------|
| Работающий интерфейс | Сайт доступен по HTTPS |
| Конфигурация сервера | Docker, nginx, Traefik |
| SSL-сертификат | Let's Encrypt |
| Домен | ai.alex-n8n.site настроен и работает |

### Критерии завершения

- [x] Сайт доступен по HTTPS
- [x] Сайт доступен по домену https://ai.alex-n8n.site
- [x] Все страницы открываются без ошибок
- [x] SSL-сертификат валидный

---

## 6. Этап 3: Серверный компонент

**Статус:** ✅ Завершён

### Цель

Реализовать серверный компонент для AI-ассистента, который отвечает на вопросы о кейсах и услугах.

### Этап 3.1: Backend Infrastructure ✅

**Реализовано:**
- Структура backend создана
- FastAPI запускается (порт 8000)
- PostgreSQL подключена (порт 5432)
- Миграции выполнены
- Таблицы: `ai_provider_settings`, `chat_sessions`, `chat_messages`, `operational_logs`
- Начальные данные: OpenAI (active), GigaChat (fallback)
- Docker образ собран

### Этап 3.2.1: Service Layer — Basic Services ✅

**Реализовано:**
- Conversation Memory Service (из Assistant Flow)
- Chat Session Service (из Assistant Flow)
- Operational Log Service (из Review Flow + PEcf09 + Assistant Flow)
- AI Provider Settings Service (из Review Flow)

### Этап 3.2.2: Service Layer — RAG & Cache ✅

**Реализовано:**
- Response Cache (из PEcf09) — кеширование ответов с TTL
- RAG Service (из Assistant Flow + PEcf09) — поиск по базе знаний через ChromaDB
- Knowledge Base Indexer (из PEcf09) — индексация JSON в ChromaDB

### Этап 3.3: REST API & Integration ✅

**Реализовано:**
- Chat Endpoint `POST /chat`
- Health endpoint `GET /health`
- Root endpoint `GET /`
- Интеграция с frontend через `src/js/api-client.js` и `src/js/chat-widget.js`

### Результат

| Артефакт | Содержание | Статус |
|----------|------------|--------|
| Backend Infrastructure | FastAPI + PostgreSQL + миграции | ✅ |
| Service Layer | Memory, Session, Log, Provider, Cache, RAG | ✅ |
| REST API | Chat endpoint, Health endpoint | ✅ |
| UI-компонент | Chat widget на всех страницах | ✅ |
| Интегрированный сайт | Сайт + AI-ассистент работают вместе | ✅ |

### Критерии завершения

- [x] Backend Infrastructure создана
- [x] Basic Services реализованы
- [x] RAG & Cache Services реализованы
- [x] REST API работает (Chat endpoint)
- [x] AI-ассистент отвечает на вопросы о кейсах
- [x] AI-ассистент отвечает на вопросы об услугах
- [x] При недоступности AI — сайт продолжает работать (fallback + error handling)
- [x] API-ключи не доступны публично

---

## 7. Этап 7: Архитектура представления кейсов

**Статус:** ✅ Частично завершён (Lead Qualification реализован как эталон)

### Цель

Привести все существующие кейсы AI Portfolio к архитектуре представления: Narrative Blueprint + Presentation Patterns.

### Результат

| Артефакт | Содержание | Статус |
|----------|------------|--------|
| Narrative Blueprint Lead Qualification | Эталонная реализация | ✅ |
| Страница Lead Qualification | Scene Navigation, Presentation Patterns | ✅ |
| Остальные кейсы | Традиционные страницы с превью | ✅ |

### Примечание

Остальные кейсы (Assistant Flow, Review Flow, HR Assistant, Prompt Review, Telegram AI Gateway, Competitor Monitor AI) используют классические страницы кейсов. Переход на Narrative Blueprint + Scene Navigation является следующим этапом развития контента, но не блокирует текущую публикацию.

---

## 8. Этап 4: Интеграция и тестирование

**Статус:** ✅ Завершён

### Цель

Объединить все компоненты и протестировать работоспособность.

### Результат

| Артефакт | Содержание |
|----------|------------|
| Интегрированный сайт | Сайт + AI-ассистент работают вместе |
| E2E тесты | Проверены пользовательские сценарии |
| README | Описание проекта и способ запуска |

### Критерии завершения

- [x] Все пользовательские сценарии из SPEC работают
- [x] AI-ассистент отвечает корректно
- [x] Сайт доступен 24/7
- [x] При падении AI сайт продолжает работать
- [x] API-ключи не доступны публично

---

## 9. Этап 5: Deployment Validation

**Статус:** ⏳ Следующий этап

### Цель

Подтвердить, что `DEPLOYMENT_GUIDE` позволяет развернуть проект с нуля в чистом окружении.

### Состав работ

| Работа | Описание | Зависит от |
|--------|----------|------------|
| **Чистое окружение** | Подготовка чистого сервера/VM | — |
| **Проход по DEPLOYMENT_GUIDE** | Выполнение инструкций шаг за шагом | Этап 4 |
| **Фиксация проблем** | Документирование несоответствий | — |
| **Исправление DEPLOYMENT_GUIDE** | Актуализация инструкций | — |
| **Повторная валидация** | Повторный проход по исправленному guide | — |
| **Deployment Validation Report** | Отчёт о валидации | — |

### Критерии завершения

- [ ] DEPLOYMENT_GUIDE позволяет развернуть проект с нуля
- [ ] Все шаги DEPLOYMENT_GUIDE выполнены успешно
- [ ] Сайт работает корректно после чистого деплоя
- [ ] AI-ассистент работает корректно после чистого деплоя
- [ ] Deployment Validation Report документирует процесс

---

## 10. Этап 6: Административная консоль v1

**Статус:** ✅ Завершён (2026-07-15)

### Цель

Реализовать административную консоль для управления AI Portfolio. Консоль изначально планировалась как следующий этап развития продукта, но была реализована и интегрирована в production-контур в рамках текущей итерации.

Deployment Validation будет проведён по решению владельца проекта перед финальной публикацией.

### Реализованная функциональность

Первая версия содержит **пять разделов навигации**, сгруппированных по функциям:

| Раздел | Назначение | Границы |
|--------|------------|---------|
| **Системные настройки (Dashboard)** | Единая сводная картина состояния AI Portfolio + управление параметрами LLM-провайдеров и выбор active/fallback | Мониторинг системы + управление LLM-провайдерами. Не управляет остальным содержимым |
| **Контент / База знаний** | Управление карточками проектов, источниками KB, запуск синхронизации | Не редактирует Narrative Blueprint и Presentation Patterns; не является визуальным конструктором страниц |
| **Логи** | Operational console в стиле Assistant Flow: журнал execution-сессий с preview запроса, summary grid, цепочкой этапов, вопросом/ответом в двух колонках, timeline pipeline с дельтами и JSON snapshot | — |
| **Диалоги** | История chat-сессий и сообщений | — |

### Архитектура Knowledge Base

| Источник | Роль | Source of Truth |
|----------|------|-----------------|
| **GitHub** | Проектная документация | ✅ Да. Основной источник знаний |
| **PostgreSQL** | Управляемые данные сайта, эксплуатация, параметры LLM-провайдеров | ✅ Да |
| **ChromaDB** | Векторный поисковый индекс | ❌ Нет. Перестраивается из источников |

**Правила первой версии:**
- GitHub остаётся Source of Truth для проектной документации.
- **Временное техническое решение v1:** локальный файл `knowledge_base/knowledge.json` используется как источник для ручной синхронизации в ChromaDB, пока не реализован GitHub Sync. Это не меняет архитектурного статуса GitHub как SOT.
- Административная консоль управляет перечнем подключённых источников и инициирует их синхронизацию вручную.
- Автоматическая синхронизация по webhook не входит в первую версию.
- PostgreSQL не является основным хранилищем проектной документации.
- ChromaDB остаётся производным индексом и перестраивается из актуальных источников.

### Narrative Blueprint и Presentation Patterns

- **Narrative Blueprint** отвечает за то, что рассказывает страница проекта, порядок раскрытия материала и драматургию.
- **Presentation Patterns** отвечают за то, как информация отображается пользователю.
- Административная консоль не редактирует ни Narrative Blueprint, ни библиотеку Presentation Patterns.
- Административная консоль работает только с управляемым контентом внутри уже утверждённой структуры.

### Архитектурное решение

Техническая реализация административной консоли v1 зафиксирована в `docs/ADMIN_CONSOLE_ARCHITECTURE.md` и реализована:

| Компонент | Решение |
|-----------|---------|
| Frontend | React + TypeScript + Vite SPA в `admin/`, `base: '/admin/'` |
| Backend | FastAPI, единый префикс `/admin` |
| Аутентификация | Bearer token: `ADMIN_API_TOKEN` |
| Routing | React Router с `basename="/admin"` |
| Docker | Единый frontend-контейнер с multi-stage build |

### Примечание

Административная консоль v1 изначально планировалась как отдельный этап развития продукта, но была реализована в рамках текущей итерации. Она не входит в первоначальный критический путь уроков Prompt Engineering, но интегрирована в production-контур.

Окончательная техническая архитектура первой версии административной консоли согласована и зафиксирована в `docs/ADMIN_CONSOLE_ARCHITECTURE.md`. План реализации перенесён в настоящий документ (см. раздел 11).

---

## 11. Технический план реализации административной консоли

> Архитектура первой версии административной консоли согласована с владельцем проекта и зафиксирована в `task_history/2026-07-15_task-admin-console-final-architecture.md`.
> Реализация выполняется в пяти этапов. Deployment Validation не входит в эту последовательность и проводится отдельно по решению владельца проекта.

### 11.1. Этап 1: Backend Foundation ✅

**Статус:** Завершён (2026-07-15).

**Цель:** подготовить серверную основу административной консоли внутри единого FastAPI-приложения.

**Результат:**
- Модели данных `ProjectCard`, `KnowledgeSource`, `KnowledgeSyncJob` добавлены в `app/models/entities.py`.
- Модель `ProjectCard` содержит поля `display_order` (порядок в каталоге портфолио) и `show_on_homepage` (`0` — не отображать на главной, `1..4` — порядок на главной).
- Alembic-миграции для новых моделей созданы и применены.
- Административная аутентификация реализована через единый `ADMIN_API_TOKEN` (`app/api/admin/dependencies.py`).
- Создан каркас Admin API: пакет `app/api/admin/` с заглушками routers (`dashboard`, `knowledge_base`, `logs`, `conversations`).
- Routers подключены в `app/main.py` с префиксом `/admin`.

**Критерий завершения:**
- [x] `GET /admin/dashboard` (заглушка) возвращает 200 при валидном токене и 403 без него.
- [x] Миграции успешно применяются к PostgreSQL.
- [x] Структура `app/api/admin/` соответствует согласованной архитектуре.

---

### 11.2. Этап 2: Admin Frontend Foundation ✅

**Статус:** Завершён (2026-07-15).

**Цель:** создать отдельный frontend-модуль административной консоли на React + TypeScript + Vite.

**Результат:**
- Создан каталог `admin/` с Vite-конфигурацией (`vite.config.ts` с `base: '/admin/'`), TypeScript и React.
- Реализован Layout (`AdminLayout`), Navigation, ProtectedRoute, LoginPage, базовые UI-компоненты (Page, Card, Table, Toolbar, Loading, ErrorState, EmptyState), API client с Bearer-token.
- Маршрутизация: `/admin/login`, `/admin/dashboard`, `/admin/content`, `/admin/logs`.
- Проверена локальная сборка `npm run build`.

**Критерий завершения:**
- [x] `admin/` собирается без ошибок.
- [x] LoginPage принимает токен и сохраняет его в `localStorage`.
- [x] ProtectedRoute перенаправляет неавторизованного пользователя на `/admin/login`.
- [x] Навигация содержит три пункта: Dashboard, Content, Logs.

---

### 11.3. Этап 3: Infrastructure Integration ✅

**Статус:** Завершён (2026-07-15).

**Цель:** интегрировать admin frontend в существующую Docker-инфраструктуру AI Portfolio.

**Результат:**
- `src/Dockerfile` переработан в multi-stage: Stage 1 собирает `admin/` через Node.js, Stage 2 — nginx-образ с public + admin static files.
- `docker-compose.yml` обновлён: frontend-сервис собирается из корня проекта (`context: .`, `dockerfile: src/Dockerfile`).
- `src/nginx.conf` расширен маршрутами `/admin/` (static SPA с fallback на `index.html`) и `/api/admin/` (proxy на backend `/admin/`).
- `admin/src/main.tsx` получил `basename="/admin"` для корректного роутинга SPA.
- Backend endpoint `/admin/` доступен через `/api/admin/`.

**Критерий завершения:**
- [x] `docker compose build ai-portfolio-frontend` завершается успешно.
- [x] `curl /admin/` возвращает `admin/index.html`.
- [x] `curl /admin/dashboard` (refresh) возвращает `admin/index.html` (SPA fallback).
- [x] `curl /api/admin/dashboard` с токеном проксируется на backend `/admin/dashboard`.
- [x] `curl /api/admin/dashboard` без токена возвращает 403.
- [x] Публичные маршруты (`/`, `/chat`, `/health`, `/project-cards`) сохранены и работают.

---

### 11.4. Этап 4: Реализация трёх рабочих пространств

**Статус:** ✅ Завершён (2026-07-15).

**Цель:** реализовать функциональность трёх согласованных рабочих пространств.

**Результат:**

**Dashboard:**
- endpoint `/admin/dashboard` отдаёт сводные метрики: статус backend / PostgreSQL / ChromaDB, AI-провайдеры, ProjectCard, KnowledgeSource, sync, logs, conversations;
- endpoint `/admin/ai-providers` отдаёт параметры LLM-провайдеров из БД;
- endpoint'ы `PATCH /admin/ai-providers/{key}`, `POST .../activate`, `POST .../set-fallback`, `POST .../test` позволяют редактировать параметры, выбирать active/fallback и тестировать соединение;
- страница `DashboardPage.tsx` отображает метрики и редактируемые карточки провайдеров.

**Content / Knowledge Base:**
- CRUD управляемых карточек проектов (`ProjectCard`) — backend + frontend;
- CRUD источников Knowledge Base (`KnowledgeSource`) — backend + frontend;
- ручная синхронизация → ChromaDB через `POST /admin/knowledge-base/sync` (перестраивает коллекцию из `knowledge_base/knowledge.json` и `knowledge_content` карточек);
- панель статуса ChromaDB.

**Logs / Conversations:**
- endpoint `/admin/logs` с фильтрацией по `event_type`, `status`, `date_from`, `date_to` и пагинацией;
- endpoint `/admin/execution-sessions` с фильтрами route/status/date/search и пагинацией для operational console «Логи»;
- endpoint `/admin/conversations` со списком сессий и фильтрами (hours, route последнего execution, active_only, search);
- endpoint `/admin/conversations/{id}` с деталями сессии, сообщениями, парными turns, execution timeline и memory budget;
- страница `LogsPage.tsx` с вкладками Execution-сессии / Аудит; правая макропанель Execution-сессии разделена на «Параметры сессии» и «Параметры исполнения»;
- страница `ConversationsPage.tsx` в стиле Assistant Flow Memory Console; заголовок сводки — «Сводка диалоговой сессии», таблица диалога содержит колонки cache hit / response time.

**Критерий завершения:**
- [x] Все три рабочих пространства доступны в UI и отвечают на действия пользователя.
- [x] Синхронизация Knowledge Base перестраивает ChromaDB.
- [x] Фильтры и пагинация работают в Logs / Conversations.
- [x] Пройден обязательный production smoke-test.


### 11.5. Этап 5: Интеграция и тестирование

**Статус:** ✅ Завершён в объёме Stage 4 (2026-07-15).

**Цель:** объединить backend, frontend и инфраструктуру в работоспособную систему.

**Результат:**
- Пройден E2E-проход по всем трём рабочим пространствам.
- Проверена аутентификация: доступ с токеном, отказ без токена.
- Проверена синхронизация источников и корректность ответов AI-ассистента после переиндексации.
- Production smoke-test пройден; регрессий не выявлено.

**Критерий завершения:**
- [x] Все критерии Этапов 1–4 выполнены.
- [x] Нет критических ошибок при ручном тестировании.

### 11.6. Deployment Validation

> **Deployment Validation не является частью последовательности реализации административной консоли.**

Deployment Validation выполняется **отдельно и только по решению владельца проекта** после завершения разработки. Он подтверждает, что обновлённый `DEPLOYMENT_GUIDE` позволяет развернуть проект с нуля в чистом окружении, включая административную консоль.

### 11.7. Execution Tracing для панели «Логи»

**Статус:** ✅ Реализовано (2026-07-18).

**Цель:** превратить панель «Логи» в operational console по образцу Assistant Flow: двухпанельный layout, фильтры, таймлайн pipeline, запрос/ответ, метаданные.

**Результат:**
- Таблицы `execution_sessions` и `execution_steps` созданы миграцией 007.
- Миграция 008 выполняет backfill для существующих `operational_logs`.
- Миграция 009 добавляет флаг `is_backfilled` в `execution_sessions` и помечает backfill'нутые сессии.
- Сервис `ExecutionTracingService` интегрирован в `ChatOrchestrator` как опциональная зависимость.
- `step_metadata` каждого шага обогащён query/response/provider/model/latency/sources для operational console.
- `ExecutionSessionsAdminService.list_sessions` подгружает `query` из `operational_log` для preview в списке.

**API:**
- `GET /admin/execution-sessions` — основной endpoint для operational console; список execution-сессий с фильтрами route/status/date/search и пагинацией.
- `GET /admin/execution-sessions/{id}` — детали execution-сессии + шаги pipeline + связанный operational log.
- `GET /admin/logs` — сохранён для совместимости.

**Frontend:**
- `LogsPage.tsx` использует `/admin/execution-sessions` и `/admin/execution-sessions/{id}`.
- `PAGE_SIZE=7` для ровного отображения 7 айтемов в списке при 100% масштабе.
- Backfill'нутые сессии отображаются с компактной меткой "приблизительный" у заголовка таймлайна; duration/delta остаются видимыми.

**Критерий завершения:**
- [x] Новый chat-запрос создаёт execution_session с полным таймлайном шагов.
- [x] Старые записи получают execution_session после миграции.
- [x] Backfill'нутые сессии помечены флагом `is_backfilled`.
- [x] Operational console «Логи» отображает список сессий, фильтры и детальную трассировку через `/admin/execution-sessions`.
- [x] Пройден production smoke-test: миграции применены, chat работает, cache hit корректно отмечает skipped шаги, admin endpoints отвечают.

### 11.8. Аудит входа в админку и посещений сайта

**Статус:** ✅ Реализовано (2026-07-19).

**Цель:** зафиксировать факт входа пользователя в административную консоль и посещения публичного сайта в `operational_logs`, чтобы понимать, кто заходил в систему / на сайт.

**Результат:**
- Добавлен backend endpoint `POST /admin/login` (`backend/app/api/admin/auth.py`): проверяет `ADMIN_API_TOKEN` через `require_admin`, пишет `operational_log` с `event_type='admin_login'`, возвращает `{ success: true }`.
- Добавлен публичный backend endpoint `POST /track-visit` (`backend/app/api/tracking.py`): пишет `operational_log` с `event_type='site_visit'`, возвращает `visitor_id`.
- `LoginPage.tsx` вызывает `POST /admin/login` до сохранения токена; при ошибке токен не сохраняется.
- Публичный frontend (`src/js/api-client.js` + `src/js/main.js`) отправляет `POST /track-visit` при загрузке каждой страницы с `visitor_id` из `localStorage`.
- `nginx.conf` проксирует `/track-visit` на backend.
- `LogsPage.tsx` получил вкладку «Аудит»: список operational logs с фильтрами по `event_type` (`admin_login`, `site_visit`, `chat_request`, `rag_query`, `other`) и `status`, детальный просмотр metadata (IP, user_agent, visitor_id).
- Миграция 010 добавляет индекс `ix_operational_logs_event_type_status` для быстрого поиска audit-событий.

**API:**
- `POST /admin/login` — проверка токена + запись `admin_login`.
- `POST /track-visit` — публичный endpoint записи `site_visit`.
- `GET /admin/logs` — список operational logs с фильтрами (event_type, status, date).

**Frontend:**
- `LoginPage.tsx`: `loginAdmin(token)` через `apiClient`.
- `src/js/api-client.js`: `getVisitorId()` + `trackVisit()`.
- `src/js/main.js`: вызов `APIClient.trackVisit()` в `init()`.
- `LogsPage.tsx`: вкладки «Execution-сессии» / «Аудит», `listLogs()` для audit-записей.

**Критерий завершения:**
- [x] `POST /admin/login` с валидным токеном создаёт `operational_log` с `event_type='admin_login'`, `status='ok'`.
- [x] `POST /admin/login` с невалидным токеном создаёт запись с `status='error'`.
- [x] Frontend `LoginPage` вызывает `/admin/login` и только потом сохраняет токен.
- [x] `POST /track-visit` создаёт `operational_log` с `event_type='site_visit'`.
- [x] Публичный сайт отправляет `visitor_id` при загрузке.
- [x] LogsPage отображает новые event_type во вкладке «Аудит».
- [x] `npm run build` проходит.
- [x] `python -m py_compile` проходит.
- [x] SOT-документы актуализированы.

### 11.9. Архитектурное упрощение логирования chat pipeline

**Статус:** ✅ Реализовано (2026-07-19).

**Цель:** устранить дублирование chat-запросов в `operational_logs` и `execution_sessions`; сделать `execution_sessions` единым SOT для chat pipeline; добавить visitor-реквизиты для сквозной идентификации.

**Результат:**
- В модель `ExecutionSession` добавлены поля `visitor_id`, `client_ip`, `user_agent` (миграция 011 + индексы).
- `ExecutionTracingService.start_session` принимает visitor-реквизиты.
- `ChatOrchestrator.process_request` больше не вызывает `log_chat_request` и не создаёт `operational_log` с `event_type='chat_request'`.
- Query/response/provider/model/rag_used/sources/error/response_time_ms сохраняются в `execution_metadata` сессии.
- `POST /chat` принимает `visitor_id` из публичного frontend; IP и user_agent извлекаются из HTTP-заголовков.
- Публичный frontend (`src/js/api-client.js`) передаёт `visitor_id` при отправке чата.
- `ExecutionSessionsAdminService` больше не подгружает связанный `OperationalLog`; preview query берётся из `execution_metadata`.
- `LogsPage.tsx`:
  - Вкладка «Execution-сессии» отображает visitor_id, IP, user_agent в списке и detail view.
  - Вкладка «Аудит» фильтрует `chat_request`/`rag_query`, оставляя только `admin_login`, `site_visit`, `provider_switch`.

**API:**
- `POST /chat` — принимает `visitor_id`, фиксирует visitor-реквизиты в execution-сессии.
- `GET /admin/execution-sessions` — список chat pipeline с visitor_id, client_ip, user_agent.
- `GET /admin/execution-sessions/{id}` — детали chat pipeline + шаги + query/response из metadata.
- `GET /admin/logs` — только системные события (`admin_login`, `site_visit`, `provider_switch`).

**Frontend:**
- `src/js/api-client.js`: `visitor_id` в `POST /chat`.
- `admin/src/api/client.ts`: тип `ExecutionSession` с visitor_id/client_ip/user_agent; `ExecutionSessionDetail` без поля `log`.
- `admin/src/pages/LogsPage.tsx`: разделение вкладок без дублирования.

**Критерий завершения:**
- [x] Новый chat-запрос создаёт только `execution_session` (без `operational_log` `chat_request`).
- [x] `execution_sessions` содержит visitor_id, client_ip, user_agent.
- [x] Вкладка «Аудит» не отображает chat_request/rag_query.
- [x] Вкладка «Execution-сессии» отображает visitor-реквизиты.
- [x] `npm run build` проходит.
- [x] `python -m py_compile` проходит.
- [x] SOT-документы актуализированы.

### 11.10. Переработка страницы «Диалоги» в стиле Assistant Flow Memory Console

**Статус:** ✅ Реализовано (2026-07-19).

**Цель:** превратить страницу «Диалоги» в операционную консоль диалоговых сессий по образцу Assistant Flow Memory Console.

**Результат:**
- Backend: `LogsConversationsService.list_conversations` расширен фильтрами `hours`, `route` (route последнего `ExecutionSession`), `active_only`, `search`; возвращает `message_count`, `turns_approx`, `visitor_id`, `last_execution` summary.
- Backend: `LogsConversationsService.get_conversation` возвращает `recent_turns` (парные user/assistant), полный список сообщений (лимит 500), связанные `ExecutionSession` со steps (лимит 20), `budget` из `MemoryBudgetPolicy`, `memory_source`.
- Frontend: `ConversationsPage.tsx` полностью переработан на двухпанельный `logs-console` layout с фильтрами (окно времени 24h/48h/7d, режим all/RAG/текст/прочие, активность all/активные/неактивные, поиск), списком сессий с keyboard navigation, auto-select и detail panel.
: - Detail panel содержит: сводку диалоговой сессии, параметры сессии (session_id, visitor IP, режим, активность, сообщения, turns, обновлена), параметры исполнения (RAG, provider/model, source, response time), memory policy (max_recent_messages, max_message_chars, total_memory_chars_budget), таблицу диалога с парными репликами и колонками cache hit / response time на уровне turn (по execution-сессии), timeline execution pipeline (по умолчанию свёрнут) и JSON snapshot.
- Добавлены CSS-классы для `memory-dialog-table`, `memory-dialog-panel` и responsive fallback в `globals.css`. Панель диалога занимает основное пространство правой панели за счёт flex-раскладки.

**API:**
- `GET /admin/conversations` — список сессий с фильтрами и runtime context.
- `GET /admin/conversations/{id}` — детали сессии с messages, turns, executions, budget.

**Frontend:**
- `admin/src/pages/ConversationsPage.tsx` — двухпанельная operational console.
- `admin/src/api/client.ts` — обновлены типы `ChatSession`, `ConversationDetail`, `listConversations`, `getConversation`.
- `admin/src/styles/globals.css` — стили для `memory-dialog-table`, `memory-detail-panel`, `memory-dialog-panel` и `memory-timeline-fold`; обновлены `.logs-summary-col` для единообразных отступов.

**Критерий завершения:**
- [x] `GET /admin/conversations` возвращает расширенный список сессий.
- [x] `GET /admin/conversations/{id}` возвращает turns, executions со steps, budget, memory_source.
- [x] Страница «Диалоги» открывается в админке и отображает двухпанельный layout.
- [x] Фильтры по времени, режиму, активности и поиску работают.
- [x] Клик по сессии показывает сводку, параметры исполнения, memory policy и таблицу диалога.
- [x] Cache hit и response time отображаются в таблице диалога как колонки на уровне turn.
- [x] Execution timeline по умолчанию свёрнут.
- [x] Execution timeline отображается для сессий с execution-сессиями.
- [x] `npm run build` проходит.
- [x] `python -m py_compile` проходит.
- [x] SOT-документы актуализированы.

---

## 11.11. GitHub Sync для Knowledge Base

**Статус:** ✅ Завершено (2026-07-19).

**Цель:** заменить временный источник `knowledge_base/knowledge.json` на автоматическую загрузку проектной документации из репозиториев APL на GitHub. GitHub должен стать единственным Source of Truth для проектной документации, из которой строится векторный индекс ChromaDB.

**Архитектурное решение:**

| Компонент | Решение |
|-----------|---------|
| Источник | Репозитории APL на GitHub (`README.md`, `docs/**/*.md`) |
| API | GitHub REST API (`/repos/{owner}/{repo}/contents/...`) |
| Аутентификация | `Authorization: token <GITHUB_TOKEN>` из `.env` |
| Промежуточное хранение | Таблицы `knowledge_documents` + `knowledge_sync_errors` в PostgreSQL |
| Индексация | `KnowledgeBaseIndexer` → ChromaDB |
| ChromaDB | Отдельный HTTP-сервис `ai-portfolio-chroma` (`HttpClient`) для thread-safe доступа |
| Триггер | Ручная синхронизация в админке (`POST /admin/knowledge-base/sync`); выполняется в фоновом thread |

**Подэтапы:**

### 11.11.1. ✅ Подготовка и исследование GitHub API

| Работа | Результат |
|--------|-----------|
| Проверить endpoints для чтения файлов и содержимого репозитория | Использован `/repos/{owner}/{repo}/contents/{path}` |
| Определить список репозиториев/организации APL | 7 источников `github_repo` в `knowledge_sources` |
| Изучить rate limits и способы аутентификации | `GITHUB_TOKEN`, заголовок `Authorization: token ...` |
| Определить структуру читаемых файлов | `README.md`, `docs/**/*.md`; исключены `task_history/`, `attachments/`, `screenshots/`, `node_modules/`, `.git/` |

### 11.11.2. ✅ Модели данных и API

| Работа | Результат |
|--------|-----------|
| Расширить `KnowledgeSource` полями `branch`, `base_path` | Модель поддерживает `source_type=github_repo`, default `branch='main'` |
| Добавить таблицу `knowledge_documents` | Миграция `012_add_knowledge_documents.py` |
| Добавить таблицу `knowledge_sync_errors` | Лог ошибок по источникам |
| Создать сервис `GitHubKnowledgeSourceService` | `backend/app/services/admin/github_knowledge_source_service.py` |
| Обновить `POST /admin/knowledge-base/sync` | Запускает fetch + индексацию в фоновом thread; возвращает `job_id` |

### 11.11.3. ✅ Загрузка и парсинг markdown

| Работа | Результат |
|--------|-----------|
| Загрузка `README.md` и `docs/**/*.md` через GitHub API | Сырые markdown-файлы сохраняются в `knowledge_documents` |
| Парсинг markdown → plain text | Библиотека `markdown` + strip HTML tags |
| Сохранение метаданных | `path`, `title`, `raw_url`, `commit_sha`, `fetched_at` |
| Обработка ошибок и пропуск недоступных файлов | Ошибки пишутся в `knowledge_sync_errors`, sync продолжается |

### 11.11.4. ✅ Индексация в ChromaDB

| Работа | Результат |
|--------|-----------|
| Очистка чанков | Перед индексацией каждого документа удаляются его старые чанки по `document_id` |
| Индексация документов из GitHub + `ProjectCard.knowledge_content` | 5400 чанков, `rag_used: true` в `/chat` |
| Обновление `last_sync_at`, `last_sync_status`, `last_sync_error` | Видно в `GET /admin/knowledge-base/sources` |
| ChromaDB deployment | Переведено на `ai-portfolio-chroma` HTTP-сервис для thread-safe concurrent доступа |

### 11.11.5. ✅ UI в админке

| Работа | Результат |
|--------|-----------|
| Форма добавления GitHub-источника | `KnowledgeSourcesPage.tsx` (placeholder `identifier`) |
| Индикатор прогресса синхронизации | `KnowledgeSyncPage.tsx` с polling job-статуса каждые 3 сек |
| Список загруженных документов с предпросмотром | Минимальный CRUD источников + статус `last_sync_*` |

### 11.11.6. ✅ Тестирование и документация

| Работа | Результат |
|--------|-----------|
| Синхронизация всех 7 кейсов APL | ✅ 192 документа, 5400 чанков |
| Проверка ответов AI-ассистента | ✅ `/chat` отвечает по `docs/SPEC.md`, `docs/ARCHITECTURE.md` |
| Проверка идемпотентности | ✅ Повторный sync не удваивает count, нет `Insert of existing embedding ID` |
| Обновление SOT-документов | ✅ `IMPLEMENTATION_PLAN.md`, `ADMIN_CONSOLE_ARCHITECTURE.md`, `PROJECT_STATE.md` |

**Критерии завершения:**
- [x] `POST /admin/knowledge-base/sync` загружает документацию из GitHub-репозиториев.
- [x] В ChromaDB индексированы README и docs всех 7 кейсов APL.
- [x] `knowledge_base/knowledge.json` больше не используется как источник.
- [x] AI-ассистент отвечает по актуальным данным из GitHub.
- [x] Админка отображает статус синхронизации и ошибки по источникам.
- [x] `npm run build` проходит.
- [x] `python -m py_compile` проходит.
- [x] SOT-документы актуализированы.

**Оценка трудоёмкости:** 8–12 часов.

---

## 12. Сводка по этапам

| Этап | Название | Статус |
|------|----------|--------|
| 0 | Подготовка | ✅ |
| 1 | Пользовательский интерфейс | ✅ |
| 2 | Деплой пользовательского интерфейса | ✅ |
| 7 | Архитектура представления кейсов | ✅ (эталон Lead Qualification) |
| 3 | Серверный компонент | ✅ |
| 4 | Интеграция | ✅ |
| 5 | Deployment Validation | ⏳ Будет проведён по решению владельца продукта |
| 6 | Административная консоль v1 | ✅ Реализован и развёрнут (Stage 4) |
| 7 | Execution Tracing для панели «Логи» | ✅ Реализовано |
| 8 | Аудит входа и посещений сайта | ✅ Реализовано |
| 9 | Переработка «Диалоги» в стиле Assistant Flow Memory Console | ✅ Реализовано |
| 10 | GitHub Sync для Knowledge Base | ✅ Завершено |

### Критический путь (завершён)

```
Этап 0 → Этап 1 → Этап 2 → Этап 7 → Этап 4
         ↓
       Этап 3 → Этап 4
```

---

## 13. Риски и зависимости

### Внешние зависимости

| Зависимость | Описание | Митигация |
|-------------|----------|-----------|
| **Контент от владельца** | Тексты для главной, кейсов, услуг | Уже подготовлен |
| **Домен** | Привязка домена к VPS | ai.alex-n8n.site настроен |
| **AI-провайдер API** | API-ключ и доступ | OpenAI + GigaChat fallback |
| **VPS** | Существующая инфраструктура | Проверить ресурсы, конфигурацию |

### Риски проекта

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Задержка контента от владельца | Низкая | Высокое | Контент подготовлен |
| Качество ответов AI | Средняя | Среднее | Подготовлена база знаний |
| Стоимость API при нагрузке | Низкая | Низкое | Мониторинг использования |
| Проблемы с деплоем | Низкая | Среднее | Deployment Validation |
| Отсутствие изображений кейсов | Средняя | Среднее | Placeholder, запрос у владельца |

---

## 14. Критерии готовности первой версии

### Продуктовые критерии

| Критерий | Признак готовности |
|----------|-------------------|
| Сайт доступен | Работает по HTTPS, все страницы открываются |
| AI-ассистент работает | Отвечает на вопросы о кейсах и услугах |
| Каналы связи работают | Telegram и Email доступны |
| Контент актуален | Все 7 кейсов описаны, услуги описаны |
| Визуальный стиль | Соответствует инженерному минимализму |

### Технические критерии

| Критерий | Признак готовности |
|----------|-------------------|
| Деплой на VPS | Сайт развёрнут на существующем VPS |
| 24/7 доступность | Сайт работает постоянно |
| Fallback AI | При недоступности AI сайт продолжает работать |
| Безопасность | API-ключи не доступны публично |
| Docker-конфигурация | Единый `docker-compose.yml` как Source of Truth, управление через Docker Compose v2 |

### Документационные критерии

| Критерий | Признак готовности |
|----------|-------------------|
| DEPLOYMENT_GUIDE | Позволяет развернуть с нуля |
| Deployment Validation Report | Валидация пройдена |
| README | Описывает проект и способ запуска |

---

## 15. Следующие шаги

1. ~~Согласование плана с владельцем~~ — ✅ Выполнено
2. ~~Этап 0: Подготовка~~ — ✅ Выполнено
3. ~~Этап 1: Пользовательский интерфейс~~ — ✅ Выполнено
4. ~~Этап 2: Деплой пользовательского интерфейса~~ — ✅ Выполнено
5. ~~Этап 3: Серверный компонент~~ — ✅ Выполнено
6. ~~Этап 4: Интеграция~~ — ✅ Выполнено
7. ~~Этап 7: Архитектура представления (эталон Lead Qualification)~~ — ✅ Выполнено
8. ~~Этап 6: Административная консоль v1 — Stage 4~~ — ✅ Выполнено
9. **Управление параметрами LLM-провайдеров через БД** — ✅ Выполнено. Параметры (`model_name`, `temperature`, `max_tokens`, `base_url`, `is_enabled`, `is_active`, `is_fallback`) перенесены в PostgreSQL; редактирование и выбор active/fallback доступны в Dashboard административной консоли.
10. **Превращение «Карточки проектов» в операционную панель** — ✅ Выполнено (2026-07-18). Страница `ProjectCardsPage.tsx` переработана в двухпанельный layout (список слева, карточка справа) с toolbar в шапке страницы, фильтрами, пагинацией, макропанелями Паспорт/Эксплуатация/Описание/База знаний и модальным редактированием. Добавлен endpoint `GET /admin/knowledge-base/project-cards/{id}/chunks` для отображения чанков ChromaDB, связанных с карточкой. Миграция `006_init_project_card_timestamps.py` инициализирует `created_at`/`updated_at` для существующих карточек.
11. **Execution Tracing для панели «Логи»** — ✅ Реализовано (2026-07-18). Таблицы `execution_sessions`/`execution_steps`, миграции 007/008, сервис `ExecutionTracingService`, endpoints `/admin/execution-sessions`, двухпанельный operational layout в `LogsPage`. Остаётся production smoke-test.
12. **GitHub Sync для Knowledge Base** — ✅ Завершено (2026-07-19). GitHub стал Source of Truth для проектной документации; синхронизация запускается вручную из админки, ChromaDB перестраивается из актуальных источников.
13. **Подготовка DEPLOYMENT_GUIDE и Deployment Validation** — ⏳ Следующий шаг. Необходимо создать отдельный файл `DEPLOYMENT_GUIDE.md`, пройти его в чистом окружении и зафиксировать Deployment Validation Report. Учесть новый сервис `ai-portfolio-chroma`.

---

## 16. История изменений

| Дата | Версия | Изменение |
|------|--------|-----------|
| 2026-07-12 | 1.0 | Первая версия IMPLEMENTATION_PLAN на основе PROJECT_STATE и SPEC |
| 2026-07-12 | 1.1 | Удалены преждевременные архитектурные решения, нейтральные формулировки, уточнено назначение PostgreSQL |
| 2026-07-13 | 1.2 | Отмечено завершение Этапа 1 и Этапа 2 |
| 2026-07-13 | 1.3 | Добавлен этап приведения существующих кейсов к архитектуре представления |
| 2026-07-14 | 1.4 | Добавлены подэтапы Этапа 3: Backend Infrastructure, Basic Services, RAG & Cache. Отмечено их завершение |
| 2026-07-14 | 1.5 | Добавлен Этап 6: Административная консоль |
| 2026-07-15 | 1.6 | Актуализировано состояние: Этапы 3.3, 4 завершены. Уточнено, что административная консоль — следующий этап развития. Репозиторий инициализирован. |
| 2026-07-15 | 1.7 | В Этапе 6 зафиксирована продуктовая концепция первой версии административной консоли: 3 рабочих пространства, архитектура Knowledge Base, роль Narrative Blueprint / Presentation Patterns. Техническая реализация оставлена для этапа проектирования. |
| 2026-07-15 | 1.8 | Этапы 11.1–11.3 отмечены как завершённые. Добавлены критерии завершения Stage 3 и детали фактически внедрённой инфраструктуры. |
| 2026-07-15 | 1.9 | Stage 4 и 11.5 отмечены завершёнными. Устранены противоречия в статусах административной консоли. Зафиксировано временное использование `knowledge_base/knowledge.json` до реализации GitHub Sync. |
| 2026-07-18 | 1.10 | Управление параметрами LLM-провайдеров перенесено в БД и Dashboard. Добавлен раздел 15 с завершёнными задачами и следующими шагами. |
| 2026-07-18 | 1.11 | Актуализирована архитектура административной консоли: `ProjectCardsPage` как операционная панель, endpoint для чанков карточки, отдельные страницы Sources/Sync, кастомная шапка `Page` через `renderHeader`, миграция 006 с `created_at`/`updated_at`. |
| 2026-07-18 | 1.12 | Добавлен Этап 11.7 «Execution Tracing для панели «Логи»»: модель данных, миграция backfill, сервис, endpoints, frontend-план. Реализация отложена; план зафиксирован в task_history и ADMIN_CONSOLE_ARCHITECTURE.md. |
| 2026-07-18 | 1.13 | Execution Tracing реализовано и развёрнуто в production: модели, миграции 007/008 (backfill 38 сессий / 328 шагов), `ExecutionTracingService`, интеграция в `ChatOrchestrator`, admin endpoints, двухпанельный `LogsPage`. Прошёл production smoke-test. Актуализирована структура разделов админки в документации. |
| 2026-07-19 | 1.14 | Добавлен Этап 11.11 «GitHub Sync для Knowledge Base». Зафиксирован план замены временного источника `knowledge.json` на автоматическую загрузку проектной документации из репозиториев APL на GitHub. |
| 2026-07-19 | 1.15 | Этап 11.11 «GitHub Sync для Knowledge Base» отмечен завершённым. Зафиксирован переход на HTTP ChromaDB (`ai-portfolio-chroma`) для thread-safe concurrent доступа. |
