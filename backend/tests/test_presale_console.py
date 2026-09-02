"""
Unit-тесты presale-аналитики (§4.5, task 2026-08-30):

- tracking.TrackEventRequest: whitelist типов событий (Literal), фильтрация
  метаданных (_filter_presale_metadata);
- PresaleService: сборка шагов воронки на мокнутой сессии (запросы
  operational_logs + execution_sessions), отклонение неподдерживаемого
  периода, «всё время» (days=0).

Сессия БД мокается (конвенция suite — без живой БД/TestClient).
"""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from app.api.tracking import (
    ALLOWED_PRESALE_EVENT_TYPES,
    TrackEventRequest,
    _filter_presale_metadata,
)
from app.services.admin.presale_service import (
    ALLOWED_PERIODS,
    FUNNEL_STEPS,
    PresaleService,
)


def check(name: str, cond: bool, detail: str = "") -> bool:
    ok = bool(cond)
    print(("PASS " if ok else "FAIL ") + name + ((": " + detail) if detail and not ok else ""))
    return ok


# ----------------------------------------------------------------------
# TrackEventRequest: whitelist типов
# ----------------------------------------------------------------------

def test_track_event_request_type_whitelist():
    ok = check(
        "case_view accepted",
        TrackEventRequest(event_type="case_view").event_type == "case_view",
    )
    ok &= check(
        "inquiry accepted",
        TrackEventRequest(event_type="inquiry").event_type == "inquiry",
    )
    rejected = False
    try:
        TrackEventRequest(event_type="page_poke")  # type: ignore[arg-type]
    except ValidationError:
        rejected = True
    ok &= check("unknown event type rejected by Literal", rejected)
    ok &= check(
        "ALLOWED_PRESALE_EVENT_TYPES matches Literal",
        sorted(ALLOWED_PRESALE_EVENT_TYPES) == ["case_view", "inquiry"],
    )
    return ok


# ----------------------------------------------------------------------
# _filter_presale_metadata
# ----------------------------------------------------------------------

def test_filter_presale_metadata():
    filtered = _filter_presale_metadata(
        {
            "card_slug": "ai-portfolio",
            "card_title": "AI Portfolio",
            "external_url": "https://github.com/x",
            "channel": "telegram",
            "label": "Написать в Telegram",
            "evil_key": "x",  # не в whitelist
            "user_agent": "Mozilla ...",  # не в whitelist
            "nested": {"a": 1},  # не скаляр
            "n": 42,
            "flag": True,
        }
    )
    ok = check(
        "only whitelisted scalars survive",
        filtered
        == {
            "card_slug": "ai-portfolio",
            "card_title": "AI Portfolio",
            "external_url": "https://github.com/x",
            "channel": "telegram",
            "label": "Написать в Telegram",
            "n": 42,
            "flag": True,
        },
        repr(filtered),
    )
    ok &= check("None metadata -> {}", _filter_presale_metadata(None) == {})
    return ok


# ----------------------------------------------------------------------
# PresaleService: сборка воронки на мокнутой сессии
# ----------------------------------------------------------------------

def _service_with_events(log_counts, chat_visitors, top_cases=None, channels=None, with_prev=True):
    """Service whose db.execute returns prepared scalars in call order.

    Per operational-log step the service issues two count queries
    (events, visitors); the chat step issues one count. The funnel for a
    bounded period issues the same round once more for the previous
    period (KPI deltas), then four selects fetch rows for top_cases /
    inquiry_channels / geo_countries / geo_inquiries.
    """
    db = MagicMock()
    results = []

    def _append_step_results():
        for step in FUNNEL_STEPS:
            if step["store"] == "execution_sessions":
                results.append(SimpleNamespace(scalar=lambda v=chat_visitors: v))
            else:
                counts = log_counts[step["event_type"]]
                results.append(SimpleNamespace(scalar=lambda v=counts["events"]: v))
                results.append(SimpleNamespace(scalar=lambda v=counts["visitors"]: v))

    _append_step_results()  # текущий период
    if with_prev:
        _append_step_results()  # предыдущий период (дельты KPI)
    top_rows = [
        (c["card_slug"], c["card_title"], c["views"], c["visitors"])
        for c in (top_cases or [])
    ]
    ch_rows = [
        (c["channel"], c["events"], c["visitors"]) for c in (channels or [])
    ]
    results.append(SimpleNamespace(fetchall=lambda rows=top_rows: rows))
    results.append(SimpleNamespace(fetchall=lambda rows=ch_rows: rows))
    # Geo-агрегаты (02.09): два select'а (site_visit и inquiry) — пустые
    # выборки означают «география не определена», что не влияет на шаги.
    results.append(SimpleNamespace(fetchall=lambda: []))
    results.append(SimpleNamespace(fetchall=lambda: []))
    db.execute.side_effect = results
    return PresaleService(db)


