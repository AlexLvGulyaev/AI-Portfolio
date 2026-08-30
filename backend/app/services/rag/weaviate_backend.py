"""
Weaviate retrieval backend (BYOV) — recreated from Assistant Flow
``services/retrieval/weaviate_backend.py`` (battle-proven schema and client
usage), adapted to the AI Portfolio metadata contract.

Weaviate stores our pre-computed embeddings (vectorizer=none) and serves the
same surface as RAGService: search / search_diverse / count_documents /
build_context. Since 29.08.2026 the backend also implements the write half
(index_store contract: add_chunks / delete_document_chunks /
clear_by_source_type / clear_collection) — KB indexing follows the
effective-active backend instead of being hardwired to Chroma.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Optional

from app.services.rag.rag_service import RECALL_MARGIN, SearchResult


def build_context(results: list[SearchResult], max_tokens: Optional[int] = None) -> str:
    """Same context contract as RAGService.build_context (shared result shape)."""
    if not results:
        return ""
    parts: list[str] = []
    length = 0
    for i, result in enumerate(results, 1):
        repo = result.metadata.get("repo")
        label = f"{repo} · {result.source}" if repo else result.source
        part = f"\n[{i}] {label}:\n{result.content}\n"
        if max_tokens:
            part_tokens = len(part) // 4
            if length + part_tokens > max_tokens:
                break
            length += part_tokens
        parts.append(part)
    return "".join(parts)


def merge_diverse(
    per_repo_results: list[list[SearchResult]],
    final_top_k: int,
    max_per_repo: int,
) -> list[SearchResult]:
    """Merge per-repo result lists by distance with a per-repo quota (RAGService contract)."""
    merged: list[SearchResult] = [r for chunk in per_repo_results for r in chunk]
    merged.sort(key=lambda r: r.score)
    repo_counts: dict[str, int] = {}
    diversified: list[SearchResult] = []
    for r in merged:
        repo = r.metadata.get("repo") or "?"
        if repo_counts.get(repo, 0) >= max_per_repo:
            continue
        repo_counts[repo] = repo_counts.get(repo, 0) + 1
        diversified.append(r)
        if len(diversified) >= final_top_k:
            break
    return diversified


class WeaviateBackend:
    """Operational Weaviate: schema ensure, near_vector search over BYOV vectors."""

    def __init__(
        self,
        *,
        host: str,
        http_port: int,
        grpc_port: int,
        class_name: str,
        embeddings_fn: Callable[[list[str]], list[list[float]]],
        recall_margin: int = RECALL_MARGIN,
        max_distance: float = 10.0,
    ):
        import weaviate

        if not class_name or not class_name.strip():
            raise ValueError("weaviate class_name must not be empty")
        self.class_name = class_name.strip()
        self._embeddings_fn = embeddings_fn
        self._margin = max(1, int(recall_margin))
        self._max_distance = float(max_distance)
        self._client = weaviate.connect_to_custom(
            http_host=host,
            http_port=int(http_port),
            http_secure=False,
            grpc_host=host,
            grpc_port=int(grpc_port),
            grpc_secure=False,
        )
        self._ensure_schema()

    @property
    def backend_name(self) -> str:
        return "weaviate"

    @property
    def config(self) -> Any:
        """RAGConfig-like surface consumed by ChatOrchestrator
        (collection name for traces; parity with RAGService)."""
        return SimpleNamespace(
            collection_name=self.class_name,
            backend="weaviate",
        )

    def build_context(
        self, results: list[SearchResult], max_tokens: Optional[int] = None
    ) -> str:
        """Class-method wrapper used by ChatOrchestrator (delegates to the
        module-level builder — same contract as RAGService.build_context)."""
        return build_context(results, max_tokens)

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def _ensure_schema(self) -> None:
        """Idempotent class creation; adds missing properties to older schemas."""
        from weaviate.classes.config import Configure, DataType, Property

        if not self._client.collections.exists(self.class_name):
            self._client.collections.create(
                name=self.class_name,
                vectorizer_config=Configure.Vectorizer.none(),
                vector_index_config=Configure.VectorIndex.hnsw(),
                properties=[
                    Property(name="text", data_type=DataType.TEXT),
                    Property(name="chunk_id", data_type=DataType.TEXT),
                    Property(name="document_id", data_type=DataType.TEXT),
                    Property(name="source", data_type=DataType.TEXT),
                    Property(name="repo", data_type=DataType.TEXT),
                    Property(name="path", data_type=DataType.TEXT),
                    Property(name="source_type", data_type=DataType.TEXT),
                    Property(name="category", data_type=DataType.TEXT),
                    Property(name="url", data_type=DataType.TEXT),
                    Property(name="commit_sha", data_type=DataType.TEXT),
                    Property(name="slug", data_type=DataType.TEXT),
                    Property(name="visibility", data_type=DataType.TEXT),
                    Property(name="chunk_index", data_type=DataType.INT),
                    Property(name="total_chunks", data_type=DataType.INT),
                    Property(name="chunk_length", data_type=DataType.INT),
                ],
            )
        try:
            coll = self._client.collections.get(self.class_name)
            names = {p.name for p in (coll.config.get().properties or [])}
            missing = [
                name
                for name in (
                    "repo", "path", "source_type", "category", "url",
                    "commit_sha", "slug", "visibility", "chunk_length",
                )
                if name not in names
            ]
            if missing:
                for name in missing:
                    coll.config.add_property(
                        Property(name=name, data_type=DataType.TEXT)
                    )
        except Exception:
            pass

    def _collection(self) -> Any:
        return self._client.collections.get(self.class_name)

    def count_documents(self) -> int:
        coll = self._collection()
        agg = coll.aggregate.over_all(total_count=True)
        total = getattr(agg, "total_count", None)
        try:
            return int(total) if total is not None else 0
        except (TypeError, ValueError):
            return 0

    def _query(self, vector: list[float], limit: int, repo_filter: Any = None) -> Any:
        from weaviate.classes.query import MetadataQuery

        coll = self._collection()
        return coll.query.near_vector(
            near_vector=vector,
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
            filters=repo_filter,
        )

    def _to_results(self, resp: Any) -> list[SearchResult]:
        out: list[SearchResult] = []
        for obj in getattr(resp, "objects", None) or []:
            props = obj.properties or {}
            meta = {
                "repo": props.get("repo"),
                "source_type": props.get("source_type"),
                "chunk_id": props.get("chunk_id"),
                "document_id": props.get("document_id"),
                # полный паритет метаданных chroma-чанков (provenance == repo+path)
                "path": props.get("path"),
                "category": props.get("category"),
                "url": props.get("url"),
                "commit_sha": props.get("commit_sha"),
                "slug": props.get("slug"),
            }
            visibility = str(props.get("visibility") or "").strip().lower()
            if visibility:
                meta["visibility"] = visibility
            ci = props.get("chunk_index")
            tc = props.get("total_chunks")
            if ci is not None:
                meta["chunk_index"] = ci
            if tc is not None:
                meta["total_chunks"] = tc
            cl = props.get("chunk_length")
            if cl is not None:
                meta["chunk_length"] = cl
            distance = 0.0
            if obj.metadata is not None and obj.metadata.distance is not None:
                distance = float(obj.metadata.distance)
            out.append(SearchResult(
                content=str(props.get("text") or ""),
                source=str(props.get("source") or "unknown"),
                score=distance,
                metadata={k: v for k, v in meta.items() if v is not None and v != ""},
            ))
        return out

    @staticmethod
    def _repo_filter(where: Optional[dict[str, Any]]):
        """Translate our chroma-style where (repo $eq / $nin) into a Weaviate filter."""
        if not where:
            return None
        from weaviate.classes.query import Filter

        repo = where.get("repo")
        if not isinstance(repo, dict):
            return None
        try:
            if "$eq" in repo:
                return Filter.by_property("repo").equal(str(repo["$eq"]))
            if "$nin" in repo:
                excluded = [str(v) for v in repo["$nin"]]
                if not excluded:
                    return None
                return ~Filter.by_property("repo").contains_any(excluded)
        except TypeError:
            # Older weaviate-client without the ~ operator — degrade to no filter;
            # public results are additionally re-checked by orchestrator-level guards.
            return None
        return None

    def search(
        self,
        query: str,
        top_k: int = 3,
        where: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        """near_vector search with a recall margin window, trimmed to top_k."""
        if not query.strip() or top_k <= 0:
            return []
        n = self.count_documents()
        if n == 0:
            return []
        vector = self._embeddings_fn([query.strip()])[0]
        limit = min(top_k * self._margin, n)
        try:
            resp = self._query(vector, limit, self._repo_filter(where))
        except Exception:
            # Negation-filter not supported by this client/server combination:
            # retry unfiltered (margin window still covers most head-room).
            if where is None:
                raise
            resp = self._query(vector, limit)
        results = self._to_results(resp)
        if where:
            excluded = (where.get("repo") or {}).get("$nin") or []
            if excluded:
                excluded = {str(v) for v in excluded}
                results = [
                    r for r in results
                    if str(r.metadata.get("repo") or "") not in excluded
                ]
        return [r for r in results if r.score <= self._max_distance][:top_k]

    def search_diverse(
        self,
        query: str,
        repos: list[str],
        per_repo_k: int = 1,
        final_top_k: int = 6,
        max_per_repo: int = 2,
    ) -> list[SearchResult]:
        """Per-repo near_vector with a margin window, merged by distance with quotas."""
        if not query.strip() or not repos:
            return []
        n = self.count_documents()
        if n == 0:
            return []
        vector = self._embeddings_fn([query.strip()])[0]
        per_repo: list[list[SearchResult]] = []
        for repo in repos:
            limit = min(max(1, per_repo_k * self._margin), n)
            from weaviate.classes.query import Filter

            try:
                repo_filter = Filter.by_property("repo").equal(str(repo))
                resp = self._query(vector, limit, repo_filter)
            except Exception:
                continue
            per_repo.append(self._to_results(resp))
        return merge_diverse(per_repo, final_top_k, max_per_repo)

    # ------------------------------------------------------------------
    # Write half (index_store contract) — KB indexing follows the active
    # backend (owner decision 29.08.2026): whichever backend is effective
    # must be the one KB-sync (re)indexes into.
    # ------------------------------------------------------------------

    _INT_PROPERTIES = ("chunk_index", "total_chunks", "chunk_length")

    @staticmethod
    def _chunk_uuid(chunk_id: str) -> str:
        """Deterministic UUID for a chunk id — re-index of the same chunk
        reuses the uuid (document chunks are deleted before insert)."""
        import uuid as _uuid

        return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"ai-portfolio:{chunk_id}"))

    @staticmethod
    def _chunk_properties(
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build batch insert objects (properties + uuid) from indexer shapes."""
        props: list[dict[str, Any]] = []
        for i, (text, metadata) in enumerate(zip(documents, metadatas)):
            meta = dict(metadata or {})
            item: dict[str, Any] = {
                "text": str(text),
                "source": str(meta.get("source") or "unknown"),
                "document_id": str(meta.get("document_id") or ""),
                "chunk_id": str(meta.get("chunk_id") or ""),
            }
            for name in (
                "repo", "path", "source_type", "category", "url",
                "commit_sha", "slug", "visibility",
            ):
                if meta.get(name) is not None and str(meta[name]) != "":
                    item[name] = str(meta[name])
            for name in WeaviateBackend._INT_PROPERTIES:
                if meta.get(name) is not None:
                    try:
                        item[name] = int(meta[name])
                    except (TypeError, ValueError):
                        pass
            props.append(item)
        return props

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Batch-insert pre-embedded chunks (BYOV, vectorizer=none)."""
        props = self._chunk_properties(documents, metadatas)
        coll = self._collection()
        from weaviate.classes.data import DataObject

        objects = [
            DataObject(
                properties=props[i],
                uuid=self._chunk_uuid(ids[i]),
                vector=embeddings[i],
            )
            for i in range(len(props))
        ]
        result = coll.data.insert_many(objects)
        # Per-object batch failures surface in the return value, not as an
        # exception — swallowing them silently loses documents (seen live:
        # 6 docs missing after a full sync, 29.08.2026). Fail loudly.
        errors = getattr(result, "errors", None)
        if errors:
            first = str(next(iter(errors.items())))
            raise RuntimeError(
                f"weaviate insert_many: {len(errors)}/{len(objects)} objects "
                f"failed; first: {first}"
            )

    def delete_document_chunks(self, document_id: str) -> int:
        """Delete every chunk of a document before re-indexing it."""
        if not document_id:
            return 0
        from weaviate.classes.query import Filter

        coll = self._collection()
        result = coll.data.delete_many(
            where=Filter.by_property("document_id").equal(document_id)
        )
        deleted = getattr(result, "successful", 0)
        try:
            return int(deleted or 0)
        except (TypeError, ValueError):
            return 0

    def clear_by_source_type(self, source_type: str) -> int:
        """Delete all chunks whose source_type equals the given value."""
        from weaviate.classes.query import Filter

        coll = self._collection()
        result = coll.data.delete_many(
            where=Filter.by_property("source_type").equal(source_type)
        )
        deleted = getattr(result, "successful", 0)
        try:
            return int(deleted or 0)
        except (TypeError, ValueError):
            return 0

    def clear_collection(self) -> None:
        """Delete every chunk of the class (documented index_store contract)."""
        coll = self._collection()
        coll.data.delete_many()

    def health(self) -> dict[str, Any]:
        detail = f"class={self.class_name}"
        try:
            if not self._client.is_ready():
                return {"ok": False, "detail": f"{detail}; not ready", "count": None}
            n = self.count_documents()
            return {"ok": True, "detail": f"{detail}; ready", "count": n}
        except Exception as exc:
            return {
                "ok": False,
                "detail": f"{detail}; {type(exc).__name__}: {exc}",
                "count": None,
            }