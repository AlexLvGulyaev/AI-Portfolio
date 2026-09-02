"""
Presale funnel analytics service (§4.5).

Aggregates the presale path across two event stores:

- ``operational_logs`` — events ``site_visit``, ``case_view``, ``inquiry``
  (visitor_id inside ``log_metadata``, решение о хранилище — ARCHITECTURE.md §8.4);
- ``execution_sessions`` — chat touchpoints (``event_type='chat_request'``,
  visitor_id in a typed column, ADR v1.4 ADMIN_CONSOLE_ARCHITECTURE).

Read-only service: no event mutation, funnel assembly only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import ExecutionSession, OperationalLog
from app.services.geo_service import resolve_geo

# Шаги воронки в фиксированном порядке пути (§4.5, 5.2).
FUNNEL_STEPS: list[dict[str, str]] = [
    {"key": "visit", "label": "Посещение сайта", "event_type": "site_visit", "store": "operational_logs"},
    {"key": "case_view", "label": "Просмотр кейса", "event_type": "case_view", "store": "operational_logs"},
    {"key": "chat", "label": "AI-ассистент", "event_type": "chat_request", "store": "execution_sessions"},
    {"key": "inquiry", "label": "Обращение", "event_type": "inquiry", "store": "operational_logs"},
]

# Периоды консоли (дней; 0 = весь период, «всё время»).
ALLOWED_PERIODS: list[int] = [7, 30, 90, 0]


def _visitor_expr_for_logs():
    """visitor_id expression for JSON log_metadata column (PostgreSQL json).

    Колонка OperationalLog.log_metadata имеет тип JSON (не JSONB), поэтому
    ``.astext`` недоступен — используется ``json_extract_path_text(json, key)``.
    """
    return func.json_extract_path_text(OperationalLog.log_metadata, "visitor_id")


# Кеш гео-резолва IP → {country_code, country, city} | None. Кардинальность
# IP в витринных логах мала, повторные запросы консоли идут без чтения mmdb.
_geo_cache: dict[str, dict[str, Any] | None] = {}


def _geo_for_ip(ip: str | None) -> dict[str, Any] | None:
    if ip is None:
        return None
    if ip not in _geo_cache:
        _geo_cache[ip] = resolve_geo(ip)
    return _geo_cache[ip]


def _dominant_ip(ips: list[str | None]) -> str | None:
    """Частейший публичный IP списка (None игнорируются); None — пусто."""
    counts: dict[str, int] = {}
    for ip in ips:
        if ip:
            counts[ip] = counts.get(ip, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


class PresaleService:
    """Aggregate presale funnel metrics for the admin console."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_funnel(self, days: int = 30) -> dict[str, Any]:
        """Return funnel for the period: `days` days, or all time when 0."""
        if days not in ALLOWED_PERIODS:
            raise ValueError(f"Unsupported period: {days}")

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days) if days else None
        steps = [self._build_step(step, since) for step in FUNNEL_STEPS]

        # Дельты KPI: тот же шаг за предыдущий период той же длины
        # (для «всё время» предыдущего периода нет).
        steps_prev: list[dict[str, Any]] | None = None
        if since is not None:
            since_prev = since - timedelta(days=days)
            steps_prev = [
                self._build_step(step, since_prev, until=since)
                for step in FUNNEL_STEPS
            ]

        return {
            "period_days": days,
            "since": since.isoformat() if since else None,
            "until": now.isoformat(),
            "steps": steps,
            "steps_prev": steps_prev,
            "top_cases": self._top_case_views(since),
            "inquiry_channels": self._inquiry_channels(since),
            "geo_countries": self._geo_countries(since),
            "geo_inquiries": self._geo_inquiries(since),
        }

    # ------------------------------------------------------------------
    # Geo aggregates (география посетителей, задача 02.09)
    # ------------------------------------------------------------------

    def _geo_countries(self, since: datetime | None) -> list[dict[str, Any]]:
        """Страны гостей: уникальные посетители + все визиты, по убыванию.

        Гость относится к стране его частейшего IP среди визитов; страна
        None (нерезолвенный IP) группируется как «не определена».
        """
        visitor = _visitor_expr_for_logs()
        ip_expr = func.json_extract_path_text(OperationalLog.log_metadata, "ip")
        rows = self._db.execute(
            select(visitor, ip_expr, func.count())
            .where(OperationalLog.event_type == "site_visit")
            .where(visitor.isnot(None))
            .where(*([OperationalLog.created_at >= since] if since else []))
            .group_by(visitor, ip_expr)
        ).fetchall()

        # Один гость может прийти с нескольких IP: доминирующий IP —
        # с наибольшим числом визитов.
        best_ip: dict[str, tuple[int, str | None]] = {}
        total_visits = 0
        for visitor_id, ip, visits in rows:
            total_visits += visits
            if ip:
                cur = best_ip.get(visitor_id)
                if cur is None or visits > cur[0]:
                    best_ip[visitor_id] = (visits, ip)
            elif visitor_id not in best_ip:
                best_ip[visitor_id] = (0, None)

        countries: dict[str, dict[str, Any]] = {}
        # «Не определена» — бакет с ключом None (IP не резолвится в страну).
        unresolved: dict[str | None, dict[str, Any]] = {
            None: {"code": None, "country": "Не определена", "visitors": 0, "visits": 0}
        }
        for visitor_id, (_visits, ip) in best_ip.items():
            geo = _geo_for_ip(ip)
            bucket = countries if geo else unresolved
            key = geo["country_code"] if geo else None
            if key not in bucket:
                bucket[key] = {
                    "code": geo["country_code"] if geo else None,
                    "country": geo["country"] if geo else "Не определена",
                    "visitors": 0,
                    "visits": 0,
                }
            bucket[key]["visitors"] += 1
            bucket[key]["visits"] += _visits

        ordered = sorted(countries.values(), key=lambda r: r["visitors"], reverse=True)
        result = [
            {**r, "share": round(100 * r["visitors"] / len(best_ip), 1) if best_ip else 0.0}
            for r in ordered
        ]
        if unresolved[None]["visitors"]:
            result.append({
                **unresolved[None],
                "share": round(100 * unresolved[None]["visitors"] / len(best_ip), 1) if best_ip else 0.0,
            })
        result.append({"total_visitors": len(best_ip), "total_visits": total_visits})
        return result

    def _geo_inquiries(self, since: datetime | None) -> list[dict[str, Any]]:
        """Страны обращающихся: та же логика по inquiry-касаниям."""
        visitor = _visitor_expr_for_logs()
        ip_expr = func.json_extract_path_text(OperationalLog.log_metadata, "ip")
        rows = self._db.execute(
            select(visitor, ip_expr, func.count())
            .where(OperationalLog.event_type == "inquiry")
            .where(visitor.isnot(None))
            .where(*([OperationalLog.created_at >= since] if since else []))
            .group_by(visitor, ip_expr)
        ).fetchall()
        per_visitor: dict[str, list[str | None]] = {}
        for visitor_id, ip, _count in rows:
            per_visitor.setdefault(visitor_id, []).append(ip)
        countries: dict[str, dict[str, Any]] = {}
        for visitor_id, ips in per_visitor.items():
            geo = _geo_for_ip(_dominant_ip(ips))
            code = geo["country_code"] if geo else None
            name = geo["country"] if geo else "Не определена"
            bucket = countries.setdefault(
                code, {"code": code, "country": name, "visitors": 0}
            )
            bucket["visitors"] += 1
        return sorted(countries.values(), key=lambda r: r["visitors"], reverse=True)

    # ------------------------------------------------------------------
    # Level 2 — visitor clusters per funnel step
    # ------------------------------------------------------------------

    # Суффикс метки шага → kind касания (см. _collect_touches).
    _STEP_KINDS: dict[str, str] = {
        "visit": "visit",
        "case_view": "case_view",
        "chat": "chat",
        "inquiry": "inquiry",
    }

    # Режимы сортировки списка гостей (задача 02.09, вариант владельца 2).
    VISITOR_SORTS = ("value", "touches", "recent")

    def get_step_visitors(
        self,
        step_key: str,
        days: int = 30,
        lost: bool = False,
        card_slug: str | None = None,
        channel: str | None = None,
        sort: str = "value",
        limit: int = 100,
    ) -> dict[str, Any]:
        """Visitors of one funnel step ('дошли') or lost between the
        previous and this step ('потеряны' — предшествующий шаг есть,
        этого касания нет).

        ``card_slug`` / ``channel`` — провал из брейкдаунов: оставляют
        только гостей, имевших соответствующее касание (case_view /
        inquiry).
        """
        if step_key not in self._STEP_KINDS:
            raise ValueError(f"Unknown funnel step: {step_key}")
        if days not in ALLOWED_PERIODS:
            raise ValueError(f"Unsupported period: {days}")
        if sort not in self.VISITOR_SORTS:
            raise ValueError(f"Unsupported sort: {sort}")

        since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        touches = self._collect_touches(since=since)

        # Фильтры брейкдаунов: гость должен иметь касание с этим slug/channel.
        if card_slug:
            slugs = {
                t["visitor"] for t in self._collect_touches(since=since)
                if t["kind"] == "case_view" and t.get("slug") == card_slug
            }
            touches = [t for t in touches if t["visitor"] in slugs]
        if channel:
            channels = {
                t["visitor"] for t in self._collect_touches(since=since)
                if t["kind"] == "inquiry" and t.get("channel") == channel
            }
            touches = [t for t in touches if t["visitor"] in channels]

        per_visitor = self._group_touches(touches)

        kind = self._STEP_KINDS[step_key]
        step_idx = [s["key"] for s in FUNNEL_STEPS].index(step_key)
        reached = {
            v for v, t in per_visitor.items() if any(x["kind"] == kind for x in t)
        }
        if lost:
            if step_idx == 0:
                return {
                    "step": step_key, "days": days, "lost": True, "sort": sort,
                    "total": 0, "visitors": [],
                }
            prev_kind = self._STEP_KINDS[FUNNEL_STEPS[step_idx - 1]["key"]]
            prev_reached = {
                v for v, t in per_visitor.items()
                if any(x["kind"] == prev_kind for x in t)
            }
            cluster = prev_reached - reached
        else:
            cluster = reached

        # Сортировка списка: ценность (дефолт) / касания / свежие; при
        # равенстве — самые свежие (касания и ценность).
        if sort == "touches":
            keyfn = lambda r: (r["touches"], r["last_seen"])  # noqa: E731
        elif sort == "recent":
            keyfn = lambda r: (r["last_seen"],)  # noqa: E731
        else:  # value — по умолчанию
            keyfn = lambda r: (r["value"], r["last_seen"])  # noqa: E731
        rows = sorted(
            (self._visitor_summary(v, per_visitor[v]) for v in cluster),
            key=keyfn,
            reverse=True,
        )
        return {
            "step": step_key,
            "days": days,
            "lost": lost,
            "sort": sort,
            "total": len(rows),
            "visitors": rows[:limit],
        }

    # ------------------------------------------------------------------
    # Level 3 — single visitor journey
    # ------------------------------------------------------------------

    def get_visitor_journey(self, visitor_id: str, days: int = 0) -> dict[str, Any]:
        """Chronological touch list for one visitor across both stores."""
        if days not in ALLOWED_PERIODS:
            raise ValueError(f"Unsupported period: {days}")
        since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        touches = [
            t for t in self._collect_touches(since=since, visitor_id=visitor_id)
        ]
        touches.sort(key=lambda t: t["ts"])
        geo = _geo_for_ip(_dominant_ip([t.get("ip") for t in touches]))
        return {
            "visitor_id": visitor_id,
            "days": days,
            "geo": geo,
            "ip": _dominant_ip([t.get("ip") for t in touches]),
            "touches": touches,
            "first_seen": touches[0]["ts"].isoformat() if touches else None,
            "last_seen": touches[-1]["ts"].isoformat() if touches else None,
        }

    # ------------------------------------------------------------------
    # Touch collection (both stores)
    # ------------------------------------------------------------------

    _EVENT_KINDS: dict[str, str] = {
        "site_visit": "visit",
        "case_view": "case_view",
        "inquiry": "inquiry",
    }

    def _collect_touches(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        visitor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """All presale touches for the period as plain dicts.

        kind: visit / case_view / chat / inquiry (business naming for the
        console; technical event_type stays in the backend).
        """
        visitor = _visitor_expr_for_logs()
        ip_expr = func.json_extract_path_text(OperationalLog.log_metadata, "ip")
        slug_expr = func.json_extract_path_text(OperationalLog.log_metadata, "card_slug")
        title_expr = func.json_extract_path_text(OperationalLog.log_metadata, "card_title")
        channel_expr = func.json_extract_path_text(OperationalLog.log_metadata, "channel")
        label_expr = func.json_extract_path_text(OperationalLog.log_metadata, "label")

        stmt = (
            select(
                OperationalLog.event_type,
                OperationalLog.created_at,
                visitor,
                OperationalLog.query,
                ip_expr,
                slug_expr,
                title_expr,
                channel_expr,
                label_expr,
            )
            .select_from(OperationalLog)
            .where(OperationalLog.event_type.in_(self._EVENT_KINDS.keys()))
            .where(visitor.isnot(None))
        )
        if since is not None:
            stmt = stmt.where(OperationalLog.created_at >= since)
        if until is not None:
            stmt = stmt.where(OperationalLog.created_at < until)
        if visitor_id is not None:
            stmt = stmt.where(visitor == visitor_id)
        touches: list[dict[str, Any]] = [
            {
                "kind": self._EVENT_KINDS[row[0]],
                "ts": row[1],
                "visitor": row[2],
                "path": row[3],
                "ip": row[4],
                "slug": row[5],
                "title": row[6],
                "channel": row[7],
                "label": row[8],
                "session_id": None,
            }
            for row in self._db.execute(stmt).fetchall()
        ]

        chat_stmt = (
            select(
                ExecutionSession.id,
                ExecutionSession.created_at,
                ExecutionSession.visitor_id,
                ExecutionSession.client_ip,
            )
            .where(ExecutionSession.event_type == "chat_request")
            .where(ExecutionSession.visitor_id.isnot(None))
        )
        if since is not None:
            chat_stmt = chat_stmt.where(ExecutionSession.created_at >= since)
        if until is not None:
            chat_stmt = chat_stmt.where(ExecutionSession.created_at < until)
        if visitor_id is not None:
            chat_stmt = chat_stmt.where(ExecutionSession.visitor_id == visitor_id)
        touches.extend(
            {
                "kind": "chat",
                "ts": row[1],
                "visitor": row[2],
                "path": None,
                "ip": row[3],
                "slug": None,
                "title": None,
                "channel": None,
                "label": None,
                "session_id": str(row[0]),
            }
            for row in self._db.execute(chat_stmt).fetchall()
        )
        return touches

    @staticmethod
    def _group_touches(
        touches: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for t in touches:
            grouped.setdefault(t["visitor"], []).append(t)
        return grouped

    @staticmethod
    def _visitor_summary(
        visitor_id: str, touches: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Per-visitor row for the level-2 cluster list."""
        by_kind = {k: 0 for k in ("visit", "case_view", "chat", "inquiry")}
        cases: list[str] = []
        channels: list[str] = []
        ips: list[str | None] = []
        for t in touches:
            by_kind[t["kind"]] += 1
            ips.append(t.get("ip"))
            if t["kind"] == "case_view":
                name = t.get("title") or t.get("slug")
                if name and name not in cases:
                    cases.append(name)
            if t["kind"] == "inquiry" and t.get("channel"):
                if t["channel"] not in channels:
                    channels.append(t["channel"])
        ordered_ts = sorted(t["ts"] for t in touches)
        geo = _geo_for_ip(_dominant_ip(ips))
        # Ценность гостя: обращение ×100, диалог ×10, кейс ×3, визит ×1
        # (задача 02.09 — «одно обращение может стоить сотни визитов»).
        value = (
            100 * by_kind["inquiry"]
            + 10 * by_kind["chat"]
            + 3 * by_kind["case_view"]
            + by_kind["visit"]
        )
        return {
            "visitor_id": visitor_id,
            "ip": _dominant_ip(ips),
            "geo": geo,
            "visits": by_kind["visit"],
            "case_views": by_kind["case_view"],
            "chats": by_kind["chat"],
            "inquiries": by_kind["inquiry"],
            "cases": cases[:5],
            "channels": channels,
            "touches": len(touches),
            "value": value,
            "first_seen": ordered_ts[0].isoformat(),
            "last_seen": ordered_ts[-1].isoformat(),
        }

    # ------------------------------------------------------------------
    # Operational-log based steps (site_visit / case_view / inquiry)
    # ------------------------------------------------------------------

    def _log_events_count(
        self, event_type: str, since: datetime | None, until: datetime | None = None
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(OperationalLog)
            .where(OperationalLog.event_type == event_type)
        )
        if since is not None:
            stmt = stmt.where(OperationalLog.created_at >= since)
        if until is not None:
            stmt = stmt.where(OperationalLog.created_at < until)
        return int(self._db.execute(stmt).scalar() or 0)

    def _log_visitors_count(
        self, event_type: str, since: datetime | None, until: datetime | None = None
    ) -> int:
        visitor = _visitor_expr_for_logs()
        stmt = (
            select(func.count(func.distinct(visitor)))
            .select_from(OperationalLog)
            .where(OperationalLog.event_type == event_type)
            .where(visitor.isnot(None))
        )
        if since is not None:
            stmt = stmt.where(OperationalLog.created_at >= since)
        if until is not None:
            stmt = stmt.where(OperationalLog.created_at < until)
        return int(self._db.execute(stmt).scalar() or 0)

    def _chat_visitors_count(
        self, since: datetime | None, until: datetime | None = None
    ) -> int:
        stmt = (
            select(func.count(func.distinct(ExecutionSession.visitor_id)))
            .select_from(ExecutionSession)
            .where(ExecutionSession.event_type == "chat_request")
            .where(ExecutionSession.visitor_id.isnot(None))
        )
        if since is not None:
            stmt = stmt.where(ExecutionSession.created_at >= since)
        if until is not None:
            stmt = stmt.where(ExecutionSession.created_at < until)
        return int(self._db.execute(stmt).scalar() or 0)

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _build_step(
        self,
        step: dict[str, str],
        since: datetime | None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        events: int
        if step["store"] == "execution_sessions":
            visitors = self._chat_visitors_count(since, until=until)
            events = visitors
        else:
            events = self._log_events_count(step["event_type"], since, until=until)
            visitors = self._log_visitors_count(step["event_type"], since, until=until)
        return {
            "key": step["key"],
            "label": step["label"],
            "events": events,
            "visitors": visitors,
        }

    def _top_case_views(self, since: datetime | None, limit: int = 5) -> list[dict[str, Any]]:
        """Group case_view events by card slug/title."""
        slug_expr = func.json_extract_path_text(OperationalLog.log_metadata, "card_slug")
        title_expr = func.json_extract_path_text(OperationalLog.log_metadata, "card_title")
        stmt = (
            select(
                slug_expr,
                title_expr,
                func.count().label("views"),
                func.count(func.distinct(_visitor_expr_for_logs())).label("visitors"),
            )
            .select_from(OperationalLog)
            .where(OperationalLog.event_type == "case_view")
            .group_by(slug_expr, title_expr)
            .order_by(func.count().desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.having(func.max(OperationalLog.created_at) >= since)
        return [
            {
                "card_slug": row[0] or "—",
                "card_title": row[1] or row[0] or "—",
                "views": int(row[2]),
                "visitors": int(row[3]),
            }
            for row in self._db.execute(stmt).fetchall()
        ]

    def _inquiry_channels(self, since: datetime | None, limit: int = 5) -> list[dict[str, Any]]:
        """Group inquiry events by response channel (telegram/email/other)."""
        channel_expr = func.json_extract_path_text(OperationalLog.log_metadata, "channel")
        stmt = (
            select(
                channel_expr,
                func.count().label("events"),
                func.count(func.distinct(_visitor_expr_for_logs())).label("visitors"),
            )
            .select_from(OperationalLog)
            .where(OperationalLog.event_type == "inquiry")
            .group_by(channel_expr)
            .order_by(func.count().desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.having(func.max(OperationalLog.created_at) >= since)
        return [
            {
                "channel": row[0] or "other",
                "events": int(row[1]),
                "visitors": int(row[2]),
            }
            for row in self._db.execute(stmt).fetchall()
        ]