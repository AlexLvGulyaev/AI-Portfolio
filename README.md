# AI Portfolio — Персональный сайт AI-инженера

Персональный сайт AI-инженера с портфолио реализованных проектов, интегрированным AI-ассистентом и информацией об услугах по AI-автоматизации.

## Онлайн-версия

**Сайт доступен по адресу:** https://ai.alex-n8n.site

## О проекте

Сайт представляет AI-инженера, специализирующегося на автоматизации бизнес-процессов с помощью искусственного интеллекта.

**Состав проекта:**

- **Главная страница** — представление и превью кейсов
- **Портфолио** — каталог всех реализованных проектов (13 кейсов)
- **Услуги** — информация о решаемых задачах и технологиях
- **Контакты** — способы связи
- **AI-ассистент** — встроенный чат-виджет для вопросов о кейсах и услугах

**О базе знаний и AI-ассистенте.** Ассистент отвечает на вопросы о портфеле поверх базы знаний, собранной из документации GitHub-репозиториев проектов: только материалы, прошедшие допуск качества (admission gate), попадают в векторный индекс. Ответы привязаны к источникам (grounding): факты о проектах ассистент берёт только из официального реестра и документов базы знаний, а при отсутствии сведений честно сообщает об этом, не достраивая ответ из общей памяти модели. Качество ассистента подтверждено контрольными eval-прогонами — итоги открыты в [`docs/AI_EVAL_REPORT.md`](docs/AI_EVAL_REPORT.md). Мета-документация платформы: [`docs/GLOSSARY.md`](docs/GLOSSARY.md) — глоссарий терминов, [`docs/FAQ.md`](docs/FAQ.md) — частые вопросы и контакты, [`docs/PORTFOLIO_OVERVIEW.md`](docs/PORTFOLIO_OVERVIEW.md) — карта портфеля, [`docs/COMPETENCIES.md`](docs/COMPETENCIES.md) — матрица компетенций.

## Технологии

### Frontend

- **HTML5** — семантическая разметка
- **CSS3** — стили, Flexbox/Grid, адаптивность
- **JavaScript (ES6+)** — минимальная интерактивность
- **Vanilla stack** — инженерный минимализм, без фреймворков

### Backend

- **FastAPI** — async web-фреймворк
- **PostgreSQL** — основная СУБД
- **SQLAlchemy + Alembic** — ORM и миграции
- **ChromaDB / Weaviate** — переключаемые векторные хранилища RAG (выбор бэкенда — из админ-консоли)
- **OpenAI / GigaChat** — мультипровайдерная LLM-цепочка (провайдер и параметры настраиваются из админ-консоли)
- **Docker + Docker Compose** — контейнеризация

### Инфраструктура

- **nginx** — статический frontend + reverse proxy для backend
- **Traefik** — reverse proxy с автоматическим SSL
- **Let's Encrypt** — SSL-сертификаты
- **VPS** — production-хостинг

## Структура проекта

```
ai-portfolio/
├── docs/                         # Документация проекта
│   ├── PROJECT_STATE.md          # Состояние проекта и решения владельца
│   ├── SPEC.md                   # Продуктовая спецификация
│   ├── IMPLEMENTATION_PLAN.md    # План реализации
│   ├── ARCHITECTURE.md           # Архитектура проекта
│   └── ADMIN_CONSOLE_ARCHITECTURE.md  # Архитектура будущей админ-консоли
├── task_history/                 # История задач по кейсу
├── src/                          # Frontend (статический сайт)
│   ├── index.html                # Главная страница
│   ├── portfolio.html            # Портфолио
│   ├── services.html             # Услуги
│   ├── contacts.html             # Контакты
│   ├── cases/                    # Страницы кейсов
│   ├── css/                      # Стили
│   ├── js/                       # JavaScript (виджет чата, API-клиент)
│   ├── assets/                   # Изображения
│   ├── Dockerfile                # Dockerfile frontend
│   └── nginx.conf                # Конфигурация nginx
├── backend/                      # Backend (FastAPI)
│   ├── app/                      # Исходный код приложения
│   │   ├── api/                  # API endpoints
│   │   │   ├── admin/            # Admin console API (Dashboard, KB, Logs, Conversations)
│   │   │   ├── chat.py           # Public chat endpoint
│   │   │   └── health.py         # Health check
│   │   ├── core/                 # Конфигурация, БД
│   │   ├── models/               # SQLAlchemy модели
│   │   ├── repositories/         # Репозитории
│   │   ├── schemas/              # Pydantic-схемы
│   │   └── services/             # Бизнес-логика
│   ├── migrations/               # Alembic-миграции
│   ├── tests/                    # Тесты
│   ├── requirements.txt          # Зависимости Python
│   ├── alembic.ini               # Конфигурация Alembic
│   ├── Dockerfile                # Dockerfile backend
│   ├── .dockerignore             # Исключения для Docker-образа
│   └── .env.example              # Шаблон переменных окружения backend
├── docker-compose.yml            # Docker Compose (Source of Truth)
├── .env.example                  # Шаблон переменных окружения проекта
├── .gitignore                    # Исключения для Git
├── attachments/                # Входные материалы и брендинг
└── README.md                     # Этот файл
```

