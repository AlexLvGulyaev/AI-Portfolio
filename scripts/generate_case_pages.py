#!/usr/bin/env python3
"""Generate case detail HTML pages for AI Portfolio public site.

Usage:
    python3 scripts/generate_case_pages.py

Reads no external files; all content is declared below. Outputs to
src/cases/<slug>.html.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "src" / "cases"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="$description">
  <title>$title — AI Portfolio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../css/styles.css">
</head>
<body>
  <header class="header">
    <div class="header__content">
      <a href="../index.html" class="header__logo">
        <span class="logo__icon">◇</span>
        <span>AI Portfolio</span>
      </a>
      <nav class="nav">
        <a href="../index.html" class="nav__link">Главная</a>
        <a href="../portfolio.html" class="nav__link nav__link--active">Проекты</a>
        <a href="../services.html" class="nav__link">Услуги</a>
        <a href="../contacts.html" class="nav__link">Контакты</a>
      </nav>
    </div>
  </header>

  <main class="main">
    <div class="page">
      <article class="case-detail">
        <div class="container">
          <a href="../portfolio.html" class="case-detail__back">← Все проекты</a>

          <header class="case-detail__header">
            <div class="case-detail__title-section">
              <h1 class="case-detail__title">$title</h1>
              <div class="case-detail__tags">
                $tags_html
              </div>
            </div>
            <div class="case-detail__actions">
              $github_btn
              $demo_btn
            </div>
          </header>

          <div class="tabs" style="min-height: 300px;">
            <div class="tabs__nav">
              <button class="tabs__tab tabs__tab--active" data-tab="task">Задача</button>
              <button class="tabs__tab" data-tab="solution">Решение</button>
              <button class="tabs__tab" data-tab="result">Результат</button>
              <button class="tabs__tab" data-tab="tech">Технологии</button>
            </div>

            <div class="tabs__content">
              <div class="tabs__panel tabs__panel--active" data-panel="task">
                <div class="case-detail__section">
                  <p style="color: var(--text-secondary); line-height: 1.7;">
                    $task_lead
                  </p>
                  <p style="color: var(--text-secondary); line-height: 1.7; margin-top: var(--spacing-md);">
                    <strong style="color: var(--text-primary);">Основные проблемы:</strong>
                  </p>
                  <ul style="color: var(--text-secondary); margin-top: var(--spacing-sm); padding-left: var(--spacing-lg);">
                    $problems_html
                  </ul>
                </div>
              </div>

              <div class="tabs__panel" data-panel="solution">
                <div class="case-detail__section">
                  <p style="color: var(--text-secondary); line-height: 1.7;">
                    $solution_lead
                  </p>
                  <p style="color: var(--text-secondary); line-height: 1.7; margin-top: var(--spacing-md);">
                    <strong style="color: var(--text-primary);">Возможности системы:</strong>
                  </p>
                  <ul style="color: var(--text-secondary); margin-top: var(--spacing-sm); padding-left: var(--spacing-lg);">
                    $solution_html
                  </ul>
                </div>
              </div>

              <div class="tabs__panel" data-panel="result">
                <div class="case-detail__stats">
                  $results_html
                </div>
                <p style="color: var(--text-secondary); line-height: 1.7; margin-top: var(--spacing-lg);">
                  $result_summary
                </p>
              </div>

              <div class="tabs__panel" data-panel="tech">
                <div class="case-detail__tech">
                  $tech_html
                </div>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>
  </main>

  <footer class="footer">
    <div class="footer__content">
      <p class="footer__copyright">© 2026 AI Automation Portfolio Lab</p>
      <nav class="footer__links">
        <a href="../portfolio.html" class="footer__link">Проекты</a>
        <a href="../services.html" class="footer__link">Услуги</a>
        <a href="../contacts.html" class="footer__link">Контакты</a>
      </nav>
    </div>
  </footer>

  <script src="../js/main.js"></script>
  <script src="../js/api-client.js"></script>
  <script src="../js/chat-widget.js"></script>

  <button class="chat-launcher" id="chat-launcher" aria-label="Открыть AI-ассистента">
    <span>💬</span>
  </button>

  <div class="chat-widget" id="chat-widget">
    <div class="chat-header">
      <div class="chat-header-left">
        <div class="chat-avatar">AI</div>
        <div>
          <div class="chat-title">AI-ассистент</div>
          <div class="chat-subtitle">Спросите о кейсах и услугах</div>
        </div>
      </div>
      <button class="chat-close" id="chat-close" aria-label="Закрыть чат">×</button>
    </div>
    <div class="chat-messages" id="chat-messages"></div>
    <div class="chat-footer">
      <input id="chat-input" class="chat-input" placeholder="Напишите вопрос..." type="text" />
      <button id="chat-send" class="chat-send"><span>➤</span></button>
    </div>
  </div>
</body>
</html>
"""


