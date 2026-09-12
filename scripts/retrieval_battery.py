#!/usr/bin/env python3
"""Поведенческая батарея project_scoped retrieval.

Прогоняет эталонные вопросы через ЖИВОЙ retrieval-контур (production
Chroma) с эмуляцией живой project_scoped-ветки оркестратора: выбор
запроса (ChatOrchestrator._scoped_query_mode), fetch max(top_k*3, 12),
дедуп по документу (_dedup_by_doc), обрезка до top_k.

Правило поведенческих проверок (урок 12.09.2026): юнит-тесты проверяют
механику, не качество выдачи — любое изменение, затрагивающее retrieval,
оркестратор или промпт, прогоняет эту батарею ДО коммита.

Ожидания — состав выдачи, зафиксированный на базлайне 12.09.2026.
Корпус живой (синхронизация под контролем admission gate): при
изменении состава документов Assistant Flow / Retail-Group ожидания
могут потребовать актуализации — об этом батарея скажет честно (FAIL).

Запуск в контейнере backend:
    docker exec -i ai-portfolio-backend python - < scripts/retrieval_battery.py
Опционально: --patched /tmp/chat_orchestrator_new.py — проверка новой
версии модуля без рестарта сервиса.
"""
import argparse
import importlib.util
import json
import sys

sys.path.insert(0, "/app")

from app.services.rag.retrieval_manager import get_retrieval_manager  # noqa: E402


def _load_orchestrator_cls(patched_path: str | None):
    if not patched_path:
        from app.services.chat_orchestrator import ChatOrchestrator

        return ChatOrchestrator, "установленный код контейнера"
    spec = importlib.util.spec_from_file_location(
        "chat_orchestrator_patched", patched_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ChatOrchestrator, f"патченный файл {patched_path}"


# slug страницы | репозиторий | вопрос | режим | проверка выдачи
CASES = [
    {
        "name": "AF: самодостаточный вопрос про базу знаний",
        "title": "Assistant Flow",
        "repo": "AlexLvGulyaev/Assistant-Flow",
        "query": "Как устроена база знаний?",
        "expect_mode": "bare",
        "check": "kb_sections",
    },
    {
        "name": "AF: самодостаточный вопрос про технологии",
        "title": "Assistant Flow",
        "repo": "AlexLvGulyaev/Assistant-Flow",
        "query": "Какие технологии использованы?",
        "expect_mode": "bare",
        "check": "stack_section",
    },
    {
        "name": "HRA: мета-вопрос о метриках (кейс 10.09, не должен сломаться)",
        "title": "HR Assistant — LoRA Fine-Tuning",
        "repo": "AlexLvGulyaev/HR-Assistant",
        "query": "Какие результаты и метрики?",
        "expect_mode": "topic_enriched",
        "check": "nonempty",
    },
    {
        "name": "RG: демонстратив «этот кейс» (кейс 05.09, не должен сломаться)",
        "title": "Retail Group",
        "repo": "AlexLvGulyaev/Retail-Group",
        "query": "Как устроен этот кейс?",
        "expect_mode": "topic_enriched",
        "check": "nonempty",
    },
    {
        "name": "Глобальный поиск (главная): тот же вопрос про базу знаний",
        "title": None,
        "repo": None,
        "query": "Как устроена база знаний?",
        "expect_mode": "global",
        "check": "nonempty_global",
    },
]

KB_SECTIONS = {"docs/ADMIN_INDEXING.md", "docs/DEMO_SCENARIOS.md"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patched", default=None,
                    help="файл с новой версией chat_orchestrator.py")
    args = ap.parse_args()

    Orch, src = _load_orchestrator_cls(args.patched)
    has_mode_cls = hasattr(Orch, "_scoped_query_mode")
    tuning = get_retrieval_manager().effective_tuning()
    top_k = int(tuning["rag_top_k"])
    fetch_k = max(top_k * 3, 12)

    backend = get_retrieval_manager().get_backend()
    print(f"Источник решения: {src}; _scoped_query_mode: "
          f"{'есть' if has_mode_cls else 'НЕТ (старый код — обогащение безусловно)'}")
    print(f"runtime tuning: top_k={top_k}, fetch={fetch_k}\n")

    failures = []
    for case in CASES:
        q = case["query"]
        if case["expect_mode"] == "global" or not has_mode_cls:
            mode = "global" if case["expect_mode"] == "global" else "topic_enriched (legacy)"
        else:
            mode = Orch._scoped_query_mode(q)

        search_query = q
        if case["expect_mode"] != "global":
            if mode == "topic_enriched" or not has_mode_cls:
                search_query = f"{case['title']} | {q}"
            from app.services.chat_orchestrator import METRIC_QUERY_RE, METRIC_QUERY_HINT
            if METRIC_QUERY_RE.search(q):
                search_query = f"{search_query}{METRIC_QUERY_HINT}"

        where = {"repo": {"$eq": case["repo"]}} if case["repo"] else None
        results = backend.search(search_query, top_k=fetch_k, where=where)
        results = Orch._dedup_by_doc(results)[:top_k]

        docs = []
        for r in results:
            m = getattr(r, "metadata", {}) or {}
            txt = (getattr(r, "content", "") or "")[:90].replace("\n", " ")
            docs.append((m.get("path", "?"), txt))

        ok = True
        why = ""
        if case["expect_mode"] == "global":
            if not results:
                ok, why = False, "глобальный поиск пуст"
        elif ("legacy" in mode or "topic_enriched" in mode) and case["expect_mode"] == "topic_enriched":
            pass  # старый код: обогащение безусловно — режим совпадает с ожиданием
        elif mode != case["expect_mode"]:
            ok, why = False, f"режим {mode} != ожидаемого {case['expect_mode']}"
        elif not results:
            ok, why = False, "выдача пуста"
        elif case["check"] == "kb_sections":
            top_docs = [d for d, _ in docs[:3]]
            if not any(d in KB_SECTIONS for d in top_docs):
                ok = False
                why = (f"KB-разделы ({sorted(KB_SECTIONS)}) не в top-3; "
                       f"top-3: {top_docs}")
        elif case["check"] == "stack_section":
            stack = any(d == "README.md" and "Технологический стек" in t
                        for d, t in docs[:3])
            if not stack:
                ok = False
                why = f"раздел «Технологический стек» не в top-3; top-3: {[d for d, _ in docs[:3]]}"

        status = "PASS" if ok else "FAIL"
        if not ok:
            failures.append(case["name"])
        print(f"[{status}] {case['name']}")
        print(f"      режим: {mode}; запрос: {search_query!r}")
        for i, (d, t) in enumerate(docs, 1):
            print(f"      {i}. {d} :: {t}")
        if why:
            print(f"      причина FAIL: {why}")
        print()

    print("=" * 60)
    if failures:
        print(f"ИТОГ: {len(failures)} FAIL из {len(CASES)}: {failures}")
        return 1
    print(f"ИТОГ: {len(CASES)}/{len(CASES)} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
