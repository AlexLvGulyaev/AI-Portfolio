# DEPLOYMENT_GUIDE — AI Portfolio

**Проект:** ai-portfolio
**Версия:** 1.0 (черновик к Deployment Validation)
**Дата:** 2026-09-02
**Статус:** Source of Truth воспроизводимости развёртывания (по правилам APL)

> Документ описывает полный процесс получения работоспособного экземпляра
> AI Portfolio с нуля на чистом окружении. Критерий качества документа —
> успешное развёртывание по приведённым инструкциям (Deployment Validation),
> а не качество текста. Каждый сценарий ниже воспроизводим из состояния
> репозитория либо явно помечен как архитектурное допущение.

---

## 1. Архитектура развёртывания

| Контейнер | Образ / сборка | Роль |
|-----------|----------------|------|
| `ai-portfolio-postgres` | `postgres:15` | PostgreSQL: карточки проектов, KB-источники, диалоги, логи, аудит, настройки |
| `ai-portfolio-backend` | сборка `backend/Dockerfile` (python:3.12-slim + uvicorn) | FastAPI API: публичный сайт API, чат/RAG-оркестратор, Admin API |
| `ai-portfolio-frontend` | сборка `src/Dockerfile` (node:20-alpine → nginx:alpine) | Публичный сайт (статика) + Admin Console SPA (собирается на этапе сборки образа) |
| `ai-portfolio-chroma` | `chromadb/chroma:1.5.9` | Векторное хранилище KB (основной retrieval-бэкенд по умолчанию) |
| `ai-portfolio-weaviate` | `cr.weaviate.io/semitechnologies/weaviate:1.39.2` | Второй retrieval-бэкенд (BYOV), внутренняя сеть |

Тома (named volumes): `ai-portfolio-postgres-data`, `ai-portfolio-chroma-data`,
`ai-portfolio-weaviate-data`, `ai-portfolio-data` (файлы кеша/данных backend).

Сеть: `n8n_default` (**external**) — общая сеть хоста, в которой работает
edge-прокси (Traefik). Маршрутизация HTTPS — Traefik по меткам контейнера
`ai-portfolio-frontend` (см. §8).

Публичные точки:

- `https://<домен>/` — публичный сайт (главная = витрина, страницы кейсов, услуги, контакты);
- `https://<домен>/admin/` — Admin Console (SPA);
- API проксируется nginx'ом фронтенда: `/chat`, `/health`, `/project-cards`, `/track-visit`, `/track-event`, `/api/admin/*` → backend `:8000`.

---

## 2. Требования к окружению

| Требование | Значение |
|------------|----------|
| ОС | Linux x86_64 (проверено: Ubuntu 24.04) |
| Docker | Docker Engine + **Compose v2** (`docker compose`; v1 не используется) |
| Доступ в интернет | Нужен на этапе сборки образов (pip, npm) и для API (OpenAI, GitHub) |
| Порт 80/443 | Заняты edge-прокси (Traefik) — см. §8 |
| DNS | A-запись домена → IP хоста (см. §8.3 про домен) |
| Внешние API | OpenAI API key (обязательно), GigaChat (опционально), GitHub token (опционально, повышает лимиты GitHub API) |

Минимальный размер диска под тома на старте — <1 ГБ (корпус KB ~ десятки МБ).

---

## 3. Переменные окружения

```bash
cp .env.example .env
```

Заполнить `.env`:

| Переменная | Обязательность | Назначение |
|------------|----------------|------------|
| `POSTGRES_USER` | ✅ | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | ✅ | Пароль PostgreSQL |
| `POSTGRES_DB` | ✅ | Имя БД |
| `DATABASE_URL` | ✅ | `postgresql://<user>:<password>@ai-portfolio-postgres:5432/<db>` — хост = имя контейнера postgres |
| `OPENAI_API_KEY` | ✅ | Основной LLM-провайдер и embeddings |
| `ADMIN_API_TOKEN` | ✅ | Bearer-токен Admin API |
| `CORS_ORIGINS` | ✅ | Origin публичного сайта, например `https://ai.alex-n8n.site` |
| `KB_REPO_OWNER` | ✅ **(обязателен, compose падает без него)** | GitHub-namespace, чьи публичные репозитории допускаются как источники KB |
| `GIGACHAT_AUTH_KEY` | опционально | Fallback LLM-провайдер |
| `GITHUB_TOKEN` | опционально | Повышает лимиты GitHub API при синхронизации KB |
| `LOG_LEVEL` | опционально | Уровень логирования backend (по умолчанию `WARNING`) |
| `DEBUG` | опционально | `false` в production (по умолчанию) |
| `RAG_BACKEND` | опционально | Начальный retrieval-бэкенд: `chroma` (по умолчанию) или `weaviate`; runtime-переключение — через Admin Console |

