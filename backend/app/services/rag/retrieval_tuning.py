"""
Retrieval tuning: PostgreSQL overrides on top of env bootstrap defaults.

Pattern recreated from Assistant Flow P6.12 (services/retrieval/retrieval_tuning.py):
``platform_settings.retrieval_tuning`` JSON stores partial overrides; keys
omitted from the stored dict mean "use env default". Fields are grouped by
application moment:

- RUNTIME — applied to queries without backend rebuild (top_k, distance filter,
  recall margin, generation cap, per-step/embeddings timeouts — AF parity,
  owner decision 29.08.2026, WH-2);
- BACKEND_BUILD — consumed when a chroma collection is created (clear/recreate);
  existing data is untouched, no reindex needed;
- INDEXING — chunking; a change requires full KB resync.

Adapted 29.08.2026 for the AI Portfolio retrieval console (task file
task_history/2026-08-29_task-aip-retrieval-console-from-af.md). The APL
additions over AF: chroma_ef_search / chroma_ef_construction and
retrieval_recall_margin (HNSW recall findings of 29.08.2026).
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

KEY_RETRIEVAL_TUNING = "retrieval_tuning"
KEY_ACTIVE_RAG_BACKEND = "active_rag_backend"

RUNTIME_KEYS: frozenset[str] = frozenset(
    {
        "rag_top_k",
        "rag_max_distance",
        "retrieval_recall_margin",
        # AF parity (WH-2): generation cap + timeouts.
        "rag_answer_max_tokens",
        "rag_retrieval_timeout",
        "rag_embedding_request_timeout",
    }
)
BACKEND_BUILD_KEYS: frozenset[str] = frozenset(
    {"chroma_ef_search", "chroma_ef_construction"}
)
INDEXING_KEYS: frozenset[str] = frozenset({"rag_chunk_size", "rag_chunk_overlap"})
ALL_KEYS: frozenset[str] = RUNTIME_KEYS | BACKEND_BUILD_KEYS | INDEXING_KEYS
REQUIRES_RESYNC_KEYS: frozenset[str] = frozenset(INDEXING_KEYS)

KNOWN_BACKENDS: frozenset[str] = frozenset({"chroma", "weaviate"})

_FIELD_SPECS: dict[str, tuple[type, tuple[float, float]] | tuple[type, None]] = {
    "rag_top_k": (int, (1, 20)),
    "rag_max_distance": (float, (0.1, 10.0)),
    "retrieval_recall_margin": (int, (1, 10)),
    # AF-verified ranges (Assistant Flow retrieval_tuning.py / settings UI 100..8000, 5..300):
    "rag_answer_max_tokens": (int, (100, 8000)),
    "rag_retrieval_timeout": (int, (5, 300)),
    "rag_embedding_request_timeout": (float, (5.0, 300.0)),
    "chroma_ef_search": (int, (10, 500)),
    "chroma_ef_construction": (int, (10, 500)),
    "rag_chunk_size": (int, (200, 5000)),
    "rag_chunk_overlap": (int, (0, 1000)),
}


def env_defaults() -> dict[str, Any]:
    """Env bootstrap values from Settings."""
    s = get_settings()
    return {k: getattr(s, k) for k in sorted(ALL_KEYS)}


def load_overrides(session) -> dict[str, Any]:
    """Read stored PG overrides, filtered to known keys with non-null values."""
    from app.models.entities import PlatformSetting

    row = session.get(PlatformSetting, KEY_RETRIEVAL_TUNING)
    if row is None or not isinstance(row.value, dict):
        return {}
    return sanitize_overrides(row.value)


def sanitize_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in raw.items() if k in ALL_KEYS and v is not None}


def validate_one(key: str, raw: Any) -> Any:
    """Validate a single tuning field against its spec (raises ValueError)."""
    if key == "rag_max_distance":
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key}: expected number, got {raw!r}") from None
        if isinstance(raw, int) and not isinstance(raw, bool):
            v = float(raw)
    elif key in _FIELD_SPECS:
        typ, _ = _FIELD_SPECS[key]
        try:
            v = typ(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key}: expected {typ.__name__}, got {raw!r}") from None
        if isinstance(raw, bool):
            raise ValueError(f"{key}: boolean is not a valid value")
    else:
        raise ValueError(f"unsupported tuning key {key!r}")
    spec = _FIELD_SPECS.get(key)
    if spec is not None:
        _, (lo, hi) = spec
        if not (lo <= v <= hi):
            raise ValueError(f"{key}: expected {lo}..{hi}, got {v}")
    return v


def validate_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Validate all patch keys; revert to int for int-fields given whole floats."""
    unknown = set(patch) - ALL_KEYS
    if unknown:
        raise ValueError(f"unknown tuning keys: {', '.join(sorted(unknown))}")
    if not patch:
        raise ValueError("empty tuning patch")
    normalized: dict[str, Any] = {}
    for k, raw in patch.items():
        v = validate_one(k, raw)
        typ, _ = _FIELD_SPECS[k]
        if typ is int and isinstance(v, float) and v.is_integer():
            v = int(v)
        normalized[k] = v
    # Cross-validation mirrors AF: overlap must be strictly less than size.
    merged = {**env_defaults(), **normalized}
    if merged["rag_chunk_overlap"] >= merged["rag_chunk_size"]:
        raise ValueError(
            f"rag_chunk_overlap ({merged['rag_chunk_overlap']}) must be strictly "
            f"less than rag_chunk_size ({merged['rag_chunk_size']})"
        )
    return normalized


def value_matches_env(key: str, value: Any, defaults: dict[str, Any]) -> bool:
    """True when the value equals the env default (redundant DB keys get stripped)."""
    env_v = defaults.get(key)
    if isinstance(env_v, bool):
        return bool(value) is env_v
    if isinstance(env_v, int) and not isinstance(env_v, bool):
        try:
            return int(value) == int(env_v)
        except (TypeError, ValueError):
            return False
    if isinstance(env_v, float):
        try:
            return abs(float(value) - float(env_v)) < 1e-9
        except (TypeError, ValueError):
            return False
    return str(value) == str(env_v)


def strip_keys_matching_env(overrides: dict[str, Any]) -> dict[str, Any]:
    defaults = env_defaults()
    return {k: v for k, v in overrides.items() if not value_matches_env(k, v, defaults)}


def effective_values(overrides: dict[str, Any]) -> dict[str, Any]:
    """Env defaults + DB overrides → flat effective dict."""
    return {**env_defaults(), **sanitize_overrides(overrides)}


def field_sources(overrides: dict[str, Any]) -> dict[str, str]:
    """Per-field env|db map for the console SourceChips."""
    return {k: ("db" if k in overrides else "env") for k in sorted(ALL_KEYS)}


def normalize_backend(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    return s if s in KNOWN_BACKENDS else "chroma"