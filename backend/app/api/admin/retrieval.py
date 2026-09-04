"""Admin API: retrieval console (active backend, health matrix, tuning).

Recreated from Assistant Flow admin_api/routes/retrieval.py (P6.10/P6.12),
adapted to the AI Portfolio auth/token model — require_admin instead of RBAC.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.admin.audit import log_admin_action
from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.core.config import get_settings
from app.services.rag import platform_settings_store as store
from app.services.rag.retrieval_manager import get_retrieval_manager
from app.services.rag.retrieval_tuning import (
    KEY_ACTIVE_RAG_BACKEND,
    KEY_RETRIEVAL_TUNING,
    KNOWN_BACKENDS,
    REQUIRES_RESYNC_KEYS,
    RUNTIME_KEYS,
    ALL_KEYS,
    env_defaults,
    normalize_backend,
    strip_keys_matching_env,
    validate_patch,
)

router = APIRouter(prefix="/retrieval")


class ActiveBackendBody(BaseModel):
    backend: str


class RetrievalCacheToggleBody(BaseModel):
    enabled: bool


class TuningPutBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rag_top_k: int | None = None
    rag_max_distance: float | None = None
    retrieval_recall_margin: int | None = None
    # AF parity (WH-2): generation cap + timeouts.
    rag_answer_max_tokens: int | None = None
    rag_retrieval_timeout: int | None = None
    rag_embedding_request_timeout: float | None = None
    chroma_ef_search: int | None = None
    chroma_ef_construction: int | None = None
    rag_chunk_size: int | None = None
    rag_chunk_overlap: int | None = None


def _patch_from_body(body: TuningPutBody) -> dict[str, Any]:
    """Only fields present in the JSON (explicit values preserved, None ignored)."""
    return {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}


@router.get("/overview")
def api_retrieval_overview(_admin: None = Depends(require_admin)) -> dict[str, Any]:
    """Env/DB/effective backend matrix + per-backend health + tuning snapshot."""
    mgr = get_retrieval_manager()
    effective = mgr.effective_backend()
    backends = {name: mgr.probe_backend(name) for name in sorted(KNOWN_BACKENDS)}
    tuning = mgr.effective_tuning()
    active_health = backends.get(effective, {})
    warnings: list[str] = []
    if not active_health.get("ok"):
        warnings.append(f"active_backend_health:{effective}:{active_health.get('detail')}")
    return {
        "env_default_backend": normalize_backend(get_settings().rag_backend),
        "db_active_backend": _db_backend_string(),
        "effective_backend": effective,
        "allowed_backends": sorted(KNOWN_BACKENDS),
        "backends": backends,
        "active_backend_health": active_health,
        "warnings": warnings,
        "tuning": {
            "runtime_keys": sorted(RUNTIME_KEYS),
            "all_keys": sorted(ALL_KEYS),
            "requires_resync_keys": sorted(REQUIRES_RESYNC_KEYS),
            "effective": tuning,
            "env_defaults": env_defaults(),
            "db_overrides": mgr.db_overrides(),
            "field_sources": mgr.tuning_sources(),
        },
        "paths": _paths_snapshot(),
        "cache": _cache_snapshot(),
    }


def _cache_snapshot() -> dict[str, Any]:
    """WH-1: retrieval cache state for the console panel."""
    from app.services.cache import retrieval_cache

    state = retrieval_cache.effective_state()
    return {
        "enabled": state["enable_retrieval_cache"],
        "enabled_env_default": retrieval_cache._env_defaults()["enable_retrieval_cache"],
        "ttl_seconds": state["ttl_seconds"],
        "generation": state["generation"],
        # reserved, не задействован (роль играет выключенный ResponseCache
        # registry-only v4): отображается в консоли как reserved.
        "enable_answer_cache": False,
        "store_path": retrieval_cache.db_path(),
        "entry_count": retrieval_cache.entry_count(),
        "stats": retrieval_cache.stats(),
    }


def _db_backend_string() -> str | None:
    value = store.get_setting(KEY_ACTIVE_RAG_BACKEND)
    return value if isinstance(value, str) else None


def _paths_snapshot() -> dict[str, Any]:
    from app.core.config import get_settings

    s = get_settings()
    return {
        "chroma_host": s.chroma_host,
        "chroma_port": s.chroma_port,
        "chroma_use_http": s.chroma_use_http,
        "chroma_collection_name": s.chroma_collection_name,
        "chroma_kb_v1_scope_note": "Indexing (KB sync) targets Chroma in v1; Weaviate fill is a follow-up iteration.",
        "weaviate_host": s.weaviate_host,
        "weaviate_http_port": s.weaviate_http_port,
        "weaviate_grpc_port": s.weaviate_grpc_port,
        "weaviate_class_name": s.weaviate_class_name,
    }


@router.put("/active-backend")
def api_retrieval_active_backend(
    body: ActiveBackendBody,
    request: Request,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist the active backend to PG; switching is allowed even if unhealthy (warning returned)."""
    name = normalize_backend(body.backend)
    if name not in KNOWN_BACKENDS or (body.backend or "").strip() not in KNOWN_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported backend {body.backend!r}; allowed: {', '.join(sorted(KNOWN_BACKENDS))}",
        )
    mgr = get_retrieval_manager()
    probe = mgr.probe_backend(name)
    warnings: list[str] = []
    if not probe.get("ok"):
        warnings.append(f"target_health_not_ok:{probe.get('detail')}")
    try:
        store.set_setting(KEY_ACTIVE_RAG_BACKEND, name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    mgr.refresh(reason="active_backend_switch")
    log_admin_action(request, db, action="set_active_backend", resource_type="retrieval_tuning",
                     details={"backend": name, "warnings": warnings})
    return {
        "effective_backend": get_retrieval_manager().effective_backend(),
        "warnings": warnings,
    }


@router.get("/tuning")
def api_retrieval_tuning_get(_admin: None = Depends(require_admin)) -> dict[str, Any]:
    mgr = get_retrieval_manager()
    return {
        "effective": mgr.effective_tuning(),
        "env_defaults": env_defaults(),
        "db_overrides": mgr.db_overrides(),
        "field_sources": mgr.tuning_sources(),
        "runtime_keys": sorted(RUNTIME_KEYS),
        "requires_resync_keys": sorted(REQUIRES_RESYNC_KEYS),
    }


@router.put("/tuning")
def api_retrieval_tuning_put(
    body: TuningPutBody,
    request: Request,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    patch = _patch_from_body(body)
    if not patch:
        raise HTTPException(status_code=400, detail="empty body: provide at least one tuning field")
    try:
        normalized = validate_patch(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    merged = strip_keys_matching_env({**get_retrieval_manager().db_overrides(), **normalized})
    try:
        if merged:
            store.set_setting(KEY_RETRIEVAL_TUNING, merged)
        else:
            store.delete_setting(KEY_RETRIEVAL_TUNING)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    mgr = get_retrieval_manager()
    mgr.refresh(reason="tuning_update")
    log_admin_action(request, db, action="update", resource_type="retrieval_tuning",
                     changed_fields=sorted(normalized),
                     details={"resync_required": any(k in normalized for k in REQUIRES_RESYNC_KEYS)})
    return {
        "effective": mgr.effective_tuning(),
        "env_defaults": env_defaults(),
        "db_overrides": mgr.db_overrides(),
        "field_sources": mgr.tuning_sources(),
        "resync_required": any(k in normalized for k in REQUIRES_RESYNC_KEYS),
        "note": "runtime fields apply within ~2.5s; chroma_ef_* apply at next collection creation",
    }


@router.delete("/tuning")
def api_retrieval_tuning_delete(
    request: Request,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        store.delete_setting(KEY_RETRIEVAL_TUNING)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    get_retrieval_manager().refresh(reason="tuning_clear")
    log_admin_action(request, db, action="tuning_reset", resource_type="retrieval_tuning")
    return {"effective": get_retrieval_manager().effective_tuning(), "db_overrides": {}}

@router.put("/cache/toggle")
def api_retrieval_cache_toggle(
    body: RetrievalCacheToggleBody,
    request: Request,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """WH-1: persist the retrieval-cache on/off switch to PG and rewrap the backend."""
    from app.services.cache import retrieval_cache

    try:
        retrieval_cache.set_enabled(body.enabled)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    get_retrieval_manager().refresh(reason="retrieval_cache_toggle")
    log_admin_action(request, db, action="cache_toggle", resource_type="retrieval_tuning",
                     details={"enabled": body.enabled})
    return {"cache": _cache_snapshot()}


@router.post("/cache/clear")
def api_retrieval_cache_clear(
    request: Request,
    _admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """WH-1: drop all cached retrieval entries (diagnostics action)."""
    from app.services.cache import retrieval_cache

    removed = retrieval_cache.clear()
    log_admin_action(request, db, action="cache_clear", resource_type="retrieval_tuning",
                     details={"removed": removed})
    return {"removed": removed, "cache": _cache_snapshot()}