def test_presale_funnel_steps_and_period():
    counts = {
        "site_visit": {"events": 100, "visitors": 40},
        "chat_request": {"events": 12, "visitors": 12},
        "case_view": {"events": 28, "visitors": 17},
        "inquiry": {"events": 6, "visitors": 5},
    }
    svc = _service_with_events(counts, chat_visitors=12)
    funnel = svc.get_funnel(days=30)
    ok = check("period stored", funnel["period_days"] == 30)
    ok &= check("since set", funnel["since"] is not None)
    ok &= check(
        "4 steps in path order",
        [s["key"] for s in funnel["steps"]] == ["visit", "case_view", "chat", "inquiry"],
    )
    by_key = {s["key"]: s for s in funnel["steps"]}
    ok &= check("visit events=100", by_key["visit"]["events"] == 100)
    ok &= check("visit visitors=40", by_key["visit"]["visitors"] == 40)
    ok &= check(
        "case_view 28/17",
        (by_key["case_view"]["events"], by_key["case_view"]["visitors"]) == (28, 17),
    )
    ok &= check(
        "chat from execution_sessions 12/12",
        (by_key["chat"]["events"], by_key["chat"]["visitors"]) == (12, 12),
    )
    ok &= check("inquiry 6/5", (by_key["inquiry"]["events"], by_key["inquiry"]["visitors"]) == (6, 5))
    rejected = False
    try:
        svc.get_funnel(days=13)
    except ValueError:
        rejected = True
    ok &= check("unsupported period raises", rejected)
    ok &= check("ALLOWED_PERIODS", ALLOWED_PERIODS == [7, 30, 90, 0])
    return ok


def test_presale_funnel_all_time_and_breakdowns():
    top_cases = [
        {"card_slug": "ai-portfolio", "card_title": "AI Portfolio", "views": 9, "visitors": 4},
        {"card_slug": "onboarding-bot", "card_title": "TOB", "views": 3, "visitors": 2},
    ]
    channels = [{"channel": "telegram", "events": 4, "visitors": 3}]
    svc = _service_with_events(
        {s["event_type"]: {"events": 5, "visitors": 3} for s in FUNNEL_STEPS},
        chat_visitors=3,
        top_cases=top_cases,
        channels=channels,
        with_prev=False,  # «всё время» — предыдущего периода нет
    )
    funnel = svc.get_funnel(days=0)
    ok = check("period 0 -> all time", funnel["period_days"] == 0)
    ok &= check("since None", funnel["since"] is None)
    ok &= check("top_cases passthrough", funnel["top_cases"] == [
        {"card_slug": "ai-portfolio", "card_title": "AI Portfolio", "views": 9, "visitors": 4},
        {"card_slug": "onboarding-bot", "card_title": "TOB", "views": 3, "visitors": 2},
    ], repr(funnel["top_cases"]))
    ok &= check("channels passthrough", funnel["inquiry_channels"] == [
        {"channel": "telegram", "events": 4, "visitors": 3}
    ])
    return ok


# ----------------------------------------------------------------------
# PresaleService: провал вглубь — кластеры шага и путь гостя
# ----------------------------------------------------------------------

def _service_with_touches(log_rows, chat_rows):
    """Service whose db.execute returns touch lists: log rows first,
    chat rows second (order used by _collect_touches). Results cycle,
    so several service calls against one mock are safe."""
    db = MagicMock()
    results = [
        SimpleNamespace(fetchall=lambda rows=log_rows: rows),
        SimpleNamespace(fetchall=lambda rows=chat_rows: rows),
    ]
    state = {"i": 0}

    def _execute(*args, **kwargs):
        res = results[state["i"] % len(results)]
        state["i"] += 1
        return res

    db.execute.side_effect = _execute
    return PresaleService(db)


def _ts(day, hour=12):
    return datetime(2026, 8, day, hour, 0, 0)


