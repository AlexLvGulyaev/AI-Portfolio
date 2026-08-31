"""Weaviate KB-class schema: tokenization contract for filter properties.

Root cause 31.08.2026: properties created without explicit tokenization get
Weaviate's default `word` tokenization. On a word-tokenized field,
`Filter.by_property("document_id").equal(doc_id)` matches every object whose
token set covers the query tokens — inserting USER_GUIDE.md silently deleted
chunks of ORCHESTRATOR_USER_GUIDE.md (~3% corpus, zero errors). The fix:
tokenization=field for every property used in exact-match filters.

Run inside the backend container: python tests/test_weaviate_schema_tokenization.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.weaviate_backend import (  # noqa: E402
    _FIELD_TOKENIZED_PROPERTIES,
    _TEXT_PROPERTIES,
    kb_class_properties,
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
    else:
        FAIL.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")


def main() -> None:
    from weaviate.classes.config import Tokenization

    check(
        "filter-properties-listed",
        all(p in _TEXT_PROPERTIES for p in _FIELD_TOKENIZED_PROPERTIES),
        f"field-tokenized names must all be _TEXT_PROPERTIES: "
        f"{_FIELD_TOKENIZED_PROPERTIES}",
    )

    props = {
        p.name: p
        for p in kb_class_properties()
     }
    for name in _TEXT_PROPERTIES:
        check(f"property-defined:{name}", name in props, "missing from schema list")

    for name in _FIELD_TOKENIZED_PROPERTIES:
        prop = props.get(name)
        got = getattr(prop, "tokenization", None)
        check(
            f"tokenization-field:{name}",
            got == Tokenization.FIELD,
            f"got {got!r}, expected {Tokenization.FIELD}",
        )

    # Display-only text properties keep the conventional word tokenization —
    # the fix must stay scoped to filter fields.
    for name in ("source", "path", "category", "url", "slug", "visibility"):
        prop = props.get(name)
        got = getattr(prop, "tokenization", None)
        check(
            f"tokenization-word:{name}",
            got == Tokenization.WORD,
            f"got {got!r}, expected {Tokenization.WORD}",
        )

    int_props = {"chunk_index", "total_chunks", "chunk_length"}
    prop = props.get("chunk_length")
    check(
        "int-props-present",
        int_props <= set(props),
        f"missing INT properties: {int_props - set(props)}",
    )
    check(
        "no-numeric-property-in-text-list",
        not (int_props & set(_TEXT_PROPERTIES)),
        "INT properties must not also be declared TEXT",
    )

    print(f"\nPASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()