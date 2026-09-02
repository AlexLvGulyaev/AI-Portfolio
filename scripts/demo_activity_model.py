#!/usr/bin/env python3
"""Демо-модель активности витрины AI Portfolio — v3 «реальные ответы».

Контекст: реальная аналитика вычищена до нуля (100% прежнего трафика был
тестовым — решение владельца 02.09). Модель наполняет пустую воронку
активностью, соответствующей ожиданиям экономической модели PEf04:
>= 10 обращений/мес, конверсия визит->обращение 1-3%.

v3 (решение владельца): ответы ассистента — НАСТОЯЩИЕ. Диалоги прогоняются
через публичный POST /chat (RAG-пайплайн бэкенда), поэтому chat_sessions,
chat_messages, execution_sessions и execution_steps создаёт сам бэкенд
(реальные ответы, этапы, источники, кеш). Синтезируется только трекинг
(site_visit/case_view/inquiry — это события фронтенда, LLM не требует).
После прогона таймстампы созданных сессий сдвигаются на плановые дни.

E2E-сценарии поведения гостя (смысл для воронки):
  S1 «Отскок»        : визит и всё.
  S2 «Смотрящий»     : визит -> кейс.
  S3 «Диалоговый»    : визит -> диалог(и), кейс не открыт.
  S4 «Исследователь» : визиты -> кейсы -> диалоги, без обращения.
  S5 «Обращение»     : визиты -> кейсы -> диалог -> обращение (путь M4).
  S6 «Прямой контакт»: визит -> обращение без диалога.

Маркер синтетики: visitor_id в диапазоне d3a00000-... («demo» в hex;
колонка execution_sessions.visitor_id — UUID). Сид фиксированный.

Запуск (из корня кейса):
    python3 scripts/demo_activity_model.py
Оценка расходов: ~450 вызовов LLM по ~$0.001 = <$1 разово (PEf04: доля
API в бюджете < 5%).
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta

SEED = 20260902
NOW = datetime(2026, 9, 2, 14, 0, 0)  # наивный UTC, якорь генерации
DAYS = 30
BASE = "https://ai.alex-n8n.site"

CASES = [  # (slug, title) — реальные project_cards
    ("ai-curator", "AI Curator"),
    ("ai-data-assistant", "AI Data Assistant"),
    ("ai-portfolio", "AI Portfolio"),
    ("assistant-flow", "Assistant Flow"),
    ("competitor-monitor", "Competitor Monitor AI"),
    ("hr-assistant", "HR Assistant"),
    ("hr-assistant-lora", "HR Assistant — LoRA Fine-Tuning"),
    ("lead-qualification", "Lead Qualification"),
    ("meeting-audit-bot", "Meeting Audit Bot"),
    ("prompt-review", "Prompt Review"),
    ("retail-group", "Retail Group"),
    ("review-auto-responder", "Review Auto Responder"),
    ("review-flow", "Review Flow"),
    ("telegram-ai-gateway", "Telegram AI Gateway"),
    ("telegram-intake-bot", "Telegram Intake Bot"),
    ("telegram-onboarding-bot", "Telegram Onboarding Bot"),
]

PROFILE = {  # 600 гостей, 12 обращений = 2.0% (полоса PEf04 1-3%)
    "S1": 360, "S2": 48, "S3": 108, "S4": 42, "S5": 10, "S6": 2,
}

# Вопросы-открытия (первое сообщение сессии) — разнообразие против кеша.
OPENERS = [
    "Нужна автоматизация приёма заявок из Telegram — что у вас есть?",
    "Подскажите кейс про автоматический ответ на отзывы клиентов",
    "Как у вас устроена квалификация лидов?",
    "Есть ли решение для базы знаний по внутренней документации?",
    "Что умеет AI Curator?",
    "Как быстро можно запустить бота под наш процесс?",
    "Нужен помощник для HR: ответы сотрудникам на типовые вопросы",
    "Делаете ли вы аудит встреч и встреч-саммитов?",
    "Какие кейсы у вас про мониторинг конкурентов?",
    "Можно ли автоматизировать разбор отзывов маркетплейсов?",
    "Покажи, что у вас есть для работы с промптами команды",
    "Как подступиться к автоматизации отчётности по сделкам?",
    "Ищу решение для первичной обработки обращений клиентов",
    "Что нужно от нас, чтобы стартовать проект?",
    "Сколько стоит запуск ассистента на наших документах?",
    "Есть ли у вас кейс про LoRA-дообучение моделей?",
]
FOLLOWUPS = [
    "А сколько это стоит и какие сроки?",
    "Что нужно от нас для старта?",
    "Есть ли похожий кейс поближе к нашей задаче?",
    "Как устроена интеграция с CRM?",
    "Кто обслуживает решение после запуска?",
    "Можно ли увидеть демо этого кейса?",
]
CASE_OPENERS = {
    "telegram-intake-bot": "Подойдёт ли Telegram Intake Bot для приёма заявок из Telegram-канала?",
    "hr-assistant-lora": "Как работает HR-ассистент на базе LoRA-дообучения?",
    "ai-curator": "Что делает AI Curator и как он собирает материалы курса?",
    "lead-qualification": "Как в кейсе Lead Qualification квалифицируются лиды?",
    "prompt-review": "Как устроено ревью промптов в кейсе Prompt Review?",
    "review-auto-responder": "Как работает автоответчик на отзывы?",
    "meeting-audit-bot": "Что умеет Meeting Audit Bot?",
    "retail-group": "Что сделано в кейсе Retail Group?",
}

RNG = random.Random(SEED)
OP_SQL: list[str] = []
CHAT_PLAN: list[dict] = []  # {visitor, ts, questions[]}


def demo_ip() -> str:
    return f"203.0.113.{RNG.randint(2, 254)}"


def weighted_ts() -> datetime:
    day = RNG.randint(0, DAYS - 1)
    hour = max(9, min(23, int(abs(RNG.gauss(14, 3.5)))))
    ts = NOW - timedelta(days=day, hours=NOW.hour - hour, minutes=RNG.randint(0, 59))
    if ts > NOW:
        ts -= timedelta(days=1)
    return ts


def q(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def op_log(event_type: str, ts: datetime, visitor: str, path: str, meta: dict) -> None:
    meta = {"visitor_id": visitor, "ip": demo_ip(),
            "user_agent": "Mozilla/5.0 (demo-activity-model)", **meta}
    OP_SQL.append(
        "INSERT INTO operational_logs (id, event_type, session_id, user_id, source, "
        "query, response, model_name, provider_key, from_cache, response_time_ms, "
        "status, error_message, log_metadata, created_at, execution_id) VALUES ("
        f"{q(str(uuid.uuid4()))}, {q(event_type)}, NULL, NULL, 'web', {q(path)}, NULL, "
        f"NULL, NULL, NULL, NULL, 'ok', NULL, {q(json.dumps(meta, ensure_ascii=False))}, "
        f"{q(ts)}, NULL);"
    )


def demo_ip() -> str:
    return f"203.0.113.{RNG.randint(2, 254)}"


def make_visitor(scenario: str, idx: int) -> None:
    visitor = f"d3a00000-0000-4000-8000-{uuid.UUID(int=RNG.getrandbits(96), version=4).hex[:12]}"
    base = weighted_hour_ts()

    n_visits = RNG.randint(1, 2) if scenario in ("S1", "S2", "S6") else RNG.randint(2, 4)
    cases = RNG.sample(CASES, k=RNG.randint(1, 2))
    cur = base
    for i in range(n_visits):
        if i:
            cur += timedelta(minutes=RNG.randint(3, 40))
        path = "/" if scenario == "S1" else RNG.choice(
            ["/", f"/cases/{cases[0][0]}.html", "/contacts.html"])
        op_log("site_visit", cur, visitor, path, {})

    if scenario == "S1":
        return
    if scenario == "S6":
        inquiry(cur + timedelta(minutes=RNG.randint(2, 15)), visitor,
                "telegram" if RNG.random() < 0.7 else "email")
        return
    if scenario == "S2":
        slug, title = cases[0]
        case_view(cur + timedelta(minutes=RNG.randint(2, 20)), visitor, slug, title)
        return
    if scenario == "S3":
        for _ in range(RNG.randint(1, 2)):
            cur += timedelta(minutes=RNG.randint(5, 45))
            plan_chat(visitor, cur, None)
        return
    if scenario == "S4":
        for slug, title in cases:
            cur += timedelta(minutes=RNG.randint(3, 25))
            case_view(cur, visitor, slug, title)
        for _ in range(RNG.randint(1, 2)):
            cur += timedelta(minutes=RNG.randint(5, 40))
            plan_chat(visitor, cur, cases[0] if RNG.random() < 0.5 else None)
        return
    if scenario == "S5":
        for slug, title in cases[: RNG.randint(1, 2) + 1]:
            cur += timedelta(minutes=RNG.randint(3, 25))
            case_view(cur, visitor, slug, title)
        cur += timedelta(minutes=RNG.randint(5, 40))
        plan_chat(visitor, cur, cases[0])
        cur += timedelta(minutes=RNG.randint(2, 30))
        inquiry(cur, visitor, "telegram" if RNG.random() < 0.7 else "email")


def weighted_hour_ts() -> datetime:
    day = RNG.randint(0, DAYS - 1)
    hour = max(9, min(23, int(abs(RNG.gauss(14, 3.5)))))
    ts = NOW - timedelta(days=day, hours=NOW.hour - hour, minutes=RNG.randint(0, 59))
    if ts > NOW:
        ts -= timedelta(days=1)
    return ts


def case_view(ts, visitor, slug, title):
    op_log("case_view", ts, visitor, f"/cases/{slug}.html",
           {"card_slug": slug, "card_title": title})


def inquiry(ts, visitor, channel):
    label = "Открыть в Telegram" if channel == "telegram" else "Написать на email"
    op_log("inquiry", ts, visitor, "/contacts.html", {"channel": channel, "label": label})


def plan_chat(visitor: str, ts: datetime, case: tuple[str, str] | None) -> None:
    questions = []
    if case:
        slug, title = case
        questions.append(CASE_OPENERS.get(slug, f"Расскажите про кейс «{title}»"))
        if RNG.random() < 0.6:
            questions.append(RNG.choice(FOLLOWUPS))
    else:
        questions.append(RNG.choice(OPENERS))
        for _ in range(RNG.randint(0, 2)):
            questions.append(RNG.choice(FOLLOWUPS))
    CHAT_PLAN.append({"visitor": visitor, "ts": ts.isoformat(), "questions": questions})


def chat_post(message: str, visitor: str, session_id: str | None) -> dict:
    payload: dict = {"message": message, "visitor_id": visitor}
    if session_id:
        payload["session_id"] = session_id
    req = urllib.request.Request(
        f"{BASE}/chat", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def psql_exec(sql_text: str) -> None:
    subprocess.run(
        ["docker", "exec", "-i", "ai-portfolio-postgres", "psql", "-U", "ai_portfolio",
         "-d", "ai_portfolio", "-q"],
        input=sql_text, text=True, check=True, capture_output=True,
    )


def main() -> int:
    # 1) Сценарии -> план касаний
    for scenario, count in PROFILE.items():
        for i in range(count):
            make_visitor(scenario, i)
    print(f"план: {sum(len(v['questions']) for v in CHAT_PLAN)} сообщений "
          f"в {len(CHAT_PLAN)} сессиях; трекинг-событий {len(OP_SQL)}")

    # 2) Трекинг-события (без LLM)
    psql_exec("BEGIN;\n" + "\n".join(OP_SQL) + "\nCOMMIT;")
    print("трекинг-события записаны")

    # 3) Диалоги через настоящий /chat
    shifts: list[tuple[str, str]] = []  # (session_id, planned_ts)
    errors = 0
    for i, item in enumerate(CHAT_PLAN):
        ts = datetime.fromisoformat(item["ts"])
        visitor = item["visitor"]
        sid = None
        try:
            for msg in item["questions"]:
                resp = chat_post(msg, visitor, sid)
                sid = str(resp["session_id"])
            shifts.append((sid, item["ts"]))
        except Exception as exc:  # noqa: BLE001 — демо-прогон, ошибки логируем
            errors += 1
            print(f"  !! [{i + 1}/{len(CHAT_PLAN)}] {visitor}: {exc}", file=sys.stderr)
        if (i + 1) % 25 == 0:
            print(f"  ... {i + 1}/{len(CHAT_PLAN)} сессий")
        time.sleep(0.3)

    # 4) Сдвиг таймстампов на плановые (реальные duration сохраняются)
    upd = [
        "BEGIN;",
        f"""UPDATE execution_sessions es SET started_at = s.ts::timestamp,
                 finished_at = s.ts::timestamp + (es.finished_at - es.started_at),
                 created_at  = s.ts::timestamp
             FROM (VALUES {", ".join(f"('{sid}'::uuid, '{ts}')" for sid, ts in shifts)}) AS s(sid, ts)
             WHERE es.session_id = s.sid;""",
        """UPDATE execution_steps st SET started_at = s.ts::timestamp + (st.started_at - es.started_at),
                 finished_at = s.ts::timestamp + (st.finished_at - es.started_at),
                 created_at  = s.ts::timestamp + (st.created_at - es.started_at)
             FROM execution_sessions es
             JOIN (VALUES {vals}) AS s(sid, ts) ON es.session_id = s.sid
             WHERE st.execution_session_id = es.id;""".format(
            vals=", ".join(f"('{sid}'::uuid, '{ts}')" for sid, ts in shifts)),
        f"""UPDATE chat_messages cm SET created_at = s.ts::timestamp + (cm.created_at - es.started_at)
             FROM chat_sessions cs
             JOIN execution_sessions es ON es.session_id = cs.id
             JOIN (VALUES {", ".join(f"('{sid}'::uuid, '{ts}')" for sid, ts in shifts)}) AS s(sid, ts)
               ON es.session_id = s.sid
             WHERE cm.session_id = cs.id;""",
        f"""UPDATE chat_sessions cs SET created_at = s.ts::timestamp, updated_at = s.ts::timestamp
             FROM (VALUES {", ".join(f"('{sid}'::uuid, '{ts}')" for sid, ts in shifts)}) AS s(sid, ts)
             WHERE cs.id = s.sid;""",
        "COMMIT;",
    ]
    psql_exec("\n".join(upd))
    print(f"таймстампы сдвинуты: {len(shifts)} сессий, ошибок API: {errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())