> Параметры LLM-провайдеров (модель, temperature, max_tokens, base_url,
> активный/резервный) — не в `.env`: управляются через Admin Console и
> хранятся в PostgreSQL (`ai_provider_settings`).

---

## 4. Пошаговое развёртывание

### Шаг 1. Получить код

```bash
git clone https://github.com/AlexLvGulyaev/AI-Portfolio.git
cd AI-Portfolio
```

### Шаг 2. Заполнить `.env`

См. §3. Проверить, что `DATABASE_URL` согласован с `POSTGRES_USER/PASSWORD/DB`
и указывает на `ai-portfolio-postgres:5432`.

### Шаг 3. Внешняя сеть

Compose объявляет сеть `n8n_default` как external. На чистом хосте она
создаётся edge-стеком (§8) либо вручную:

```bash
docker network create n8n_default
```

### Шаг 4. Сборка и запуск

```bash
docker compose up -d --build
```

Сборка frontend-образа включает `npm ci && npm run build` Admin Console
(node:20-alpine) и укладку статики публичного сайта в nginx. Первый запуск
тягает базовые образы и устанавливает зависимости — ожидайте несколько минут.

Состояние: `docker compose ps` — все пять сервисов со статусом healthy
(healthchecks определены в compose для postgres, backend, chroma, weaviate).

### Шаг 5. Миграции базы данных

Миграции применяются вручную (автоматического прогона при старте нет):

```bash
docker compose exec ai-portfolio-backend alembic upgrade head
```

Alembic берёт `DATABASE_URL` из окружения контейнера (`migrations/env.py`).
Миграция `003_seed_project_cards.py` заполняет реестр 13 карточек проектов —
после неё витрина (`GET /project-cards`) наполнена без ручных действий.

Проверка версии: `docker compose exec ai-portfolio-backend alembic current`.

### Шаг 6. Проверка работоспособности

```bash
curl -s http://localhost:8000/health            # backend health
curl -s http://localhost:8000/project-cards     # 13 карточек
curl -s -H "Authorization: Bearer $ADMIN_API_TOKEN" \
     http://localhost:8000/admin/dashboard      # сводка системы
```

Публичный сайт — `https://<домен>/` (после настройки edge, §8);
Admin Console — `https://<домен>/admin/`.

### Шаг 7. Наполнение базы знаний (KB)

После первого развёртывания векторный индекс пуст — ассистент корректно
отвечает «информации нет». Наполнение выполняется администратором через
Admin Console (`/admin/` → «Источники и синхронизация»):

1. Войти в Admin Console, вставив `ADMIN_API_TOKEN` (запрос токена при входе, хранится в localStorage).
2. «Добавить GitHub-репозиторий» — селектор предлагает публичные репозитории namespace `KB_REPO_OWNER` (требование registry-only политики KB: источник привязывается к карточке проекта).
3. Для источника: построить **Preview состава** (draft-правила include/exclude) → проверить состав файлов → **Одобрить**.
4. **Синхронизировать** — прогрессбар в консоли; по завершении в консоли «Документы» видны документы и чанки.

Альтернативный путь — те же шаги через Admin API (`Bearer $ADMIN_API_TOKEN`);
эндпоинты описаны в `docs/ARCHITECTURE.md`.

> Смена активного retrieval-бэкенда (chroma/weaviate) — Admin Console →
> «Система → Retrieval» (runtime, без рестарта). Синхронизация идёт в
> активный бэкенд.

---

## 5. Admin Console

