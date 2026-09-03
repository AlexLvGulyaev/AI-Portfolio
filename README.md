# 🏠 AI Portfolio

Витрина AI-инженера: 13 реализованных проектов с лендингами и AI-ассистентом, который отвечает на вопросы о кейсах по документации GitHub-репозиториев — с указанием источников.

## ▶️ Live Demo

**Сайт:** https://ai.alex-n8n.site — откройте чат-виджет и спросите о любом кейсе, услугах или компетенциях.

## ❓ Зачем

Заказчику AI-автоматизации трудно оценить исполнителя до первого контракта: обещания не проверишь, а «кейсы» без живого доступа — просто скриншоты.

**AI Portfolio закрывает эту проблему.** Каждый кейс витрины — реализованный проект с публичным GitHub-репозиторием и лендингом, а встроенный ассистент — работающий образец того, что получает заказчик: RAG-ассистент по вашей базе знаний, где:

- факты берутся только из официального реестра проектов и допущенных документов (grounding с указанием источников);
- материалы попадают в базу знаний только через управляемый допуск качества (admission gate);
- при отсутствии сведений ассистент честно отвечает «информации нет»;
- качество подтверждено контрольными eval-прогонами (корректность 94,6%, p95 < 5 секунд — [`docs/AI_EVAL_REPORT.md`](docs/AI_EVAL_REPORT.md)).

Больше о бизнес-ценности — в [`docs/BUSINESS_VALUE.md`](docs/BUSINESS_VALUE.md).

## 🎯 Для кого

- Малый бизнес с ручными процессами — автоматизация рутины: Telegram-боты, n8n-контуры, обработка входящих заявок и документов.
- Компании с накопленной базой знаний — AI-ассистенты, которые отвечают по документации, а не по памяти модели.
- Образовательные платформы — AI-ассистенты поверх LMS и учебных материалов.
- Все, кому нужен AI-контур «под ключ» — от проектирования до production-развёртывания на своём хостинге.

