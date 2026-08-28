"""
Tests for the diagnostic eval-tracing infrastructure.

Contract:
- tracing is opt-in (env EVAL_TRACE_ENABLED); disabled = no file, no records
- enabled = one JSON line per request with required diagnostic fields
- content_head/content_sha256 provide verifiable compact representations
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import eval_trace as et


def test_disabled_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EVAL_TRACE_ENABLED", None)
        assert et.is_enabled() is False
    print("PASS: disabled by default")


def test_enabled_by_flag():
    for v in ("1", "true", "YES"):
        with patch.dict(os.environ, {"EVAL_TRACE_ENABLED": v}):
            assert et.is_enabled() is True
    print("PASS: enabled by flag")


def test_trace_writes_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "traces.jsonl")
        with patch.dict(os.environ, {
            "EVAL_TRACE_ENABLED": "1",
            "EVAL_TRACE_FILE": f,
        }):
            assert et.is_enabled() is True
            tr = et.EvalTrace(eval_case_id="A-01", query="тест")
            tr.set("cache_hit", False)
            tr.set("retrieved_chunks", [{"rank": 1, "repo": "r/x", "path": "README.md"}])
            tr.set("answer", "ответ")
            tr.finish(1234)

        lines = Path(f).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        for key in ("request_id", "eval_case_id", "query", "cache_hit",
                    "retrieved_chunks", "answer", "latency_ms_total"):
            assert key in rec, key
        assert rec["eval_case_id"] == "A-01"
        assert rec["latency_ms_total"] == 1234
    print("PASS: jsonl record with required fields")


def test_content_helpers():
    head = et.content_head("x" * 500, limit=200)
    assert len(head) == 200
    assert et.content_head("abc") == "abc"
    h = et.content_sha256("abc")
    assert len(h) == 16 and h == et.content_sha256("abc")
    assert et.content_sha256("abc") != et.content_sha256("abd")
    print("PASS: content_head / content_sha256")


if __name__ == "__main__":
    test_disabled_by_default()
    test_enabled_by_flag()
    test_trace_writes_jsonl()
    test_content_helpers()
    print("All eval-trace tests passed.")