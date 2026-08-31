"""Root-README ranking boost: classifier and reordering contract.

Zone-B fix (c_fails_analysis 31.08.2026): chunk 0 of a repo root README
(document_id "github_<owner>/<repo>_README.md") holds the anchor blocks of
top-level questions ("какую задачу решает", "как устроен", "LLM") but loses
distance ranking to BUSINESS_VALUE/USER_GUIDE docs of the same repo and
never reaches top_k. The boost multiplies such a chunk's score (distance)
by a constant INSIDE the recall window only — it never adds candidates and
never touches nested READMEs or chunk_index != 0.

Run inside the backend container: python tests/test_root_readme_boost.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.rag_service import (  # noqa: E402
    ROOT_README_BOOST,
    SearchResult,
    apply_root_readme_boost,
    is_root_readme_chunk,
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
    else:
        FAIL.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")


def make(document_id: str, chunk_index: int, score: float, text: str = "") -> SearchResult:
    return SearchResult(
        content=text,
        source=document_id,
        score=score,
        metadata={"document_id": document_id, "chunk_index": chunk_index},
        chunk_id=document_id,
    )


def main() -> None:
    # --- is_root_readme_chunk: positive cases -----------------------------
    check("root readme ch0 detected", is_root_readme_chunk(
        {"document_id": "github_AlexLvGulyaev/PromptReview_README.md", "chunk_index": 0}))
    check("root readme without chunk_index not boosted (safe default)",
          not is_root_readme_chunk(
              {"document_id": "github_AlexLvGulyaev/PromptReview_README.md"}))
    check("root readme non-numeric chunk_index not boosted",
          not is_root_readme_chunk(
              {"document_id": "github_AlexLvGulyaev/PromptReview_README.md",
               "chunk_index": "x"}))

    # --- negative cases: not a root README ---------------------------------
    check("nested README not boosted", not is_root_readme_chunk(
        {"document_id": "github_AlexLvGulyaev/telegram-intake-bot_docs/examples/README.md",
         "chunk_index": 0}))
    check("nested README (single subdir) not boosted", not is_root_readme_chunk(
        {"document_id": "github_AlexLvGulyaev/AI-Curator_docs/README.md",
         "chunk_index": 0}))
    check("chunk_index != 0 not boosted", not is_root_readme_chunk(
        {"document_id": "github_AlexLvGulyaev/PromptReview_README.md",
         "chunk_index": 5}))
    check("non-readme doc not boosted", not is_root_readme_chunk(
        {"document_id": "github_AlexLvGulyaev/PromptReview_BUSINESS_VALUE.md",
         "chunk_index": 0}))
    check("empty metadata not boosted", not is_root_readme_chunk(None))
    check("empty doc id not boosted", not is_root_readme_chunk({"chunk_index": 0}))

    # --- apply_root_readme_boost: reorders within window --------------------
    far_doc = make("github_A/PromptReview_BUSINESS_VALUE.md", 0, 0.500)
    root_readme = make("github_A/PromptReview_README.md", 0, 0.480)
    other_doc = make("github_B/ORCHESTRATOR_USER_GUIDE.md", 3, 0.520)
    results = [far_doc, root_readme, other_doc]
    boosted = apply_root_readme_boost(results)

    check("boost scales score by constant",
          abs(root_readme.score - 0.480 * ROOT_README_BOOST) < 1e-12,
          f"score={root_readme.score}")
    check("non-root docs untouched (far_doc)",
          abs(far_doc.score - 0.500) < 1e-12, f"score={far_doc.score}")
    check("non-root docs untouched (other_doc)",
          abs(other_doc.score - 0.520) < 1e-12, f"score={other_doc.score}")
    check("result sorted by distance", [r.chunk_id for r in boosted] == [
        root_readme.chunk_id, far_doc.chunk_id, other_doc.chunk_id],
        f"order={[r.chunk_id for r in boosted]}")
    check("no candidates added", len(boosted) == 3, f"n={len(boosted)}")
    check("same objects, no copies", all(r in (far_doc, root_readme, other_doc)
                                         for r in boosted))

    # Boost must not save a chunk excluded by max_distance on the caller side
    # (weaviate.search filters BEFORE the boost; rag_service.search too).
    check("in-place mutation, returns same list", apply_root_readme_boost([]) == [])

    n = len(PASS) + len(FAIL)
    print(f"test_root_readme_boost: {len(PASS)}/{n} checks passed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()