def test_presale_step_visitors_reached_and_lost():
    # v1: visit + case_view (дошёл до шага 2)
    # v2: только visit (потерян между шагами 1 → 2)
    # v3: только chat (пришёл без визита — немонотонность)
    # Форма строки лога: (event_type, ts, visitor, path, ip, slug, title,
    # channel, label) — ip добавлен задачей гео-обогащения 02.09.
    log_rows = [
        ("site_visit", _ts(20), "v1", "/", "88.99.10.1", None, None, None, None),
        ("case_view", _ts(20, 13), "v1", "/", "88.99.10.1", "ai-curator", "AI Curator", None, None),
        ("site_visit", _ts(25), "v2", "/contacts.html", "88.99.10.2", None, None, None, None),
        ("inquiry", _ts(26), "v3", "/", None, None, None, "telegram", "@guest"),
    ]
    chat_rows = [("s-1", _ts(21), "v3", "88.99.10.3")]
    svc = _service_with_touches(log_rows, chat_rows)

    reached = svc.get_step_visitors("case_view", days=30, lost=False)
    ok = check("reached total=1", reached["total"] == 1, repr(reached))
    row = reached["visitors"][0]
    ok &= check("v1 row fields", (
        row["visitor_id"] == "v1"
        and row["visits"] == 1
        and row["case_views"] == 1
        and row["cases"] == ["AI Curator"]
    ), repr(row))
    ok &= check("cases limited to 5 list", isinstance(row["cases"], list))

    lost = svc.get_step_visitors("case_view", days=30, lost=True)
    ok &= check(
        "lost = visit-but-no-case_view",
        [r["visitor_id"] for r in lost["visitors"]] == ["v2"],
        repr(lost),
    )

    first_lost = svc.get_step_visitors("visit", days=30, lost=True)
    ok &= check("first step has no lost cohort", first_lost["total"] == 0)

    chat = svc.get_step_visitors("chat", days=30)
    ok &= check(
        "chat visitors include v3 (execution_sessions)",
        any(r["visitor_id"] == "v3" and r["chats"] == 1 for r in chat["visitors"]),
        repr(chat),
    )

    bad = False
    try:
        svc.get_step_visitors("nonsense", days=30)
    except ValueError:
        bad = True
    ok &= check("unknown step rejected", bad)

    # Сортировки (задача 02.09, вариант 2): на шаге visit все трое.
    # Ценность: v1 = визит 1 + кейс 3 = 4; v2 = 1; v3 = обращение 100 + диалог 10 = 110.
    visit = svc.get_step_visitors("visit", days=30, sort="value")
    ok &= check("sort=value: v3 (обращение+диалог) выше v1 (кейс+визит)",
                [r["visitor_id"] for r in visit["visitors"]] == ["v3", "v1", "v2"],
                repr([r["visitor_id"] for r in visit["visitors"]]))
    ok &= check("value weights: v1=4, v2=1, v3=110",
                {r["visitor_id"]: r["value"] for r in visit["visitors"]}
                == {"v1": 4, "v2": 1, "v3": 110},
                repr({r["visitor_id"]: r["value"] for r in visit["visitors"]}))
    by_touches = svc.get_step_visitors("visit", days=30, sort="touches")
    ok &= check("sort=touches: v1 (2 касания) первый",
                [r["visitor_id"] for r in by_touches["visitors"]][0] == "v1")
    recent = svc.get_step_visitors("visit", days=30, sort="recent")
    ok &= check("sort=recent: самый свежий — v3 (26-е число)",
                [r["visitor_id"] for r in recent["visitors"]][0] == "v3",
                repr([r["visitor_id"] for r in recent["visitors"]]))
    bad_sort = False
    try:
        svc.get_step_visitors("visit", days=30, sort="nonsense")
    except ValueError:
        bad_sort = True
    ok &= check("unknown sort rejected", bad_sort)
    return ok


def test_presale_visitor_journey_chronology():
    log_rows = [
        ("case_view", _ts(21, 10), "v9", "/", "88.99.10.1", "ai-curator", "AI Curator", None, None),
        ("site_visit", _ts(20), "v9", "/", "88.99.10.1", None, None, None, None),
        ("inquiry", _ts(22), "v9", "/", None, None, None, "telegram", "@guest"),
        ("inquiry", _ts(23), "other-guest", "/", None, None, None, "email", "hi"),
    ]
    chat_rows = [("s-9", _ts(21, 14), "v9", "88.99.10.1")]
    svc = _service_with_touches(log_rows, chat_rows)

    journey = svc.get_visitor_journey("v9")
    ok = check("3 touches for v9", len(journey["touches"]) == 3, repr(journey))
    kinds = [t["kind"] for t in journey["touches"]]
    ok &= check(
        "chronological order visit → case_view → chat → inquiry",
        kinds == ["visit", "case_view", "chat", "inquiry"],
        repr(kinds),
    )
    ok &= check("chat carries session_id", journey["touches"][2]["session_id"] == "s-9")
    ok &= check("first/last seen", (
        journey["first_seen"] == _ts(20).isoformat()
        and journey["last_seen"] == _ts(22).isoformat()
    ))
    empty = svc.get_visitor_journey("nobody")
    ok &= check("unknown visitor -> empty journey", empty["touches"] == [])
    return ok


if __name__ == "__main__":
    results = [
        test_track_event_request_type_whitelist(),
        test_filter_presale_metadata(),
        test_presale_funnel_steps_and_period(),
        test_presale_funnel_all_time_and_breakdowns(),
        test_presale_step_visitors_reached_and_lost(),
        test_presale_visitor_journey_chronology(),
    ]
    print()
    print("PASS " if all(results) else "FAIL ", sum(1 for r in results if r), "/", len(results))
    raise SystemExit(0 if all(results) else 1)