## Быстрый старт (Production-like)

### 1. Подготовить окружение

```bash
cp .env.example .env
# Заполнить .env реальными значениями:
# - OPENAI_API_KEY         (обязательно — API key)
# - ADMIN_API_TOKEN        (обязательно для admin endpoints)
# - POSTGRES_PASSWORD      (обязательно)
# - DATABASE_URL           (обязательно, формируется из POSTGRES_*)
# - CORS_ORIGINS           (обязательно)
# - GIGACHAT_AUTH_KEY      (опционально — API key fallback-провайдера)
# Параметры провайдеров (model, temperature, max_tokens, base_url)
# задаются через админку после запуска, а не в .env.
```

### 2. Запустить проект

```bash
docker compose up -d --build
```

> **Примечание:** проект управляется через Docker Compose v2 (`docker compose`). Устаревший `docker-compose` v1 не используется; ручной запуск контейнеров через `docker run` не является штатным способом эксплуатации.

### 3. Проверить работоспособность

```bash
# Health check backend
curl -s http://localhost:8000/health

# AI-ассистент
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Какие услуги вы предоставляете?"}'

# Публичный API карточек проектов (без авторизации)
curl -s http://localhost:8000/project-cards

# Admin console (требуется ADMIN_API_TOKEN)
curl -s -H "Authorization: Bearer $ADMIN_API_TOKEN" http://localhost:8000/admin/dashboard
```

## Локальная разработка backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Заполнить .env (OPENAI_API_KEY, DATABASE_URL, ADMIN_API_TOKEN, ...)
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Локальная разработка frontend

```bash
cd src
python -m http.server 8000
# Открыть http://localhost:8000
```

## Кейсы

В портфолио представлены 13 реализованных проектов:

1. **AI Curator** — AI-ассистент для образовательных платформ (LMS + База знаний)
2. **AI Data Assistant** — Анализ файлов через чат с AI (CSV/Excel/JSON/DOCX)
3. **Review Flow** — Автоматизация работы с отзывами (Controlled Hybrid + RAG)
4. **Review Auto Responder** — Автоответчик на отзывы с мультипровайдерной LLM-цепочкой
5. **Assistant Flow** — Мультимодальный AI-ассистент для обработки заявок клиентов
6. **Meeting Audit Bot** — Telegram-бот аудита встреч и звонков (STT + LLM)
7. **Lead Qualification** — AI-система квалификации лидов из Website и Telegram
8. **HR Assistant** — Telegram-бот HR-автоматизации (резюме, matching, multimedia)
9. **HR Assistant — LoRA Fine-Tuning** — LoRA-дообучение Qwen2.5 для matching-модели
10. **Telegram Intake Bot** — Telegram-бот первичной поддержки и сбора лидов
11. **Telegram Onboarding Bot** — Адаптивный onboarding-бот с сертификацией
12. **Retail Group** — Голосовой AI-консультант для ритейла (B2B case story)
13. **Prompt Review** — Автоматическая проверка качества промптов

## AI-ассистент

Встроенный чат-виджет позволяет посетителям задавать вопросы о:

- кейсах в портфолио;
- услугах и технологиях;
- компетенциях AI-инженера.

Ассистент использует:
- RAG (Retrieval-Augmented Generation) на базе ChromaDB;
- OpenAI как основного провайдера;
- GigaChat как fallback-провайдер;
- файловый кеш ответов для снижения стоимости API.

Параметры LLM-провайдеров (model, temperature, max_tokens, base_url, активный/fallback статус)
управляются через административную консоль и хранятся в PostgreSQL. API-ключи задаются только в `.env`.

## Развёртывание

Краткий запуск production-like окружения описан в разделе **Быстрый старт**. Полная инструкция по развёртыванию поддерживается в актуальном состоянии по решению владельца проекта.

## Статус

AI Portfolio развёрнут и доступен по адресу https://ai.alex-n8n.site. Кейсы публикуются как самостоятельные портфельные активы с live demo, GitHub-репозиториями и документацией. Репозиторий находится под управлением Git.

Следующие этапы:
- Завершение перевода всех кейсов на единый AIP v1.1 лендинг-шаблон
- Актуализация деплоймент-валидации для legacy-кейсов

## Лицензия

© 2024 AI Portfolio. Все права защищены.
