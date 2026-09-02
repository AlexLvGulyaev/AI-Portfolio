# 🧭 Матрица компетенций AI Portfolio

Какие инженерные компетенции подтверждает портфель и чем именно: каждая строка ссылается на конкретные проекты, где компетенция реализована, — по принципу «компетенция подтверждается реализацией».

Технологические термины расшифрованы в [глоссарии](GLOSSARY.md); полный состав портфеля — в [обзоре портфеля](PORTFOLIO_OVERVIEW.md).

---

## 🧩 Прикладные и архитектурные компетенции

| Компетенция | Чем подтверждена |
|-------------|------------------|
| **RAG: базы знаний и диалоговый поиск по документации** | AI Curator (KB + RAG + админ-консоль допуска источников), Assistant Flow (мультимодальная RAG-платформа), Review Flow (LLM + RAG по отзывам) |
| **Проектирование контролируемых AI-циклов** («AI готовит — человек решает») | Review Flow — Controlled Hybrid с staff-контуром |
| **AI-классификация входящих и интеграция с CRM** | Lead Qualification (n8n-конвейер, AI-классификация, scoring, CRM) |
| **Telegram-боты: приём обращений, FAQ, сбор лидов** | Telegram Intake Bot; Telegram Onboarding Bot (FSM-сценарии, RBAC) |
| **HR-автоматизация: резюме, matching, онбординг** | HR Assistant (резюме, matching, мультимедийные ответы), HR Assistant — LoRA Fine-Tuning, Telegram Onboarding Bot |
| **Голосовые сценарии: транскрибация и анализ** | Meeting Audit Bot (STT, мультипровайдерный анализ, трейсы); Retail Group (пресейл голосового ассистента первой линии, пилотный план и экономика) |
| **Генерация мультимедиа из LLM-пайплайнов** | HR Assistant (TTS-ответы, генерация изображений) |
| **Диалоговый анализ данных с отчётами** | AI Data Assistant (графики, DOCX-отчёты, Docker E2E-тесты) |
| **Контроль качества LLM-промптов** | Prompt Review (автоматический анализ качества и рекомендации) |

## ⚙️ Технологический стек

| Технология | Где применена |
|------------|---------------|
| **Python, FastAPI** | Backend ключевых LLM-проектов портфеля: AI Curator, Assistant Flow, Review Flow, AI Data Assistant, Meeting Audit Bot |
| **PostgreSQL** | Хранение данных продуктов (Assistant Flow) и самой платформы AI Portfolio |
| **React** | Интерфейсы Review Flow и Assistant Flow; админ-консоль AI Portfolio |
| **Векторные базы: ChromaDB / Weaviate** | Assistant Flow (ChromaDB); платформа AI Portfolio — переключаемые бэкенды RAG (активный Weaviate) |
| **Мультипровайдерность LLM: OpenAI / GigaChat** | AI Curator, Review Auto Responder, Meeting Audit Bot, AI Data Assistant и сама платформа (переключение провайдера без изменения кода) |
| **n8n (workflow-автоматизация)** | Lead Qualification |
| **Docker Compose, E2E-тестирование** | AI Data Assistant (Docker E2E), платформа AI Portfolio (compose-развёртывание) |
| **Telegram Bot API** | Meeting Audit Bot, HR Assistant, Telegram Intake Bot, Telegram Onboarding Bot |

## 🛠️ Инженерные практики (что отличает внедрение от демо)

| Практика | Где реализована |
|----------|-----------------|
| **Eval-регрессия ассистента на контрольном наборе** | AI Portfolio — контрольные eval-прогоны каждой версии ассистента, публичный отчёт: [`docs/AI_EVAL_REPORT.md`](AI_EVAL_REPORT.md) |
| **Допуск источников к базе знаний (admission gate, fail-closed)** | AI Portfolio — только документация, прошедшая проверку качества, попадает в KB ассистента |
| **Операционные консоли** | AI Portfolio (логи, диалоги, аудит, retrieval, допуск) — наблюдаемость промптов, retrieval и действий оператора |
| **RBAC и операторские контуры** | Review Auto Responder (demo-RBAC), Telegram Onboarding Bot (RBAC тем), Review Flow (staff-контур) |
| **Трейсинг исполнения** | Meeting Audit Bot (execution-трейсы), AI Portfolio (операционные логи исполнения) |

## 🔬 ML-глубина

| Компетенция | Чем подтверждена |
|-------------|------------------|
| **Дообучение LLM под задачу (fine-tuning, LoRA)** | HR Assistant — LoRA Fine-Tuning: LoRA-дообучение Qwen2.5 под matching-модель HR-ассистента |
| **Машинное обучение в связке с продуктом** | LoRA-эксперименты ориентированы на matching-модель HR-ассистента: подбор кандидатов под вакансии |

---

*Практики инженерной среды разработки проектов описаны в [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). Для вопросов о применимости опыта к вашей задаче — контакты в [FAQ](FAQ.md).*

---

## 📚 Связанные документы

- [🗺️ `docs/PORTFOLIO_OVERVIEW.md`](PORTFOLIO_OVERVIEW.md) — карта портфеля.
- [💼 `docs/BUSINESS_VALUE.md`](BUSINESS_VALUE.md) — бизнес-ценность платформы.
- [🏠 `README.md`](../README.md) — обзор проекта.