- URL: `https://<домен>/admin/` (SPA раздаётся nginx'ом контейнера `ai-portfolio-frontend`).
- Аутентификация: Bearer `ADMIN_API_TOKEN`; токен вводится на экране входа и хранится в localStorage браузера (`ai_portfolio_admin_token`).
- Разделы: Обзор, Проекты, Контент (Источники и синхронизация, Документы), Система (Retrieval, AI-настройки), Аналитика (Пресейл), Операционная консоль (Логи, Диалоги, Аудит), Справка (Обозначения).

---

## 6. Обновление развёрнутого экземпляра

```bash
git pull
docker compose build ai-portfolio-backend ai-portfolio-frontend
docker compose up -d
docker compose exec ai-portfolio-backend alembic upgrade head   # если есть новые миграции
```

> Изменения кода backend и frontend (включая Admin Console) запечены в
> образах — правка файлов на хосте не вступает в силу без ребилда.

---

## 7. Резервное копирование

Данные состояния — в named volumes:

| Volume | Что содержит |
|--------|--------------|
| `ai-portfolio-postgres-data` | Все структурированные данные (карточки, KB-реестр, диалоги, логи, настройки) |
| `ai-portfolio-chroma-data` | Векторный индекс активного по умолчанию бэкенда |
| `ai-portfolio-weaviate-data` | Векторный индекс второго бэкенда |
| `ai-portfolio-data` | Файлы backend (ретривал-кеш sqlite и др.) |

Минимальная резервная копия — дамп PostgreSQL:

```bash
docker compose exec ai-portfolio-postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > backup_$(date +%F).sql.gz
```

Восстановление векторов не требует бэкапа: полный индекс пересоздаётся
синхронизацией из GitHub-источников (§4, шаг 7).

---

## 8. Edge-инфраструктура (Traefik) и домен

### 8.1 Допущение

HTTPS-терминация выполняется внешним Traefik, работающим в той же сети
`n8n_default`. Метки маршрутизатора заданы в compose для сервиса
`ai-portfolio-frontend`:

```
traefik.http.routers.ai-portfolio-frontend.rule=Host(`ai.alex-n8n.site`)
traefik.http.routers.ai-portfolio-frontend.entrypoints=websecure
traefik.http.routers.ai-portfolio-frontend.tls.certresolver=letsencrypt
```

Требования к edge: Traefik v2/v3 с сертификат-резолвером `letsencrypt`
(Let's Encrypt) и сетью `n8n_default`. Порты 80/443 публикует именно Traefik,
не сервисы проекта.

### 8.2 Домен

Домен `ai.alex-n8n.site` зафиксирован в двух местах:
1) правило Traefik в `docker-compose.yml`;
2) `server_name` в `src/nginx.conf`.
Плюс `CORS_ORIGINS` в `.env`.

При развёртывании на другом домене заменить его в этих трёх местах до
`docker compose up`, либо направить DNS домена на хост развёртывания.

### 8.3 Валидация без публичного DNS

Если чистое окружение не имеет DNS-записи, допускается проверка через
SSH-туннель/локальный порт (публикация порта фронтенда — временное
изменение compose, не коммитящееся в репозиторий), либо тестовый домен с
A-записью на хост. TLS-цепочка (Let's Encrypt) в этом случае проверяется
отдельно или на основном хосте.

---

## 9. GeoIP-обогащение (опционально)

Гео-базы DB-IP Lite кладутся в `backend/data/geoip/` (в git не входят).
Файл отсутствует — гео-обогащение отключается graceful, все каналы работают.
Подключение: скачать базу в `backend/data/geoip/` и перезапустить backend.

---

## 10. Устранение неполадок

| Симптом | Проверка |
|---------|----------|
| Compose падает на старте с сообщением про `KB_REPO_OWNER` | Переменная не заполнена в `.env` — обязательна |
| Backend unhealthy | `docker compose logs ai-portfolio-backend`; проверить `DATABASE_URL`, доступность postgres |
| Сайт отдаётся, API 502 | nginx фронтенда не видит backend: проверить сеть `n8n_default` и статус `ai-portfolio-backend` |
| Ассистент отвечает «информации нет» на всё | KB не наполнена — пройти §4 шаг 7; проверить активный retrieval-бэкенд в «Система → Retrieval» |
| `docker compose up` не может создать сеть | `n8n_default` external — создать вручную (§4 шаг 3) или поднять edge (§8) |
| Витрина без карточек | Миграции не применены — `alembic upgrade head` (§4 шаг 5) |

---

## 11. Связанные документы

- [`docs/TZ.md`](TZ.md) — техническое задание.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура решения.
- [`README.md`](../README.md) — быстрый старт.

## 12. История изменений

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2026-09-02 | 1.0 | Первая версия: полный процесс развёртывания из фактического состояния репозитория (compose, env, миграции, KB bootstrap, edge/Traefik, backup, troubleshooting). Статус — черновик к Deployment Validation (§4.7 п.7.0) |