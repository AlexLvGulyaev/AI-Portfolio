"""
Retrieval manager: active backend resolution + effective tuning + lazy build.

Recreated from Assistant Flow ``services/retrieval/runtime_manager.py`` (P6.9/
P6.10 pattern): PG ``platform_settings`` stores the active backend and tuning
overrides; the manager caches effective values for ~2.5 s, rebuilds the
backend lazily when the build signature changes, and never silently falls
back — a failed build raises (the admin console exposes the health detail).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from app.core.config import get_settings
from app.services.rag import platform_settings_store as store
from app.services.rag.rag_service import RAGConfig, RAGService
from app.services.rag.retrieval_tuning import (
    KEY_ACTIVE_RAG_BACKEND,
    KEY_RETRIEVAL_TUNING,
    KNOWN_BACKENDS,
    effective_values,
    field_sources,
    normalize_backend,
)

_EFFECTIVE_CACHE_S = 2.5


def make_embeddings_fn(
    config: RAGConfig, timeout: float | None = None
) -> Callable[[list[str]], list[list[float]]]:
    """Callable mapping texts to embedding vectors via the configured OpenAI-compatible API.

    `timeout` (AF WH-2, rag_embedding_request_timeout) is passed to the OpenAI
    client verbatim; None keeps the SDK default.
    """
    from openai import OpenAI

    client = (
        OpenAI(api_key=get_settings().openai_api_key, timeout=timeout)
        if timeout is not None
        else OpenAI(api_key=get_settings().openai_api_key)
    )
    model = config.embedding_model

    def embed(texts: list[str]) -> list[list[float]]:
        response = client.embeddings.create(
            model=model, input=texts, encoding_format="float"
        )
        return [item.embedding for item in response.data]

    return embed


def _settings_base_config() -> RAGConfig:
    """Base chroma config from env (keeps RAGConfig.from_settings as source)."""
    return RAGConfig.from_settings()


def replace_tuning(cfg: RAGConfig, tuning: dict[str, Any]) -> RAGConfig:
    """Apply effective tuning fields onto a RAGConfig copy."""
    from dataclasses import replace

    return replace(
        cfg,
        recall_margin=int(tuning["retrieval_recall_margin"]),
        max_distance=float(tuning["rag_max_distance"]),
        ef_search=int(tuning["chroma_ef_search"]),
        ef_construction=int(tuning["chroma_ef_construction"]),
        chunk_size=int(tuning["rag_chunk_size"]),
        chunk_overlap=int(tuning["rag_chunk_overlap"]),
        embedding_request_timeout=float(tuning["rag_embedding_request_timeout"]),
    )


class RetrievalManager:
    """Active retrieval backend + effective tuning (effective cache 2.5 s)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._backend: Any = None
        self._built_key: Optional[tuple] = None
        self._cache_enabled_at_build: bool = False
        self._eff_backend: Optional[str] = None
        self._eff_backend_at: float = 0.0
        self._eff_tuning: Optional[dict[str, Any]] = None
        self._eff_tuning_at: float = 0.0

    # ---------- effective values ----------

    def _db_value(self, key: str) -> Any | None:
        try:
            return store.get_setting(key)
        except Exception:
            return None

    def effective_backend(self) -> str:
        """PG override when a valid backend name, else env default (AF pattern)."""
        now = time.monotonic()
        if (
            self._eff_backend is not None
            and (now - self._eff_backend_at) < _EFFECTIVE_CACHE_S
        ):
            return self._eff_backend
        env_default = normalize_backend(get_settings().rag_backend)
        db_v = self._db_value(KEY_ACTIVE_RAG_BACKEND)
        resolved = env_default
        if isinstance(db_v, str) and db_v.strip() in KNOWN_BACKENDS:
            resolved = db_v.strip()
        self._eff_backend = resolved
        self._eff_backend_at = now
        return resolved

    def effective_tuning(self) -> dict[str, Any]:
        """Env defaults + PG overrides (build-time fields consumed at backend build)."""
        now = time.monotonic()
        if (
            self._eff_tuning is not None
            and (now - self._eff_tuning_at) < _EFFECTIVE_CACHE_S
        ):
            return self._eff_tuning
        db = self._db_value(KEY_RETRIEVAL_TUNING)
        overrides = (
            {k: v for k, v in db.items() if isinstance(v, (int, float))}
            if isinstance(db, dict)
            else {}
        )
        self._eff_tuning = effective_values(overrides)
        self._eff_tuning_at = now
        return self._eff_tuning

    def tuning_sources(self) -> dict[str, str]:
        db = self._db_value(KEY_RETRIEVAL_TUNING)
        return field_sources(db if isinstance(db, dict) else {})

    def db_overrides(self) -> dict[str, Any]:
        db = self._db_value(KEY_RETRIEVAL_TUNING)
        return dict(db) if isinstance(db, dict) else {}

    # ---------- backend lifecycle ----------

    @staticmethod
    def _build_key(name: str, tuning: dict[str, Any]) -> tuple:
        """Selects what forces a backend rebuild (runtime fields do not)."""
        return (
            name,
            tuning["chroma_ef_search"],
            tuning["chroma_ef_construction"],
            tuning["retrieval_recall_margin"],
        )

    def _build_backend(self, name: str, tuning: dict[str, Any]) -> Any:
        if name == "chroma":
            return RAGService(config=replace_tuning(_settings_base_config(), tuning))
        if name == "weaviate":
            from app.services.rag.weaviate_backend import WeaviateBackend

            return WeaviateBackend(
                host=get_settings().weaviate_host,
                http_port=get_settings().weaviate_http_port,
                grpc_port=get_settings().weaviate_grpc_port,
                class_name=get_settings().weaviate_class_name,
                embeddings_fn=make_embeddings_fn(
                    _settings_base_config(),
                    timeout=float(tuning["rag_embedding_request_timeout"]),
                ),
                recall_margin=tuning["retrieval_recall_margin"],
                max_distance=float(tuning["rag_max_distance"]),
            )
        raise ValueError(
            f"unsupported retrieval backend {name!r}; "
            f"allowed: {', '.join(sorted(KNOWN_BACKENDS))}"
        )

    def get_backend(self) -> Any:
        """Active backend, rebuilt lazily when the build signature changes.

        When the retrieval cache is enabled (WH-1), the search surface is
        wrapped in CachingRetrievalBackend; toggling the cache rewraps without
        touching the underlying connection.
        """
        from app.services.cache import retrieval_cache
        from app.services.cache.caching_retrieval_backend import CachingRetrievalBackend

        name = self.effective_backend()
        tuning = self.effective_tuning()
        key = self._build_key(name, tuning)
        cache_enabled = retrieval_cache.is_enabled()
        with self._lock:
            if (
                self._backend is None
                or self._built_key != key
                or self._cache_enabled_at_build != cache_enabled
            ):
                base = self._build_backend(name, tuning)
                self._backend = (
                    CachingRetrievalBackend(base, name, tuning)
                    if cache_enabled
                    else base
                )
                self._built_key = key
                self._cache_enabled_at_build = cache_enabled
        return self._backend

    def refresh(self, reason: str = "manual") -> None:
        """Drop cached backend + effective caches (after switch / tuning change)."""
        with self._lock:
            self._backend = None
            self._built_key = None
            self._eff_backend = None
            self._eff_backend_at = 0.0
            self._eff_tuning = None
            self._eff_tuning_at = 0.0

    # ---------- health probes ----------

    def probe_backend(self, name: str) -> dict[str, Any]:
        """Per-backend probe without switching the active one (console health matrix)."""
        if name == "chroma":
            return self._probe_chroma()
        if name == "weaviate":
            return self._probe_weaviate()
        return {"ok": False, "detail": f"unknown backend {name!r}", "count": None}

    def _probe_chroma(self) -> dict[str, Any]:
        try:
            import chromadb

            settings = get_settings()
            client = chromadb.HttpClient(
                host=settings.chroma_host, port=settings.chroma_port
            )
            try:
                coll = client.get_collection(settings.chroma_collection_name)
                return {"ok": True, "detail": "ready", "count": int(coll.count())}
            except Exception:
                return {
                    "ok": True,
                    "detail": "server reachable; collection missing (create via resync)",
                    "count": None,
                }
        except Exception as exc:
            return {
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "count": None,
            }

    def _probe_weaviate(self) -> dict[str, Any]:
        try:
            from app.services.rag.weaviate_backend import WeaviateBackend

            settings = get_settings()
            backend = WeaviateBackend(
                host=settings.weaviate_host,
                http_port=settings.weaviate_http_port,
                grpc_port=settings.weaviate_grpc_port,
                class_name=settings.weaviate_class_name,
                embeddings_fn=make_embeddings_fn(
                    _settings_base_config(),
                    timeout=float(self.effective_tuning()["rag_embedding_request_timeout"]),
                ),
                recall_margin=1,
            )
            try:
                return backend.health()
            finally:
                backend.close()
        except Exception as exc:
            return {
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "count": None,
            }


_manager: Optional[RetrievalManager] = None
_manager_lock = threading.Lock()


def get_retrieval_manager() -> RetrievalManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = RetrievalManager()
    return _manager