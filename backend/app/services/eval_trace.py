"""
Diagnostic eval tracing for the chat pipeline (opt-in).

Enabled ONLY when env EVAL_TRACE_ENABLED is truthy ("1"/"true"/"yes").
When disabled, every hook is a no-op and the request path is untouched.

Writes one JSON line per request to EVAL_TRACE_FILE (default
data/eval/traces.jsonl). Records the full request path: query, history,
cache hit/miss + key hash, collection, retrieved chunks with scores and
provenance, final context, prompt, answer, citations, timings, error.

Records contain user-visible content (queries/answers) but never secrets:
no env values, tokens, or headers are captured.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def is_enabled() -> bool:
    """True when eval tracing is switched on via environment."""
    return os.environ.get("EVAL_TRACE_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def trace_file() -> str:
    """Path of the JSONL trace file."""
    return os.environ.get("EVAL_TRACE_FILE", "data/eval/traces.jsonl")


def content_head(text: str, limit: int = 200) -> str:
    """Compact verifiable representation of long content."""
    t = text or ""
    if len(t) <= limit:
        return t
    return t[:limit]


def content_sha256(text: str) -> str:
    """Content fingerprint (to verify full context without storing it twice)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


class EvalTrace:
    """Accumulates one diagnostic record per eval request and writes JSONL."""

    def __init__(self, eval_case_id: str | None = None, query: str | None = None):
        self.record: dict[str, Any] = {
            "request_id": str(__import__("uuid").uuid4()),
            "eval_case_id": eval_case_id,
            "query": query,
            "ts_started": time.time(),
            "error": None,
        }

    def set(self, key: str, value: Any) -> None:
        self.record[key] = value

    def set_error(self, error: str) -> None:
        self.record["error"] = error

    def finish(self, latency_ms: int) -> None:
        self.record["latency_ms_total"] = latency_ms
        self.record["ts_finished"] = time.time()
        try:
            path = Path(trace_file())
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(self.record, ensure_ascii=False) + "\n")
        except Exception:
            # Tracing must never break the request path.
            pass