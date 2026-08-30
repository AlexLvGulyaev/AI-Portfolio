"""
Retrieval cache: кеш результатов векторного поиска (WH-1, AF-parity).

Рекреация паттерна Assistant Flow (services/cache/retrieval_cache.py —
caching_retrieval_backend поверх активного бэкенда), адаптированная к AIP:

- Хранилище — sqlite ``data/cache/retrieval_cache.sqlite3`` (не файл-JSON,
  как ResponseCache: записи маленькие, но их много и они живут TTL).
- Ключ — детерминированный fingerprint (см. caching_retrieval_backend):
  запрос + параметры вызова + runtime-тюнинг + embedding-модель + бэкенд +
  generation. Смена generation инвалидирует всё.
- Инвалидация по индексации: PG-счётчик ``retrieval_generation``
  (platform_settings) инкрементируется после успешного KB-синка — это закрывает
  известную дыру AF («generation из env не поднимается при reindex», их §35).
- Дефолт — ВЫКЛ (env ``ENABLE_RETRIEVAL_CACHE=false``); включается тумблером
  консоли Retrieval (PG ``enable_retrieval_cache``).
- TTL/вкл-выкл берутся из platform_settings с коротким кешем (2.5 с, паттерн
  retrieval_manager) поверх env-дефолтов.

Статус задачи: task_history/2026-08-29_task-aip-retrieval-cache-wh1.md.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict
from typing import Any, Optional

from app.core.config import get_settings
from app.services.rag import platform_settings_store as store

KEY_ENABLE_RETRIEVAL_CACHE = "enable_retrieval_cache"
KEY_RETRIEVAL_GENERATION = "retrieval_generation"

_DB_PATH = "data/cache/retrieval_cache.sqlite3"
_EFFECTIVE_CACHE_S = 2.5

_init_lock = threading.Lock()
_initialized = False

# Кеш эффективных значений (enable / ttl / generation) — 2.5 c,
# паттерн RetrievalManager._eff_*.
_eff_lock = threading.Lock()
_eff: Optional[dict[str, Any]] = None
_eff_at: float = 0.0

# Diagnostics: counters за жизнь процесса (AF CacheStats idiom).
_stats_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0, "writes": 0, "evictions": 0}


def _ensure_db() -> sqlite3.Connection:
    """Open (creating on demand) the sqlite store with WAL + schema init."""
    global _initialized
    with _init_lock:
        if not _initialized:
            os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
            conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS retrieval_cache ("
                " key TEXT PRIMARY KEY,"
                " payload TEXT NOT NULL,"
                " created_at REAL NOT NULL)"
            )
            conn.commit()
            _initialized = True
    return sqlite3.connect(_DB_PATH, check_same_thread=False)


# ---------- effective values (env bootstrap + PG override, 2.5 s cache) ----------


def _env_defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "enable_retrieval_cache": bool(s.enable_retrieval_cache),
        "ttl_seconds": int(s.retrieval_cache_ttl_seconds),
        "generation": int(s.rag_retrieval_generation),
    }


def effective_state(refresh: bool = False) -> dict[str, Any]:
    """Effective cache settings: env defaults + PG overrides (cached 2.5 s)."""
    global _eff, _eff_at
    now = time.monotonic()
    if not refresh and _eff is not None and (now - _eff_at) < _EFFECTIVE_CACHE_S:
        return _eff
    base = _env_defaults()
    try:
        enabled_pg = store.get_setting(KEY_ENABLE_RETRIEVAL_CACHE)
        if isinstance(enabled_pg, bool):
            base["enable_retrieval_cache"] = enabled_pg
        gen_pg = store.get_setting(KEY_RETRIEVAL_GENERATION)
        if isinstance(gen_pg, int) and not isinstance(gen_pg, bool):
            base["generation"] = gen_pg
    except Exception:
        pass  # store недоступен — работаем на env-дефолтах
    with _eff_lock:
        _eff = base
        _eff_at = now
    return base


def is_enabled() -> bool:
    return bool(effective_state()["enable_retrieval_cache"])


def generation() -> int:
    return int(effective_state()["generation"])


def bump_generation(reason: str = "kb_sync") -> int:
    """Increment the PG generation counter (invalidates all cached entries)."""
    new_gen = generation() + 1
    store.set_setting(KEY_RETRIEVAL_GENERATION, new_gen)
    effective_state(refresh=True)
    return new_gen


def set_enabled(value: bool) -> None:
    """Persist the enabled toggle to PG (console switch)."""
    store.set_setting(KEY_ENABLE_RETRIEVAL_CACHE, bool(value))
    effective_state(refresh=True)


# ---------- cache payload serialization ----------


def serialize_results(results: list) -> str:
    """SearchResult-like objects -> JSON string (dataclass asdict)."""
    rows = []
    for r in results:
        rows.append(
            {
                "content": r.content,
                "source": r.source,
                "score": r.score,
                "metadata": r.metadata,
                "chunk_id": r.chunk_id,
            }
        )
    return json.dumps(rows, ensure_ascii=False, default=str)


def deserialize_results(payload: str) -> list:
    """Rebuild SearchResult objects from the cached JSON payload."""
    from app.services.rag.rag_service import SearchResult

    rows = json.loads(payload)
    return [
        SearchResult(
            content=r["content"],
            source=r["source"],
            score=r["score"],
            metadata=r["metadata"],
            chunk_id=r["chunk_id"],
        )
        for r in rows
    ]


# ---------- store operations ----------


def get_cached(key: str) -> Optional[list]:
    """Cached results by fingerprint key; TTL + generation aware, updates stats."""
    ttl = int(effective_state()["ttl_seconds"])
    try:
        conn = _ensure_db()
        try:
            row = conn.execute(
                "SELECT payload, created_at FROM retrieval_cache WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            _bump("misses")
            return None
        if ttl > 0 and (time.time() - float(row[1])) > ttl:
            _bump("evictions")
            delete_key(key)
            _bump("misses")
            return None
        _bump("hits")
        return deserialize_results(row[0])
    except Exception:
        # Кеш не должен ломать retrieval: любая ошибка хранилища — miss.
        _bump("misses")
        return None


def put_cached(key: str, results: list) -> None:
    try:
        payload = serialize_results(results)
        conn = _ensure_db()
        try:
            conn.execute(
                "INSERT INTO retrieval_cache (key, payload, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload,"
                " created_at = excluded.created_at",
                (key, payload, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
        _bump("writes")
    except Exception:
        pass  # запись в кеш — best effort


def delete_key(key: str) -> None:
    try:
        conn = _ensure_db()
        try:
            conn.execute("DELETE FROM retrieval_cache WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def clear() -> int:
    """Drop all cached entries; returns the number of removed rows (best effort)."""
    removed = 0
    try:
        conn = _ensure_db()
        try:
            removed = int(conn.execute("SELECT COUNT(*) FROM retrieval_cache").fetchone()[0])
            conn.execute("DELETE FROM retrieval_cache")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
    return removed


def entry_count() -> int:
    try:
        conn = _ensure_db()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM retrieval_cache").fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return 0


def db_path() -> str:
    return _DB_PATH


def _bump(k: str) -> None:
    with _stats_lock:
        _stats[k] += 1


def stats() -> dict[str, Any]:
    """Process-lifetime diagnostics (AF CacheStats idiom)."""
    with _stats_lock:
        hits, misses = _stats["hits"], _stats["misses"]
        total = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "writes": _stats["writes"],
            "evictions": _stats["evictions"],
            "total": total,
            "hit_rate": round(hits / total, 4) if total else 0.0,
        }


def asdict_search_result(r) -> dict[str, Any]:  # pragma: no cover - helper
    return asdict(r)