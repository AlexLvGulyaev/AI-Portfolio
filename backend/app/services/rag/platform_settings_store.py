"""
PG storage for the platform-settings key-value store (migration 020).

Thin replacement for Assistant Flow's PlatformSettingsRepository: we have a
single SQLAlchemy session factory; values are JSON documents.
"""

from __future__ import annotations

from typing import Any

from app.core.database import SessionLocal
from app.models.entities import PlatformSetting


def get_setting(key: str) -> Any | None:
    session = SessionLocal()
    try:
        row = session.get(PlatformSetting, key)
        return row.value if row is not None else None
    finally:
        session.close()


def set_setting(key: str, value: Any) -> None:
    session = SessionLocal()
    try:
        row = session.get(PlatformSetting, key)
        if row is None:
            row = PlatformSetting(key=key, value=value)
            session.add(row)
        else:
            row.value = value
        session.commit()
    finally:
        session.close()


def delete_setting(key: str) -> None:
    session = SessionLocal()
    try:
        row = session.get(PlatformSetting, key)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()