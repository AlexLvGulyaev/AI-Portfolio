"""Unit-тесты ретривал-консоли (task 2026-08-29, recreation from AF)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException

from app.services.rag import retrieval_tuning as rt
from app.services.rag.weaviate_backend import merge_diverse
from app.services.rag.rag_service import SearchResult


# ---------- validate_patch ----------

def test_validate_patch_happy():
    out = rt.validate_patch({"rag_top_k": 8, "rag_max_distance": 1.5})
    assert out == {"rag_top_k": 8, "rag_max_distance": 1.5}
    print("PASS: validate_patch normalizes valid patch")


def test_validate_patch_unknown_and_empty():
    try:
        rt.validate_patch({"nope": 1}); assert False
    except ValueError as e:
        assert "unknown tuning keys" in str(e)
    try:
        rt.validate_patch({}); assert False
    except ValueError:
        pass
    print("PASS: unknown keys / empty patch rejected")


def test_validate_patch_ranges_and_cross_check():
    try:
        rt.validate_patch({"rag_top_k": 0}); assert False
    except ValueError as e:
        assert "1..20" in str(e)
    try:
        rt.validate_patch({"rag_max_distance": 99}); assert False
    except ValueError:
        pass
    try:
        rt.validate_patch({"rag_chunk_size": 500, "rag_chunk_overlap": 500}); assert False
    except ValueError as e:
        assert "strictly" in str(e)
    print("PASS: range and chunk-size cross-validation enforced")


# ---------- env defaults / strip ----------

def test_env_defaults_cover_all_keys():
    d = rt.env_defaults()
    assert set(d) == set(rt.ALL_KEYS)
    assert d["rag_top_k"] >= 1 and d["chroma_ef_search"] >= 10
    print("PASS: env defaults cover all tuning keys")


def test_strip_keys_matching_env():
    defaults = rt.env_defaults()
    overrides = {"rag_top_k": defaults["rag_top_k"], "rag_top_k_x": None, "rag_max_distance": 2.0}
    overrides = {k: v for k, v in overrides.items() if v is not None}
    stripped = rt.strip_keys_matching_env(overrides)
    assert stripped == {"rag_max_distance": 2.0}
    print("PASS: redundant env-equal keys stripped")


def test_effective_values_merge():
    merged = rt.effective_values({"rag_top_k": 9, "junk": "x"})
    assert merged["rag_top_k"] == 9
    assert "junk" not in merged
    print("PASS: effective values merge env + sanitized overrides")


# ---------- sanitize / sources ----------

def test_sanitize_and_sources():
    raw = {"rag_top_k": 5, "hack": "x", "rag_max_distance": None}
    clean = rt.sanitize_overrides(raw)
    assert clean == {"rag_top_k": 5, "rag_max_distance": None} or "rag_max_distance" not in clean
    assert "hack" not in clean
    src = rt.field_sources({"rag_top_k": 5})
    assert src["rag_top_k"] == "db" and src["rag_max_distance"] == "env"
    print("PASS: sanitize drops unknown keys; sources per-field")


# ---------- normalize_backend ----------

def test_normalize_backend():
    assert rt.normalize_backend(None) == "chroma"
    assert rt.normalize_backend("faiss") == "chroma"  # unsupported → chroma
    assert rt.normalize_backend("weaviate") == "weaviate"
    print("PASS: backend normalization")


# ---------- weaviate merge_diverse ----------

def _r(repo, score):
    return SearchResult(content="t", source="f.md", score=score, metadata={"repo": repo})


def test_merge_diverse_quota():
    per_repo = [
        [_r("a", 0.1), _r("a", 0.2), _r("a", 0.3)],
        [_r("b", 0.15)],
        [_r("c", 0.4)],
    ]
    out = merge_diverse(per_repo, final_top_k=4, max_per_repo=2)
    assert [x.metadata["repo"] for x in out] == ["a", "b", "a", "c"]
    print("PASS: merge_diverse sorts by distance with per-repo quota")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL RETRIEVAL CONSOLE TESTS PASSED")