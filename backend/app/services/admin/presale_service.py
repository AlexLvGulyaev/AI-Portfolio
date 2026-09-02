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
        }

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

    def get_step_visitors(
        self,
        step_key: str,
        days: int = 30,
        lost: bool = False,
        card_slug: str | None = None,
        channel: str | None = None,
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
                    "step": step_key, "days": days, "lost": True,
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

        # Богатейшие касаниями гости сверху (директивное ревью 02.09),
        # при равенстве — самые свежие.
        rows = sorted(
            (self._visitor_summary(v, per_visitor[v]) for v in cluster),
            key=lambda r: (r["touches"], r["last_seen"]),
            reverse=True,
        )
        return {
            "step": step_key,
            "days": days,
            "lost": lost,
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
        return {
            "visitor_id": visitor_id,
            "days": days,
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
                "slug": row[4],
                "title": row[5],
                "channel": row[6],
                "label": row[7],
                "session_id": None,
            }
            for row in self._db.execute(stmt).fetchall()
        ]

        chat_stmt = (
            select(
                ExecutionSession.id,
                ExecutionSession.created_at,
                ExecutionSession.visitor_id,
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
        for t in touches:
            by_kind[t["kind"]] += 1
            if t["kind"] == "case_view":
                name = t.get("title") or t.get("slug")
                if name and name not in cases:
                    cases.append(name)
            if t["kind"] == "inquiry" and t.get("channel"):
                if t["channel"] not in channels:
                    channels.append(t["channel"])
        ordered_ts = sorted(t["ts"] for t in touches)
        return {
            "visitor_id": visitor_id,
            "visits": by_kind["visit"],
            "case_views": by_kind["case_view"],
            "chats": by_kind["chat"],
            "inquiries": by_kind["inquiry"],
            "cases": cases[:5],
            "channels": channels,
            "touches": len(touches),
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