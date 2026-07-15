# Административная консоль AI Portfolio — Архитектурное решение

**Дата:** 2026-07-14
**Статус:** Проект

---

## 1. Контекст

### 1.1. Фактическое состояние

**Public Frontend AI Portfolio:**
- Технологии: vanilla HTML + CSS + JavaScript
- Расположение: `src/`
- Сервер: nginx (Docker)
- Маршрут: `/`

**Backend AI Portfolio:**
- Технологии: FastAPI + PostgreSQL + ChromaDB
- Расположение: `backend/`
- Endpoints: `/chat`, `/health`, `/`

**Инфраструктура:**
- Docker Compose: 3 сервиса (postgres, frontend, backend)
- nginx: проксирует `/chat`, `/health`, `/api` на backend
- Домен: `ai.alex-n8n.site`

### 1.2. Принципы решения

1. **Public frontend остаётся без изменений** — vanilla HTML/CSS/JS
2. **Admin frontend — отдельный React-модуль** — внутри проекта, не отдельный продукт
3. **Backend остаётся единым** — расширяется admin endpoints
4. **Маршрут admin — `/admin/`** — обслуживается nginx
5. **Переиспользование из AF/RF** — только нужные компоненты и решения
6. **Визуальное оформление — дизайн-система AI Portfolio** — не копировать стили AF/RF

---

## 2. Структура admin frontend-модуля

### 2.1. Каталог

```
ai-portfolio/
├── admin/                          # Новый frontend-модуль
│   ├── package.json               # Зависимости React + Vite
│   ├── vite.config.ts             # Конфигурация сборки
│   ├── tsconfig.json              # TypeScript конфигурация
│   ├── index.html                 # Entry point для admin
│   ├── Dockerfile                 # Сборка admin frontend
│   └── src/
│       ├── main.tsx               # React entry point
│       ├── App.tsx                # Root component + routing
│       ├── api/
│       │   └── client.ts          # API client для backend
│       ├── auth/
│       │   └── api.ts             # Auth utilities
│       ├── components/            # Reusable UI components
│       │   ├── Layout.tsx         # Admin layout
│       │   ├── Navigation.tsx     # Side navigation
│       │   ├── ProtectedRoute.tsx # Auth guard
│       │   ├── StatusBadge.tsx    # Status badges
│       │   ├── MetricCard.tsx     # Dashboard cards
│       │   ├── EmptyState.tsx     # Empty state placeholder
│       │   ├── LoadingState.tsx   # Loading spinner
│       │   └── ...
│       ├── pages/
│       │   ├── DashboardPage.tsx  # Dashboard (Overview)
│       │   ├── LogsPage.tsx       # Logs (Operational)
│       │   ├── ConversationsPage.tsx # Conversations (Operational)
│       │   ├── KnowledgeBasePage.tsx # Knowledge Base (Operational)
│       │   ├── ProvidersPage.tsx  # Providers (Configuration)
│       │   ├── ModelsPage.tsx     # Models (Configuration)
│       │   ├── CachePage.tsx      # Cache (Utility)
│       │   ├── HealthPage.tsx     # Health (Monitoring)
│       │   └── AnalyticsPage.tsx  # Analytics (Dashboard)
│       ├── styles/
│       │   └── globals.css        # AI Portfolio design system
│       └── utils/
│           └── helpers.ts         # Utility functions
├── src/                           # Public frontend (без изменений)
├── backend/                       # Backend (расширяется)
└── docker-compose.yml             # Docker (расширяется)
```

### 2.2. Технологический стек admin

| Компонент | Технология | Источник |
|-----------|-----------|----------|
| **Framework** | React 18.3 | AF admin-ui |
| **Language** | TypeScript 5.6 | AF admin-ui |
| **Build tool** | Vite 5.4 | AF admin-ui |
| **Router** | react-router-dom 6.28 | AF admin-ui |
| **Styling** | CSS (AI Portfolio design) | Новый |

