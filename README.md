# AI Portfolio — Персональный сайт AI-инженера

Персональный сайт AI-инженера с портфолио реализованных проектов, интегрированным AI-ассистентом и информацией об услугах по AI-автоматизации.

## Онлайн-версия

**Сайт доступен по адресу:** https://ai.alex-n8n.site

## О проекте

Сайт представляет AI-инженера, специализирующегося на автоматизации бизнес-процессов с помощью искусственного интеллекта.

**Состав проекта:**

- **Главная страница** — представление и превью кейсов
- **Портфолио** — каталог всех реализованных проектов (7 кейсов)
- **Услуги** — информация о решаемых задачах и технологиях
- **Контакты** — способы связи
- **AI-ассистент** — встроенный чат-виджет для вопросов о кейсах и услугах

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
- **ChromaDB** — векторное хранилище для RAG
- **OpenAI** — эмбеддинги и основная LLM (GPT-4.1-mini)
- **GigaChat** — fallback LLM-провайдер
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
# - OPENAI_API_KEY         (обязательно)
# - ADMIN_API_TOKEN        (обязательно для admin endpoints)
# - POSTGRES_PASSWORD      (обязательно)
# - DATABASE_URL           (обязательно, формируется из POSTGRES_*)
# - CORS_ORIGINS           (обязательно)
# - GIGACHAT_AUTH_KEY      (опционально, fallback-провайдер)
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

В портфолио представлены 7 реализованных проектов:

1. **Assistant Flow** — AI-ассистент для обработки заявок клиентов
2. **Review Flow** — Автоматизация работы с отзывами
3. **Lead Qualification** — AI-система квалификации лидов
4. **HR Assistant** — Telegram-бот для HR-автоматизации
5. **Prompt Review** — Автоматическая проверка промптов
6. **Telegram AI Gateway** — Шлюз для AI-моделей в Telegram
7. **Competitor Monitor AI** — Мониторинг конкурентов

## AI-ассистент

Встроенный чат-виджет позволяет посетителям задавать вопросы о:

- кейсах в портфолио;
- услугах и технологиях;
- компетенциях AI-инженера.

Ассистент использует:
- RAG (Retrieval-Augmented Generation) на базе ChromaDB;
- OpenAI GPT-4.1-mini как основную модель;
- GigaChat как fallback-провайдер;
- файловый кеш ответов для снижения стоимости API.

## Развёртывание

Полная инструкция по развёртыванию (`DEPLOYMENT_GUIDE.md`) будет подготовлена после завершения разработки по решению владельца проекта.

Краткий запуск production-like окружения описан в разделе **Быстрый старт**.

## Статус

Проект завершён в объёме уроков Prompt Engineering. Репозиторий находится под управлением Git.

Следующие этапы:
- Административная консоль
- Deployment Validation перед финальной публикацией

## Лицензия

© 2024 AI Portfolio. Все права защищены.
