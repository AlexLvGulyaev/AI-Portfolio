"""
CachingRetrievalBackend: обёртка над активным retrieval-бэкендом (WH-1).

Рекреация AF services/cache/caching_retrieval_backend.py: перехватывает
``search`` и ``search_diverse``; всё остальное (build_context, count_documents,
health, ...) проходит через ``__getattr__`` к базовому бэкенду.

Ключ кеша — детерминированный fingerprint:
  нормализованный запрос + имя бэкенда + аргументы вызова (top_k/where/repos/...)
  + runtime-тюнинг (top_k/max_distance/recall_margin) + embedding-модель
  + generation. Смена generation (после успешного KB-синка) инвалидирует всё.

Заметка о where-guard: публичный чат и admin chat-preview дают разные
where ($nin скрытых репозиториев есть только у публичного) — guard входит в
параметры вызова и в ключ, поэтому кеш не склеивает каналы.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.cache import retrieval_cache


def _fingerprint_key(
    backend_name: str,
    call: dict[str, Any],
    tuning: dict[str, Any],
    embedding_model: str,
) -> str:
    parts = {
        "v": "aip-rc1",
        "backend": backend_name,
        "call": call,
        "tuning": {
            "rag_top_k": tuning.get("rag_top_k"),
            "rag_max_distance": tuning.get("rag_max_distance"),
            "retrieval_recall_margin": tuning.get("retrieval_recall_margin"),
        },
        "embedding_model": embedding_model,
        "generation": retrieval_cache.generation(),
    }
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CachingRetrievalBackend:
    """Прозрачный кеш-слой над search/search_diverse активного бэкенда."""

    def __init__(self, base: Any, backend_name: str, tuning: dict[str, Any]) -> None:
        self._base = base
        self._backend_name = backend_name
        self._tuning = tuning
        self._embedding_model = getattr(
            getattr(base, "config", None), "embedding_model", ""
        )

    # ---------- cached operations ----------

    def search(self, query: str, top_k: int = 6, where: Any = None):
        key = _fingerprint_key(
            self._backend_name,
            {"op": "search", "query": query, "top_k": top_k, "where": where},
            self._tuning,
            self._embedding_model,
        )
        cached = retrieval_cache.get_cached(key)
        if cached is not None:
            return cached
        results = self._base.search(query, top_k=top_k, where=where)
        if results:
            retrieval_cache.put_cached(key, results)
        return results

    def search_diverse(
        self,
        query: str,
        repos: list[str] | None = None,
        per_repo_k: int = 1,
        final_top_k: int = 6,
        max_per_repo: int = 2,
    ):
        key = _fingerprint_key(
            self._backend_name,
            {
                "op": "search_diverse",
                "query": query,
                "repos": repos,
                "per_repo_k": per_repo_k,
                "final_top_k": final_top_k,
                "max_per_repo": max_per_repo,
            },
            self._tuning,
            self._embedding_model,
        )
        cached = retrieval_cache.get_cached(key)
        if cached is not None:
            return cached
        results = self._base.search_diverse(
            query,
            repos=repos,
            per_repo_k=per_repo_k,
            final_top_k=final_top_k,
            max_per_repo=max_per_repo,
        )
        if results:
            retrieval_cache.put_cached(key, results)
        return results

    # ---------- passthrough ----------

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)