**Примечание:** Review Flow использует React 19 + JavaScript, Assistant Flow — React 18 + TypeScript. TypeScript предпочтительнее для типобезопасности.

---

## 3. Способ сборки

### 3.1. Vite конфигурация

```typescript
// admin/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/admin/",              // Базовый путь для static assets
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  server: {
    port: 5174,                 // Локальная разработка (не 5173 — занято AF)
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

### 3.2. Package.json scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  }
}
```

### 3.3. Dockerfile для admin

```dockerfile
# admin/Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html/admin
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 4. Способ публикации по /admin/

### 4.1. nginx конфигурация

```nginx
# Добавить в существующий src/nginx.conf

# Admin frontend (статика)
location /admin/ {
    alias /usr/share/nginx/html/admin/;
    try_files $uri $uri/ /admin/index.html;
}

# Admin API endpoints
location /admin-api/ {
    proxy_pass http://ai-portfolio-backend:8000/admin/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### 4.2. Альтернатива: единый nginx контейнер

Вместо отдельного контейнера для admin, использовать существующий nginx с двумя сборками:

```
nginx container/
├── /usr/share/nginx/html/          # Public frontend
│   ├── index.html
│   ├── portfolio.html
│   ├── services.html
│   ├── contacts.html
│   ├── cases/
│   ├── css/
│   └── js/
└── /usr/share/nginx/html/admin/   # Admin frontend
    ├── index.html
    └── assets/
```

---

## 5. Интеграция с существующим nginx

### 5.1. Вариант A: Единый nginx контейнер (рекомендуется)

```
docker-compose.yml:
  ai-portfolio-frontend:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./src:/usr/share/nginx/html:ro
      - admin-dist:/usr/share/nginx/html/admin:ro
```

**Преимущества:**
- Один контейнер nginx
- Минимальные изменения
- Проще deployment

### 5.2. Вариант B: Два nginx контейнера

```
docker-compose.yml:
  ai-portfolio-frontend:
    # Public frontend (существующий)
    
  ai-portfolio-admin:
    # Admin frontend (новый)
```

**Преимущества:**
- Изоляция public и admin
- Возможность независимого масштабирования

**Рекомендация:** Вариант A на первом этапе.

---

## 6. Интеграция с единым backend

### 6.1. Новые admin endpoints

```
backend/app/api/
├── __init__.py
├── health.py                    # Существующий
├── chat.py                      # Существующий
└── admin/                       # Новые admin endpoints
    ├── __init__.py
    ├── overview.py              # Dashboard
    ├── logs.py                  # Logs (из RF)
    ├── conversations.py         # Conversations
    ├── knowledge_base.py        # Knowledge Base
    ├── providers.py             # Providers (из RF)
    ├── models.py                # Models
    ├── cache.py                 # Cache
    ├── health_admin.py          # Health (расширенный)
    └── analytics.py             # Analytics (из RF)
```

### 6.2. Auth middleware

```python
# backend/app/api/admin/dependencies.py

from fastapi import Header, HTTPException

async def require_admin(x_role: str = Header(None)):
    """Simple admin auth for MVP."""
    if x_role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return True
```

### 6.3. Router registration

```python
# backend/app/main.py

from app.api.admin import (
    overview_router,
    logs_router,
    conversations_router,
    knowledge_base_router,
    providers_router,
    models_router,
    cache_router,
    health_admin_router,
    analytics_router,
)

# Admin routers
app.include_router(overview_router, prefix="/admin", tags=["admin"])
app.include_router(logs_router, prefix="/admin", tags=["admin"])
app.include_router(conversations_router, prefix="/admin", tags=["admin"])
# ... и т.д.
```

---

## 7. Перечень компонентов AF/RF для переноса

### 7.1. Backend — копировать без изменений

| Компонент | Источник | Назначение |
|-----------|----------|------------|
| `logs.py` | Review Flow | Logs API endpoint |
| `providers.py` | Review Flow | AI Providers management |
| `healthcheck_service.py` | Assistant Flow | Health checks service |
| `observability_service.py` | Assistant Flow | Session observability |

### 7.2. Backend — адаптировать

| Компонент | Источник | Адаптация |
|-----------|----------|-----------|
| `overview.py` | Assistant Flow | Адаптировать под AI Portfolio KB |
| `documents.py` | Assistant Flow | Адаптировать под AI Portfolio Knowledge Base |
| `analytics.py` | Review Flow | Адаптировать под AI Portfolio метрики |

### 7.3. Frontend — копировать с минимальной адаптацией

| Компонент | Источник | Адаптация |
|-----------|----------|-----------|
| `Layout.tsx` | Assistant Flow | Переименовать, адаптировать navigation |
| `Navigation.tsx` | Assistant Flow | Адаптировать пункты меню |
| `ProtectedRoute.tsx` | Assistant Flow | Без изменений |
| `StatusBadge.tsx` | Assistant Flow | Без изменений |
| `MetricCard.tsx` | Assistant Flow | Без изменений |
| `EmptyState.tsx` | Assistant Flow | Без изменений |
| `LoadingState.tsx` | Assistant Flow | Без изменений |
| `api/client.ts` | Assistant Flow | Изменить baseURL |
| `OverviewPage.tsx` | Assistant Flow | Адаптировать данные |
| `LogsPage.tsx` | Assistant Flow | Минимальная адаптация |
| `MemoryPage.tsx` → `ConversationsPage.tsx` | Assistant Flow | Адаптировать под ChatSession |
| `DocumentsPage.tsx` → `KnowledgeBasePage.tsx` | Assistant Flow | Адаптировать под KB |
| `AiProvidersPage.jsx` → `ProvidersPage.tsx` | Review Flow | Конвертировать JSX → TSX |
| `AnalyticsPage.jsx` → `AnalyticsPage.tsx` | Review Flow | Конвертировать JSX → TSX |

### 7.4. Frontend — создавать заново

| Страница | Причина |
|----------|---------|
| `CachePage.tsx` | Новая функциональность |
| `ModelsPage.tsx` | Новая функциональность (управление моделями провайдеров) |

---

## 8. Перечень компонентов, требующих адаптации

### 8.1. Существенная адаптация

| Компонент | Источник | Изменения |
|-----------|----------|-----------|
| **Knowledge Base** | AF Documents | AF хранит документы в БД, AI Portfolio — JSON + ChromaDB |
| **Overview/Dashboard** | AF Overview | Разные метрики (сессии vs документы) |
| **Analytics** | RF Analytics | Разные метрики (reviews vs conversations) |

### 8.2. Минимальная адаптация

| Компонент | Источник | Изменения |
|-----------|----------|-----------|
| **Logs** | RF Logs | Только API URL |
| **Providers** | RF Providers | Только API URL |
| **Sessions → Conversations** | AF Memory | Переименование сущностей |

### 8.3. Auth

Assistant Flow использует сложную auth-систему с JWT токенами. Для MVP AI Portfolio:

```typescript
// admin/src/auth/api.ts

const ADMIN_TOKEN_KEY = "ai_portfolio_admin_token";

export function getAdminToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY);
}

export function setAdminToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

export function clearAdminToken(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}

export function isAdmin(): boolean {
  return !!getAdminToken();
}
```

Backend:
```python
# Простой header-based auth для MVP
async def require_admin(x_role: str = Header(None)):
    if x_role != "admin":
        raise HTTPException(status_code=403)
```

---

## 9. Изменения Docker Compose

### 9.1. Добавить сборку admin

```yaml
# docker-compose.yml

services:
  # ... существующие сервисы ...

  # Admin frontend build stage (multi-stage build)
  ai-portfolio-admin-build:
    build:
      context: ./admin
      dockerfile: Dockerfile
    volumes:
      - admin-dist:/app/dist

volumes:
  # ... существующие volumes ...
  admin-dist:
```

### 9.2. Интеграция с nginx

**Вариант A (рекомендуется):** Модифицировать существующий frontend Dockerfile для включения admin:

```dockerfile
# src/Dockerfile (модификация)

# Stage 1: Build admin
FROM node:20-alpine AS admin-builder
WORKDIR /admin
COPY admin/package*.json ./
RUN npm ci
COPY admin/ ./
RUN npm run build

# Stage 2: Build frontend
FROM nginx:alpine
COPY --from=admin-builder /admin/dist /usr/share/nginx/html/admin
COPY src/ /usr/share/nginx/html/
COPY src/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 9.3. Полный docker-compose с admin

```yaml
# docker-compose.yml (изменённый)

services:
  ai-portfolio-postgres:
    # Без изменений

  ai-portfolio-backend:
    # Без изменений

  ai-portfolio-frontend:
    build:
      context: .
      dockerfile: src/Dockerfile.admin  # Новый Dockerfile
    restart: always
    container_name: ai-portfolio
    networks:
      - ai-portfolio-network
    depends_on:
      - ai-portfolio-backend
```

---

## 10. Изменения SOT-документов

### 10.1. PROJECT_STATE.md

Добавить раздел:
```markdown
## Административная консоль

**Технологии:** React 18.3 + TypeScript 5.6 + Vite 5.4

**Маршрут:** `/admin/`

**Источники компонентов:**
- Assistant Flow: Layout, Navigation, Logs, Sessions, Documents
- Review Flow: Providers, Analytics, Logs API

**Auth:** Header-based (X-Role: admin) для MVP
```

### 10.2. IMPLEMENTATION_PLAN.md

Добавить этап:
```markdown
## Этап 6: Административная консоль

### Цель
Реализовать административную консоль для управления AI Portfolio.

### Состав работ
| Работа | Описание | Зависит от |
|--------|----------|------------|
| Admin Backend API | Регистрация admin endpoints | Этап 3 |
| Admin Frontend Module | Создание React-модуля | — |
| Docker Integration | Интеграция admin в docker-compose | Admin Frontend |
| nginx Configuration | Настройка /admin/ маршрута | Docker Integration |

### Критерии завершения
- [ ] Admin API endpoints работают
- [ ] Admin frontend доступен по /admin/
- [ ] Dashboard отображает статистику
- [ ] Logs отображаются
- [ ] Conversations отображаются
- [ ] Knowledge Base управляется
- [ ] Providers настраиваются
```

### 10.3. SPEC.md

Не требует изменений — административная консоль не является частью публичного продукта.

---

## 11. Рабочие пространства

### 11.1. Dashboard (Overview)

**Тип:** Overview Workspace

**Основа:** Assistant Flow `OverviewPage.tsx`

**Компоненты:**
- Статистика сессий
- Статус AI провайдеров
- Статус базы знаний
- Статус системы

### 11.2. Logs (Operational Workspace)

**Тип:** Operational Workspace

**Основа:** Review Flow `LogsPage.jsx`

**Компоненты:**
- Фильтры: время, модель, статус
- Список логов
- Детализация лога

**Operational Pattern:** Left panel (filters + list) + Right panel (detail)

### 11.3. Conversations (Operational Workspace)

**Тип:** Operational Workspace

**Основа:** Assistant Flow `MemoryPage.tsx`

**Компоненты:**
- Фильтры: время, провайдер, статус
- Список сессий
- Детализация сессии (история диалога)

**Operational Pattern:** Left panel (filters + list) + Right panel (detail)

### 11.4. Knowledge Base (Operational Workspace)

**Тип:** Operational Workspace

**Основа:** Assistant Flow `DocumentsPage.tsx`

**Компоненты:**
- Список документов KB
- Просмотр документа
- Reindex
- Статус ChromaDB

**Operational Pattern:** Left panel (list) + Right panel (detail)

### 11.5. Providers (Configuration Workspace)

**Тип:** Configuration Workspace

**Основа:** Review Flow `AiProvidersPage.jsx`

**Компоненты:**
- Список провайдеров
- Активация провайдера
- Тестирование провайдера
- Fallback настройка

**Layout:** Static configuration panel

### 11.6. Models (Configuration Workspace)

**Тип:** Configuration Workspace

**Основа:** Review Flow `AiProvidersPage.jsx` (модели внутри провайдеров)

**Компоненты:**
- Список моделей провайдера
- Выбор активной модели

**Layout:** Static configuration panel

### 11.7. Cache (Utility Workspace)

**Тип:** Utility Workspace

**Основа:** Новая реализация

**Компоненты:**
- Статистика кеша
- Очистка кеша
- Просмотр записей кеша

**Layout:** Simple utility panel

### 11.8. Health (Monitoring Workspace)

**Тип:** Monitoring Workspace

**Основа:** Assistant Flow health checks

**Компоненты:**
- Статус PostgreSQL
- Статус ChromaDB
- Статус AI провайдеров
- Статус API

**Layout:** Monitoring dashboard

### 11.9. Analytics (Analytics Workspace)

**Тип:** Analytics Workspace

**Основа:** Review Flow `AnalyticsPage.jsx`

**Компоненты:**
- Графики использования
- Метрики сессий
- Метрики провайдеров

**Layout:** Analytics dashboard

---

## 12. План реализации

### Этап 1: Backend Admin API (1-2 дня)

1. Создать `backend/app/api/admin/` структуру
2. Реализовать auth middleware
3. Перенести `logs.py` из RF
4. Перенести `providers.py` из RF
5. Создать `overview.py` с базовыми метриками

### Этап 2: Admin Frontend Module (2-3 дня)

1. Создать `admin/` каталог
2. Настроить Vite + TypeScript + React
3. Создать базовую структуру `src/`
4. Перенести Layout и Navigation из AF
5. Перенести базовые components из AF

### Этап 3: Docker Integration (0.5 дня)

1. Модифицировать `src/Dockerfile` для multi-stage build
2. Обновить `docker-compose.yml`
3. Настроить nginx для `/admin/`

### Этап 4: Рабочие пространства (3-5 дней)

1. Dashboard — OverviewPage
2. Logs — LogsPage
3. Conversations — MemoryPage
4. Knowledge Base — DocumentsPage
5. Providers — AiProvidersPage
6. Models — новая страница
7. Cache — новая страница
8. Health — health checks
9. Analytics — AnalyticsPage

### Этап 5: Тестирование и документация (1 день)

1. E2E тестирование
2. Обновление SOT-документов
3. Deployment Validation

---

## 13. Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Конфликт версий React/TypeScript | Низкая | Среднее | Использовать версии из AF |
| Сложность auth | Средняя | Среднее | Начать с простого header-based auth |
| Различия в метриках AF/RF | Средняя | Низкое | Адаптировать под AI Portfolio |
| Размер admin bundle | Низкая | Низкое | Code splitting в Vite |

---

## 14. Критерий готовности

Архитектурный каркас считается готовым, если:

- [ ] Backend имеет структуру `app/api/admin/`
- [ ] Admin endpoints зарегистрированы в FastAPI
- [ ] Создан `admin/` каталог с React-приложением
- [ ] Admin frontend собирается через Vite
- [ ] nginx обслуживает `/admin/` маршрут
- [ ] Docker Compose собирает admin в составе единого контейнера
- [ ] Базовый Layout и Navigation работают
- [ ] Заглушки страниц для всех 9 рабочих пространств созданы
- [ ] PROJECT_STATE.md обновлён
- [ ] IMPLEMENTATION_PLAN.md обновлён