С чем можно обратиться — на странице [Услуги](https://ai.alex-n8n.site/services.html).

## ✨ Ключевые возможности

- **Витрина 13 кейсов** — единый лендинг-стандарт: результат, проблема/решение, метрики, сценарии; главная страница одновременно является каталогом.
- **Подбор кейса под задачу** — опишите задачу на главной, платформа вернёт до 3 релевантных кейсов с объяснением применимости по документам (`POST /case-match`, grounded).
- **Живой AI-ассистент** — RAG с grounding: ответы по документации кейсов из векторного индекса, с карточками источников; клик по источнику открывает панель документа с подсвеченным фрагментом и ссылкой на GitHub; оценка ответов 👍/👎.
- **Управляемый допуск знаний** — каждый документ проходит admission gate: draft-правила → immutable-превью с commit SHA → утверждение → синхронизация.
- **Multi-provider LLM** — OpenAI активен, GigaChat в фоллбэке; провайдер и параметры настраиваются из админ-консоли.
- **Admin Console** — реакт-консоль: контент и допуск KB, retrieval-настройки, AI-настройки (включая управляемый системный промпт с историей версий), операционные логи, диалоги, аудит, пресейл-воронка.
- **Switchable vector store** — ChromaDB / Weaviate переключаются без изменения кода.
- **Dual theme** — светлая и тёмная темы на всех публичных страницах.
- **Измеримое качество** — eval-отчёт с корректностью и latency в документации.

## 🌐 Публичные точки входа

| Точка входа | URL | Доступ |
|-------------|-----|--------|
| Сайт-витрина | https://ai.alex-n8n.site | публично |
| Admin Console | https://af-admin.alex-n8n.site | bearer-токен `ADMIN_API_TOKEN` |
| Backend health | `GET /health` | публично |
| Каталог проектов | `GET /project-cards` | публично |
| AI-ассистент | `POST /chat` | публично (rate limit 10 req/min на IP) |
| Подбор кейса под задачу | `POST /case-match` | публично |
| Панель документа | `GET /document-fragment` | публично |

Контракты всех публичных эндпойнтов — [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md); ограничение частоты запросов — 10 req/min на IP с burst 20 (429 при превышении).

## 📚 Документация

### Для посетителей и заказчиков

- [🙋 `docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — как пользоваться витриной, подбором кейса и ассистентом.
- [💼 `docs/BUSINESS_VALUE.md`](docs/BUSINESS_VALUE.md) — бизнес-ценность: какие задачи клиента закрываются и как строится работа.
- [🎬 `docs/SYSTEM_DEMO.md`](docs/SYSTEM_DEMO.md) — продукт как работающая система: демо-сценарии и скриншоты.
- [🎬 `docs/E2E_SCENARIOS.md`](docs/E2E_SCENARIOS.md) — сквозные сценарии работы системы.
- [❓ `docs/FAQ.md`](docs/FAQ.md) — частые вопросы и контакты.
- [🗺️ `docs/PORTFOLIO_OVERVIEW.md`](docs/PORTFOLIO_OVERVIEW.md) — карта портфеля.

### Для пользователей и операторов

- [🎛️ `docs/ADMIN_GUIDE.md`](docs/ADMIN_GUIDE.md) — операции администратора: допуск источников KB, retrieval, AI-настройки, мониторинг.
- [🔧 `docs/OPERATIONS.md`](docs/OPERATIONS.md) — эксплуатация развёрнутого экземпляра: регламент, штатные операции, инциденты, бэкапы.
- [🛣️ `docs/ROADMAP.md`](docs/ROADMAP.md) — развитие платформы: незакрытые требования и утверждённые направления.
- [🔤 `docs/GLOSSARY.md`](docs/GLOSSARY.md) — глоссарий терминов.
- [🧭 `docs/COMPETENCIES.md`](docs/COMPETENCIES.md) — матрица компетенций.

### Для инженеров и интеграторов

- [🏗️ `docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура системы.
- [📡 `docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — контракт публичных эндпойнтов.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) — воспроизводимое развёртывание с нуля (валидировано Deployment Validation).
- [🧾 `docs/DEPLOYMENT_VALIDATION_REPORT.md`](docs/DEPLOYMENT_VALIDATION_REPORT.md) — протокол Deployment Validation.
- [🔬 `docs/TESTING_CONTRACT.md`](docs/TESTING_CONTRACT.md) — тестовые контуры: unit, eval, E2E.
- [🧪 `docs/AI_EVAL_REPORT.md`](docs/AI_EVAL_REPORT.md) — методика и итоги eval-тестирования ассистента.
- [📝 `docs/PROMPT_ARCHITECTURE.md`](docs/PROMPT_ARCHITECTURE.md) — промпт-архитектура и активный системный промпт.
- [🖥️ `docs/ADMIN_CONSOLE_ARCHITECTURE.md`](docs/ADMIN_CONSOLE_ARCHITECTURE.md) — техническая архитектура Admin Console.
- [📋 `docs/SPEC.md`](docs/SPEC.md) — продуктовая спецификация.
- [📊 `docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — состояние проекта.
- [📋 `docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — план реализации.
- [📐 `docs/TZ.md`](docs/TZ.md) — техническое задание.

## ✅ Статус проекта

Развёрнут и доступен по адресу https://ai.alex-n8n.site. Production-ready release — 04.09.2026: Deployment Validation пройдена в чистом окружении (3 прогона fresh-from-zero по `DEPLOYMENT_GUIDE`), eval-качество ассистента принято (94,6% / p95 4956 мс).

## 🛠️ Технологии

| Слой | Стек |
|------|------|
| Frontend | Vanilla HTML5/CSS3/JS (ES6+), dual theme, без фреймворков |
| Backend | FastAPI, PostgreSQL, SQLAlchemy + Alembic |
| Vector store | ChromaDB / Weaviate (переключаемые) |
| LLM | OpenAI (активный) / GigaChat (фоллбэк), embeddings `text-embedding-3-small` |
| Admin Console | React + TypeScript + Vite |
| Инфраструктура | Docker Compose, nginx, Traefik + Let's Encrypt, VPS |

## 📁 Структура проекта

```
ai-portfolio/
├── docs/                         # Документация (карта — раздел выше)
├── src/                          # Frontend: сайт, страницы кейсов, чат-виджет
│   ├── index.html                # Главная = витрина всех проектов
│   ├── services.html / contacts.html
│   ├── cases/                    # 13 лендингов кейсов
│   ├── _scripts/                 # Генераторы: build_registry, generate_landings
│   ├── Dockerfile / nginx.conf   # Сборка frontend-образа
├── backend/                      # Backend (FastAPI): API, RAG, admission gate
│   ├── app/                      # api/ (в т.ч. admin/), services/, models/
│   ├── migrations/               # Alembic-миграции
│   ├── tests/                    # Unit-тесты
├── admin/                        # Admin Console (React + TS + Vite)
├── e2e/                          # E2E-каркас консоли
├── scripts/                      # Служебные скрипты
├── demos/                        # Демонстрационные материалы
├── docker-compose.yml            # Source of Truth развёртывания
└── .env.example                  # Шаблон переменных окружения
```

## 🚀 Быстрый старт

```bash
cp .env.example .env    # заполнить: OPENAI_API_KEY, ADMIN_API_TOKEN, POSTGRES_PASSWORD,
                        # DATABASE_URL, CORS_ORIGINS, KB_REPO_OWNER
docker compose up -d --build
curl -s http://localhost:8000/health
```

Полная инструкция воспроизводимого развёртывания с нуля (включая наполнение базы знаний через Admin API) — [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md). Параметры LLM-провайдеров и системный промпт настраиваются через Admin Console после запуска; API-ключи задаются только в `.env`.

## 📚 Связанные документы

- [💼 `docs/BUSINESS_VALUE.md`](docs/BUSINESS_VALUE.md) — бизнес-ценность.
- [🏗️ `docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) — развёртывание.
- [🧪 `docs/AI_EVAL_REPORT.md`](docs/AI_EVAL_REPORT.md) — eval-качество ассистента.

## 📄 Лицензия

© 2026 AI Portfolio. Все права защищены.