def _li(items):
    return "\n".join(
        f'<li style="margin-bottom: var(--spacing-sm);">{item}</li>' for item in items
    )


def _tag(items):
    return "\n".join(f'<span class="tag">{item}</span>' for item in items)


def _tech(items):
    icon = (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        '<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>'
        '</svg>'
    )
    return "\n".join(
        f'<div class="case-detail__tech-item">{icon}{item}</div>' for item in items
    )


def _stats(stats):
    parts = []
    for stat in stats:
        parts.append(
            '<div class="case-detail__stat">'
            f'<div class="case-detail__stat-value">{stat["value"]}</div>'
            f'<div class="case-detail__stat-label">{stat["label"]}</div>'
            '</div>'
        )
    return "\n".join(parts)


CASES = [
    {
        "slug": "review-auto-responder",
        "title": "Review Auto Responder",
        "description": "Автономный AI-ассистент для ответов на отзывы: мультипровайдерный, с операторской панелью и demo-RBAC.",
        "tags": ["FastAPI", "OpenAI", "GigaChat", "LLM", "Telegram"],
        "demo_url": "https://review-auto-responder.alex-n8n.site",
        "github_url": "https://github.com/AlexLvGulyaev/review-auto-responder",
        "task_lead": "Команда поддержки получала отзывы клиентов через сайт и тратила время на ручной мониторинг страницы, определение тональности и подготовку ответов.",
        "problems": [
            "Задержки в реакции на негативные отзывы",
            "Ручная классификация тональности",
            "Отсутствие единого формата ответов",
            "Риск пропустить новый отзыв",
        ],
        "solution_lead": "Разработан автономный обработчик, который 24/7 опрашивает сайт отзывов, определяет тональность, генерирует ответ нейросетью и уведомляет оператора в Telegram.",
        "solution": [
            "Публичный сайт отзывов на FastAPI + PostgreSQL",
            "Мультипровайдерная генерация: OpenAI / GigaChat",
            "Словарный классификатор тональности без расхода токенов",
            "Операторская панель /admin с runtime-конфигом",
            "Демо-RBAC: полный и read-only токены",
            "Три контура observability: логи, трейсы, аудит",
        ],
        "result_summary": "Система обеспечивает круглосуточную обработку отзывов без пропусков, единый стиль ответов и прозрачный контроль оператора.",
        "stats": [
            {"value": "24/7", "label": "Автономная обработка"},
            {"value": "2", "label": "LLM-провайдера"},
            {"value": "3", "label": "Контура observability"},
            {"value": "18/18", "label": "Deployment Validation PASS"},
        ],
        "tech": [
            "FastAPI + SQLAlchemy 2 async",
            "PostgreSQL 16",
            "OpenAI SDK + GigaChat OAuth-адаптер",
            "asyncio + httpx",
            "Telegram Bot API",
            "Docker Compose",
        ],
    },
    {
        "slug": "ai-curator",
        "title": "AI Curator",
        "description": "AI-ассистент для образовательных платформ с LMS-интеграцией, Knowledge Base и RAG.",
        "tags": ["FastAPI", "RAG", "KB", "React", "LMS"],
        "demo_url": "https://curator.alex-n8n.site",
        "github_url": "https://github.com/AlexLvGulyaev/ai-curator",
        "task_lead": "Студенты задают однотипные вопросы о дедлайнах, заданиях и материалах, а преподаватели отвечают на них многократно в разрозненных каналах.",
        "problems": [
            "Повторяющиеся вопросы от студентов",
            "Информация разбросана между LMS и мессенджерами",
            "Нет персонализированных ответов с источниками",
            "Отсутствие аналитики проблемных тем",
        ],
        "solution_lead": "AI Curator объединяет два источника — LMS (учебный процесс) и Knowledge Base (учебные материалы) — и отвечает студентам через публичный веб-интерфейс с указанием источника.",
        "solution": [
            "Интеграция с Moodle через LMS Adapter",
            "Управляемая Knowledge Base с версионированием",
            "RAG-поиск по учебным материалам",
            "Публичный Web UI с safe demo mode",
            "Admin Console с аналитикой и отчётами",
            "Кэширование ответов и аудит диалогов",
        ],
        "result_summary": "Студенты получают ответы за секунды 24/7, преподаватели видят аналитику запросов и пробелы в материалах.",
        "stats": [
            {"value": "2", "label": "Источника данных (LMS + KB)"},
            {"value": "24/7", "label": "Ответы студентам"},
            {"value": "109", "label": "pytest-тестов"},
            {"value": "React", "label": "Web UI + Admin Console"},
        ],
        "tech": [
            "FastAPI",
            "React + Vite + Tailwind CSS",
            "Moodle LMS",
            "PostgreSQL + ChromaDB",
            "OpenAI API",
            "Docker + Traefik",
        ],
    },
    {
        "slug": "ai-data-assistant",
        "title": "AI Data Assistant",
        "description": "Data-ассистент для анализа файлов: чат, графики, DOCX-отчёты, мультипровайдерный runtime-конфиг.",
        "tags": ["FastAPI", "HTMX", "Data Analysis", "OpenAI", "GigaChat"],
        "demo_url": "https://data-assistant.alex-n8n.site",
        "github_url": "https://github.com/AlexLvGulyaev/ai-data-assistant",
        "task_lead": "Командам нужен быстрый взгляд на CSV/Excel/JSON без разворачивания BI или ручной работы в Excel, но универсальные LLM-чаты не загружают файлы и не гарантируют воспроизводимый артефакт.",
        "problems": [
            "Ручной анализ отнимает время",
            "BI-платформы избыточны для разового вопроса",
            "LLM-чаты не строят графики и не сохраняют отчёты",
            "Привязка к одному LLM-провайдеру",
        ],
        "solution_lead": "Пользователь загружает файл и общается с ассистентом на естественном языке; модель планирует действие, приложение исполняет его локально — метрики, графики и DOCX-отчёты.",
        "solution": [
            "Загрузка CSV, Excel, JSON и изображений",
            "4 типа графиков: histogram, bar, line, pie",
            "DOCX-отчёты для скачивания",
            "Мультипровайдерность: OpenAI / GigaChat / YandexGPT",
            "Runtime-конфиг оператора в /admin без рестарта",
            "Structured output + fallback-парсер",
        ],
        "result_summary": "Анализ файла превращается в чатовый диалог с воспроизводимыми артефактами, а смена провайдера занимает секунды.",
        "stats": [
            {"value": "4", "label": "Типа графиков"},
            {"value": "DOCX", "label": "Готовые отчёты"},
            {"value": "4", "label": "LLM-провайдера"},
            {"value": "18/18", "label": "Deployment Validation PASS"},
        ],
        "tech": [
            "FastAPI + Jinja2 + HTMX",
            "OpenAI Chat Completions + structured output",
            "matplotlib + python-docx",
            "Pydantic Settings",
            "Docker Compose",
        ],
    },
    {
        "slug": "meeting-audit-bot",
        "title": "Meeting Audit Bot",
        "description": "Telegram-бот аудита встреч: транскрибация AssemblyAI, мультипровайдерный LLM-анализ, веб-админка.",
        "tags": ["Telegram Bot", "STT", "FastAPI", "OpenAI", "GigaChat"],
        "demo_url": "https://meeting-audit-bot.alex-n8n.site/admin",
        "github_url": "https://github.com/AlexLvGulyaev/meeting-audit-bot",
        "task_lead": "Руководители, HR и sales-менеджеры получают записи встреч и звонков, но ручной прослушивание и разбор отнимает часы и не масштабируется.",
        "problems": [
            "Долгое ручное прослушивание записей",
            "Нет структурированной оценки диалога",
            "Сложно отслеживать качество онбординга и продаж",
            "Разные сценарии требуют разных чек-листов",
        ],
        "solution_lead": "Telegram-бот принимает аудио/видео, AssemblyAI разделяет речь по спикерам, LLM анализирует диалог по выбранному сценарию, а веб-админка управляет провайдерами и сценариями.",
        "solution": [
            "Приём аудио и видео в Telegram",
            "Диаризация спикеров через AssemblyAI",
            "Сценарии аудита: онбординг, B2B-звонок, онлайн-урок, чат клиента",
            "Мультипровайдерный LLM: OpenAI / GigaChat",
            "Execution tracing по шагам обработки",
            "Дневной лимит и аудит событий",
        ],
        "result_summary": "Запись превращается в структурированный аудит с оценкой, таймкодами и возможностью смены сценария без рестарта.",
        "stats": [
            {"value": "4", "label": "Сценария аудита"},
            {"value": "2", "label": "LLM-провайдера"},
            {"value": "5", "label": "Обработок/день на пользователя"},
            {"value": "24/7", "label": "Telegram-бот"},
        ],
        "tech": [
            "FastAPI + python-telegram-bot",
            "AssemblyAI (STT + speaker labels)",
            "OpenAI SDK + GigaChat OAuth-адаптер",
            "PostgreSQL 16",
            "Docker Compose",
        ],
    },
    {
        "slug": "telegram-intake-bot",
        "title": "Telegram Intake Bot",
        "description": "Telegram-бот первичной поддержки с двумя сценариями: FAQ и сбор лидов с LLM-извлечением полей.",
        "tags": ["Telegram Bot", "Support", "FAQ", "Lead Capture"],
        "demo_url": None,
        "github_url": "https://github.com/AlexLvGulyaev/telegram-intake-bot",
        "task_lead": "Малые команды техподдержки и отделов продаж получают входящие сообщения в свободной форме: данные теряются в переписке, менеджер вручную выясняет детали.",
        "problems": [
            "Заявки и лиды приходят неструктурированно",
            "Нет единого формата передачи между сотрудниками",
            "Перемешивание ТП и продаж в одном чате",
            "Ручное уточнение обязательных полей",
        ],
        "solution_lead": "Telegram-бот ведёт короткий естественный диалог, извлекает поля через LLM с JSON Schema и отправляет структурированную заявку или лида в чат операторов.",
        "solution": [
            "Два сценария: техподдержка и сбор лидов",
            "Естественный диалог без форм",
            "LLM-извлечение с Pydantic-валидацией",
            "Детерминированные guard replies",
            "Квалификация лидов: горячий / тёплый / холодный",
            "Docker-контейнеризация",
        ],
        "result_summary": "Клиент пишет свободным текстом, а команда получает готовую заявку с нужными полями.",
        "stats": [
            {"value": "2", "label": "Сценария в одном боте"},
            {"value": "JSON", "label": "Структурированный вывод"},
            {"value": "Docker", "label": "Контейнеризация"},
            {"value": "aiogram", "label": "Telegram Bot API"},
        ],
        "tech": [
            "Python 3.12",
            "aiogram 3.x",
            "OpenAI API + JSON Schema",
            "httpx + pydantic",
            "Docker",
        ],
    },
    {
        "slug": "telegram-onboarding-bot",
        "title": "Telegram Onboarding Bot",
        "description": "Telegram-бот адаптации сотрудников: обучение, тестирование, универсальные темы и RBAC.",
        "tags": ["Telegram Bot", "Onboarding", "HR", "PostgreSQL"],
        "demo_url": None,
        "github_url": "https://github.com/AlexLvGulyaev/telegram-onboarding-bot",
        "task_lead": "HR и руководители тратят время наставников на повторяющееся объяснение базовых правил новичкам, качество онбординга нестабильно и не измеримо.",
        "problems": [
            "Нестабильное качество онбординга",
            "Субъективные критерии оценки",
            "Нет измеримого результата обучения",
            "Сложно масштабировать на сезонный найм",
        ],
        "solution_lead": "Бот ведёт сотрудника по обучающему сценарию: объясняет материал, сам решает, когда переходить к тесту, задаёт вопросы по одному, оценивает ответы и сохраняет результат в PostgreSQL.",
        "solution": [
            "Обучение + тест в одном диалоге",
            "Универсальные темы через JSON-конфиг или /new_topic",
            "Двухслойный промпт с версионированием",
            "Дедупликация вопросов по embeddings",
            "Guard-логика фаз жизненного цикла",
            "RBAC для админ-команд",
        ],
        "result_summary": "Онбординг становится измеримым и повторяемым: HR получает сохранённый в БД балл и сводку по каждому сотруднику.",
        "stats": [
            {"value": "~$0.005", "label": "Стоимость сессии"},
            {"value": "PostgreSQL", "label": "Сохранение результатов"},
            {"value": "JSON", "label": "Структурированный ответ LLM"},
            {"value": "aiogram", "label": "FSM-диалог"},
        ],
        "tech": [
            "Python 3.11",
            "aiogram 3.x FSM",
            "PostgreSQL 16 + SQLAlchemy 2 async",
            "OpenAI Chat Completions + Embeddings",
            "Docker Compose",
        ],
    },
    {
        "slug": "retail-group",
        "title": "Retail Group",
        "description": "Голосовой AI-ассистент первой линии поддержки для ритейла: пилотный план, экономика, Case Story.",
        "tags": ["Voice AI", "Presale", "n8n", "RAG"],
        "demo_url": None,
        "github_url": None,
        "task_lead": "Сеть продуктовых магазинов получает до 3 000 входящих звонков в день, около 60% из которых — типовые вопросы: часы работы, статус заказа, акции, стандартные возвраты.",
        "problems": [
            "Линейный рост трафика ведёт к линейному росту ФОТ",
            "8 операторов первой линии отвечают по шаблонам",
            "Сложные и продажные обращения не доходят до опытных операторов",
            "Нет прозрачной аналитики по темам обращений",
        ],
        "solution_lead": "Голосовой контур: телефония → ASR/STT → оркестратор n8n → LLM-классификатор → LLM + RAG / оператор → TTS → телефония. Типовые звонки закрывает ИИ, сложные эскалируются с контекстом.",
        "solution": [
            "Голосовой AI-ассистент первой линии",
            "Классификация типового / сложного обращения",
            "RAG по базе знаний + интеграция с CRM",
            "Эскалация на оператора с сохранением контекста",
            "Логи в PostgreSQL и дашборд Metabase",
            "Пилотный план на 2 недели с метриками GO/ITERATE/STOP",
        ],
        "result_summary": "Пилотная гипотеза: сокращение времени типового звонка до 15–60 секунд, высвобождение 2–3 операторов, экономия ~290 000 ₽/мес.",
        "stats": [
            {"value": "3 000", "label": "Входящих звонков/день"},
            {"value": "60%", "label": "Типовых обращений"},
            {"value": "~290k", "label": "₽/мес прогноз экономии"},
            {"value": "0,8", "label": "мес окупаемости"},
        ],
        "tech": [
            "n8n — оркестрация",
            "ASR / STT",
            "LLM: GPT-4o mini / YandexGPT / GigaChat",
            "RAG: Qdrant / ChromaDB",
            "PostgreSQL + Metabase",
            "Telegram-бот как резервный канал",
        ],
    },
]


