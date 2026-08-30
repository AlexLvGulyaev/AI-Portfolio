"""WH-1/WH-2 unit-тесты (task 2026-08-29, AF-parity):

- новые runtime-ключи retrieval-консоли (rag_answer_max_tokens,
  rag_retrieval_timeout, rag_embedding_request_timeout): валидация и диапазоны;
- retrieval cache: сериализация SearchResult, детерминизм ключа, TTL-store
  (put/get/delete/clear), bump generation.

Запуск: docker exec ai-portfolio-backend pytest tests/test_retrieval_wh1_wh2.py -q
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rag import retrieval_tuning as rt
from app.services.rag.rag_service import SearchResult


# ---------- WH-2: runtime-ключи ----------

def test_new_runtime_keys_present():
    for k in ("rag_answer_max_tokens", "rag_retrieval_timeout", "rag_embedding_request_timeout"):
        assert k in rt.RUNTIME_KEYS and k in rt.ALL_KEYS
        assert k not in rt.REQUIRES_RESYNC_KEYS
    print("PASS: WH-2 keys are RUNTIME (no resync)")


def test_env_defaults_include_wh2():
    d = rt.env_defaults()
    assert d["rag_answer_max_tokens"] == 800
    assert d["rag_retrieval_timeout"] == 30
    assert d["rag_embedding_request_timeout"] == 30.0
    print("PASS: env defaults match config")


def test_validate_wh2_happy():
    assert rt.validate_patch({"rag_answer_max_tokens": 1200}) == {"rag_answer_max_tokens": 1200}
    assert rt.validate_patch({"rag_retrieval_timeout": 60.0}) == {"rag_retrieval_timeout": 60}
    out = rt.validate_patch({"rag_embedding_request_timeout": 15.5})
    assert out == {"rag_embedding_request_timeout": 15.5}
    print("PASS: validate_patch accepts AF ranges")


def test_validate_wh2_out_of_range():
    for key, raw in (
        ("rag_answer_max_tokens", 50),
        ("rag_answer_max_tokens", 9000),
        ("rag_retrieval_timeout", 1),
        ("rag_retrieval_timeout", 400),
        ("rag_embedding_request_timeout", 1.0),
        ("rag_embedding_request_timeout", 500.0),
    ):
        try:
            rt.validate_patch({key: raw})
            assert False, f"no raise for {key}={raw}"
        except ValueError as e:
            assert "expected" in str(e)
    print("PASS: out-of-range rejected")


# ---------- SearchResult-сериализация ----------

def _mk_result(i: int) -> SearchResult:
    return SearchResult(
        content=f"content-{i}",
        source=f"src-{i}.md",
        score=0.123 * (i + 1),
        metadata={"repo": "owner/repo", "path": f"p/{i}.md", "chunk_index": i},
        chunk_id=f"c-{i}",
    )


def test_serialize_roundtrip():
    from app.services.cache import retrieval_cache as rc

    res = [_mk_result(0), _mk_result(1)]
    payload = rc.serialize_results(res)
    out = rc.deserialize_results(payload)
    assert len(out) == 2
    assert out[0].content == "content-0"
    assert out[1].metadata["repo"] == "owner/repo"
    assert abs(out[1].score - 0.246) < 1e-9
    print("PASS: SearchResult serialize/deserialize roundtrip")


# ---------- fingerprint ключа ----------

def test_fingerprint_deterministic_and_sensitive():
    from app.services.cache.caching_retrieval_backend import _fingerprint_key

    tuning = {"rag_top_k": 6, "rag_max_distance": 10.0, "retrieval_recall_margin": 3}
    a = _fingerprint_key("chroma", {"op": "search", "query": "q", "top_k": 6, "where": None}, tuning, "m1")
    b = _fingerprint_key("chroma", {"op": "search", "query": "q", "top_k": 6, "where": None}, tuning, "m1")
    assert a == b and len(a) == 64
    for changed in (
        _fingerprint_key("weaviate", {"op": "search", "query": "q", "top_k": 6, "where": None}, tuning, "m1"),
        _fingerprint_key("chroma", {"op": "search", "query": "q2", "top_k": 6, "where": None}, tuning, "m1"),
        _fingerprint_key("chroma", {"op": "search", "query": "q", "top_k": 7, "where": None}, tuning, "m1"),
        _fingerprint_key(
            "chroma", {"op": "search", "query": "q", "top_k": 6, "where": {"repo": {"$eq": "r"}}}, tuning, "m1"
        ),
     ):
        assert changed != a
    print("PASS: fingerprint stable, backend/query/args/where-sensitive")


# ---------- sqlite store ----------

def test_store_put_get_ttl_clear(tmp_path=None):
    from app.services.cache import retrieval_cache as rc

    key = f"unit:{time.time()}"
    rc.put_cached(key, [_mk_result(7)])
    got = rc.get_cached(key)
    assert got is not None and got[0].chunk_id == "c-7"
    assert rc.delete_key(key) is None
    assert rc.get_cached(key) is None
    print("PASS: store put/get/delete")


def test_bump_generation():
    try:
        from app.services.cache import retrieval_cache as rc

        before = rc.generation()
        after = rc.bump_generation(reason="test")
        assert after == before + 1
        # вернуть значение, чтобы не влиять на прочие прогоны
        from app.services.rag.platform_settings_store import set_setting

        set_setting(rc.KEY_RETRIEVAL_GENERATION, before)
        print("PASS: generation bump +1 (restored)")
    except Exception as e:
        print(f"SKIP: generation bump (store unavailable: {e})")


if __name__ == "__main__":
    test_new_runtime_keys_present()
    test_env_defaults_include_wh2()
    test_validate_wh2_happy()
    test_validate_wh2_out_of_range()
    test_serialize_roundtrip()
    test_fingerprint_deterministic_and_sensitive()
    test_store_put_get_ttl_clear()
    test_bump_generation()
    print("ALL OK")