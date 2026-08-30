"""
Managed system prompt storage for the AI settings console (task 2026-08-30).

SOT for prompt versions — PG table ``system_prompts`` (migration 021).
The builtin prompt (``prompt_assembly.SYSTEM_PROMPT``, ``v4-compact-multi``)
remains the fallback when the table has no active row and the reset source.

Contract:

- body — полный шаблон сборки с плейсхолдерами ``{registry_block}``,
  ``{registry_list}``, ``{rag_context}``, ``{conversation_history}``,
  ``{user_query}`` (валидация на сохранении);
- единственный активный промпт (partial unique index, миграция 021);
- дедупликация по паре (метка версии, ``body_hash`` sha256[:16]): повторное
  сохранение той же версии не плодит строк; то же тело под новой меткой —
  отдельная запись в истории (решение владельца 30.08.2026);
- смена активной версии меняет fingerprint промпта — ответ-кеш
  детерминированных ответов и generation не наследует старые ключи.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.entities import SystemPrompt
from app.services.prompt_assembly import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION

REQUIRED_PLACEHOLDERS = (
    "{registry_block}",
    "{registry_list}",
    "{rag_context}",
    "{conversation_history}",
    "{user_query}",
)


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def validate_body(body: str) -> list[str]:
    """Ошибки валидации тела промпта (пустой список — валидно)."""
    errors: list[str] = []
    if not body or not body.strip():
        errors.append("Тело промпта пусто")
        return errors
    for ph in REQUIRED_PLACEHOLDERS:
        if ph not in body:
            errors.append(f"Отсутствует обязательный плейсхолдер {ph}")
    if not errors:
        try:
            body.format(
                registry_block="probe",
                registry_list="probe",
                rag_context="probe",
                conversation_history="probe",
                user_query="probe",
            )
        except (KeyError, IndexError, ValueError) as exc:
            errors.append(f"Шаблон не собирается: {exc}")
    return errors


class SystemPromptService:
    """CRUD + активация версий системного промпта."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        """Активная версия + история (новые сверху)."""
        rows = self._db.scalars(
            select(SystemPrompt).order_by(SystemPrompt.created_at.desc(), SystemPrompt.id)
        ).all()
        active = next((r for r in rows if r.is_active), None)
        return {
            "active": self._to_dict(active) if active else None,
            "items": [self._to_dict(r) for r in rows],
            "builtin": {
                "version": SYSTEM_PROMPT_VERSION,
                "body": SYSTEM_PROMPT,
                "body_hash": body_hash(SYSTEM_PROMPT),
            },
        }

    def get_active_row(self) -> SystemPrompt | None:
        try:
            return self._db.scalar(select(SystemPrompt).where(SystemPrompt.is_active.is_(True)))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_version(self, version: str, body: str, note: str | None = None) -> dict[str, Any]:
        """Сохраняет версию и активирует её (дедуп по паре метка+тело)."""
        errors = validate_body(body)
        if errors:
            raise ValueError("; ".join(errors))
        version = (version or "").strip()
        if not version:
            raise ValueError("Не указана метка версии")
        if len(version) > 100:
            raise ValueError("Метка версии длиннее 100 символов")

        digest = body_hash(body)
        existing = self._db.scalar(select(SystemPrompt).where(
            SystemPrompt.version == version, SystemPrompt.body_hash == digest))
        if existing is not None:
            return self._activate_row(existing)
        row = SystemPrompt(version=version, body=body, body_hash=digest, note=note)
        self._db.add(row)
        self._db.flush()
        return self._activate_row(row)

    def activate(self, prompt_id) -> dict[str, Any]:
        row = self._db.get(SystemPrompt, prompt_id)
        if row is None:
            raise LookupError("system_prompt_not_found")
        return self._activate_row(row)

    def reset_to_builtin(self) -> dict[str, Any]:
        """Активирует вшитый промпт как управляемую версию (idempotent)."""
        digest = body_hash(SYSTEM_PROMPT)
        existing = self._db.scalar(select(SystemPrompt).where(
            SystemPrompt.version == SYSTEM_PROMPT_VERSION, SystemPrompt.body_hash == digest))
        if existing is not None:
            return self._activate_row(existing)
        row = SystemPrompt(
            version=SYSTEM_PROMPT_VERSION,
            body=SYSTEM_PROMPT,
            body_hash=digest,
            note="Вшитый системный промпт (источник сброса)",
            is_builtin=True,
        )
        self._db.add(row)
        self._db.flush()
        return self._activate_row(row)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _activate_row(self, row: SystemPrompt) -> dict[str, Any]:
        self._db.execute(
            update(SystemPrompt)
            .where(SystemPrompt.is_active.is_(True), SystemPrompt.id != row.id)
            .values(is_active=False)
        )
        row.is_active = True
        self._db.commit()
        self._db.refresh(row)
        return self._to_dict(row)

    @staticmethod
    def _to_dict(row: SystemPrompt) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "version": row.version,
            "body": row.body,
            "body_hash": row.body_hash,
            "note": row.note,
            "is_active": row.is_active,
            "is_builtin": row.is_builtin,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


def load_active_prompt(db: Session) -> tuple[str | None, str | None]:
    """
    Активный управляемый промпт для ChatOrchestrator.

    Возвращает ``(body, version)`` или ``(None, None)`` — нет активной
    строки либо таблица недоступна (fail-open к вшитому дефолту: поведение
    канала не меняется при отсутствии записи).
    """
    try:
        row = db.scalar(select(SystemPrompt).where(SystemPrompt.is_active.is_(True)))
    except Exception:
        return None, None
    if row is None:
        return None, None
    return row.body, row.version