def render(case: dict) -> str:
    github_btn = (
        f'<a href="{case["github_url"]}" class="btn btn-secondary" target="_blank" rel="noopener">GitHub</a>'
        if case.get("github_url") else '<span class="btn btn-secondary" style="opacity:.5;cursor:default;">GitHub</span>'
    )
    demo_btn = (
        f'<a href="{case["demo_url"]}" class="btn btn-primary" target="_blank" rel="noopener">Demo</a>'
        if case.get("demo_url") else '<span class="btn btn-primary" style="opacity:.5;cursor:default;">Demo</span>'
    )

    return PAGE_TEMPLATE \
        .replace("$title", case["title"]) \
        .replace("$description", case["description"]) \
        .replace("$tags_html", _tag(case["tags"])) \
        .replace("$github_btn", github_btn) \
        .replace("$demo_btn", demo_btn) \
        .replace("$task_lead", case["task_lead"]) \
        .replace("$problems_html", _li(case["problems"])) \
        .replace("$solution_lead", case["solution_lead"]) \
        .replace("$solution_html", _li(case["solution"])) \
        .replace("$results_html", _stats(case["stats"])) \
        .replace("$result_summary", case["result_summary"]) \
        .replace("$tech_html", _tech(case["tech"]))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        path = OUTPUT_DIR / f"{case['slug']}.html"
        path.write_text(render(case), encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
