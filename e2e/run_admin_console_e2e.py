#!/usr/bin/env python3
"""E2E-каркас консоли «Источники и синхронизация» (§4.6.3, human-in-the-loop).

Запуск с VPS (родная среда, python3 + playwright):
    python3 e2e/run_admin_console_e2e.py [--only E1 E2]

Принципы:
- только текстовый вывод (PASS/FAIL/SKIP) — никаких скриншотов;
- трёхсторонняя сверка: DOM консоли ↔ admin API ↔ PostgreSQL (docker exec);
- production-мутации требуют явного человеческого подтверждения (human gates);
- read-only сценарии безопасны и не изменяют данных.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "https://ai.alex-n8n.site"
CONSOLE_URL = f"{BASE}/admin/content/sources"
LEGACY_SYNC_URL = f"{BASE}/admin/content/sync"
ENV_PATH = "/opt/ai-automation-portfolio-lab/cases/ai-portfolio/.env"
DB_CONTAINER = "ai-portfolio-postgres"

RESULTS: list[tuple[str, str, str]] = []  # (scenario, status, note)


def admin_token() -> str:
    with open(ENV_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("ADMIN_API_TOKEN="):
                return line.strip().split("=", 1)[1]
    raise RuntimeError("ADMIN_API_TOKEN не найден в .env")


def api_get(path: str) -> dict:
    from urllib.request import Request, urlopen
    req = Request(f"{BASE}/api/admin/{path}",
                  headers={"Authorization": f"Bearer {admin_token()}"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def db(sql: str) -> list[list[str]]:
    out = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", "ai_portfolio", "-d", "ai_portfolio",
         "-At", "-F", "\t", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return [line.split("\t") for line in out.stdout.strip().splitlines() if line]


def check(code: str, ok: bool, note: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((code, status, note))
    print(f"[{status}] {code}{' — ' + note if note else ''}")


def md_paths(patterns) -> list[str]:
    return [p for p in (patterns or []) if p.endswith(".md")]


class Console:
    """Обёртка над playwright-страницей консоли."""

    def __init__(self, page) -> None:
        self.page = page

    def open(self, wait_ms: int = 2200) -> None:
        self.page.goto(f"{BASE}/admin/content/sources", wait_until="networkidle")
        self.page.wait_for_timeout(wait_ms)

    def open_and_select(self, identifier_part: str) -> None:
        self.open()
        self.page.fill(".logs-search", identifier_part)
        self.page.wait_for_timeout(500)
        self.page.click(".ac-source-item")
        self.page.wait_for_timeout(2200)
        self.page.fill(".logs-search", "")
        self.page.wait_for_timeout(400)

    def set_filter(self, value: str) -> None:
        self.page.select_option(".ac-filters-row select >> nth=0", value)
        self.page.wait_for_timeout(400)

    def summary_rows(self) -> dict[str, str]:
        raw = self.page.eval_on_selector_all(
            ".op-panel .op-meta-row",
            "els => els.map(e => e.innerText.replace(/\\n/g, '|'))",
        )
        rows: dict[str, str] = {}
        for item in raw:
            if "|" in item:
                k, v = item.split("|", 1)
                rows[k.strip()] = v.strip()
        return rows


# ---------------------------------------------------------------------------
# E1 — навигация и гидратация
# ---------------------------------------------------------------------------

def e1(c: Console) -> None:
    p = c.page
    c.open()
    nav = p.eval_on_selector_all(
        "nav a, aside a", "els => els.map(e => e.textContent.trim())")
    check("E1.1 «Источники и синхронизация» в меню", "Источники и синхронизация" in nav)
    p.goto(LEGACY_SYNC_URL, wait_until="networkidle")
    p.wait_for_timeout(800)
    check("E1.1 легаси /admin/content/sync редиректит", p.url.rstrip("/") == f"{BASE}/admin/content/sources")
    c.open()

    st = api_get("knowledge-base/status")
    strip = p.inner_text(".ac-strip").replace("\n", " ")
    expect = f"{st['chunks']} чанков · {st['documents']} документов"
    check("E1.2 статы стрипа == /knowledge-base/status",
          st["collection_name"] in strip and expect in strip, expect)

    sources = api_get("knowledge-base/sources")["items"]
    items_p1 = p.eval_on_selector_all(".ac-source-item", "els => els.length")
    pages_total = (len(sources) + 6) // 7
    counter = p.inner_text(".ac-pagination__counter")
    check("E1.3 пагинация: API↔UI, 7/стр, pages",
          items_p1 == min(7, len(sources)) and f"из {pages_total}" in counter,
          f"total={len(sources)}, стр1={items_p1}; {counter}")
    p.eval_on_selector_all(".logs-page-btn", "els => els[1].click()")
    p.wait_for_timeout(400)
    items_p2 = p.eval_on_selector_all(".ac-source-item", "els => els.length")
    check("E1.3 стр.2 содержит остаток", items_p2 == len(sources) - 7, f"стр2={items_p2}")
    p.eval_on_selector_all(".logs-page-btn", "els => els[0].click()")
    p.wait_for_timeout(400)

    for query, expect_frag in (("PromptReview", "Prompt Review"), ("HR Assistant", "HR Assistant")):
        p.fill(".logs-search", query)
        p.wait_for_timeout(400)
        titles = p.eval_on_selector_all(".ac-source-item__title", "els => els.map(e => e.textContent.trim())")
        check(f"E1.4 поиск «{query}»", any(expect_frag in t for t in titles), str(titles))
    p.fill(".logs-search", "")
    p.wait_for_timeout(400)

    by_title = {(s.get("display_name") or s["identifier"]): s for s in sources}
    item_texts = p.eval_on_selector_all(
        ".ac-source-item", "els => els.map(e => e.innerText.replace(/\\n/g, '|'))")
    matched, bad = 0, []
    for text in item_texts:
        lines = [ln.strip() for ln in text.split("|") if ln.strip()]
        hit = next((ln for ln in lines if ln in by_title), None)
        if hit is None:
            bad.append(f"не найдено в API: {lines}")
        else:
            matched += 1
    check("E1.5 айтемы связываются с API по названию", matched > 0 and not bad,
          "; ".join(bad) or f"{matched} свёрки")

    # E1.6 выбор айтема → гидратация трёх панелей
    c.open_and_select("PromptReview")
    src = next(s for s in sources if s["identifier"] == "AlexLvGulyaev/PromptReview")
    rows = c.summary_rows()
    ok_repo = rows.get("Репозиторий") == src["identifier"]
    check("E1.6 СВОДКА == /sources/{id} (репозиторий)", ok_repo, rows.get("Репозиторий", "нет"))
    hist_ui = p.eval_on_selector_all(".ac-history-item", "els => els.length")
    hist_db = db(f"SELECT count(*) FROM kb_admission_events WHERE source_id='{src['id']}'")[0][0]
    check("E1.6 история решений == событиям в БД", str(hist_ui) == hist_db[0] if isinstance(hist_db, str) else str(hist_ui) == hist_db,
          f"UI={hist_ui} DB={hist_db}")


# ---------------------------------------------------------------------------
# E2 — семантика статусов и корпуса
# ---------------------------------------------------------------------------

def e2(c: Console) -> None:
    sources = api_get("knowledge-base/sources")["items"]

    # Динамические базы (решение владельца 29.08): состав KB растёт легитимно
    # через сам пайплайн консоли — проверяем инварианты, а не замороженные
    # числа. Backfill-регресс: у каждого одобренного источника есть
    # approved_at; не-одобренные статусы (pending и т. п.) — легитимное
    # состояние пайплайна, фиксируются в деталях, но не проваливают проверку.
    approved = [s for s in sources if s.get("admission_status") == "approved"]
    no_ts = [s["identifier"] for s in approved if not s.get("approved_at")]
    pending = [s["identifier"] for s in sources if s.get("admission_status") != "approved"]
    check("E2.1 у всех одобренных заполнен approved_at (регресс backfill)",
          not no_ts,
          f"approved={len(approved)}/{len(sources)}; " +
          (f"не одобрены: {'; '.join(pending)}; " if pending else "") +
          ("; ".join(no_ts) or "approved_at у всех одобренных"))

    # Реестр-политика KB (решение владельца 29.08, модель «А»): источник всегда
    # привязан к карточке реестра (project_card_id, FK NOT NULL).
    unbound = [s["identifier"] for s in sources if not s.get("project_card_id")]
    check("E2.5 все источники привязаны к карточкам реестра (регресс 016)",
          not unbound, "; ".join(unbound) or f"{len(sources)}/{len(sources)}")

    mism = []
    for s in sources:
        docs = int(db(f"SELECT count(*) FROM knowledge_documents WHERE source_id='{s['id']}'")[0][0])
        rules = len(md_paths(s.get("include_patterns")))
        if docs != rules:
            mism.append(f"{s['identifier']}: docs={docs} rules={rules}")
    check(f"E2.2 правила == документам KB по всем {len(sources)} (1:1:1)", not mism,
          "; ".join(mism) or f"{len(sources)}/{len(sources)}")

    p = c.page
    pr = next(s for s in sources if s["identifier"] == "AlexLvGulyaev/PromptReview")
    rows = c.summary_rows()
    kb_val = rows.get("Состав", "")
    check("E2.3 Эксплуатация «Состав» == правилам PR (17 в KB)",
          "в KB: 17" in kb_val and "исключено" in kb_val, kb_val)
    approved_ui = rows.get("Одобрен", "")
    check("E2.3 Эксплуатация «Одобрен» заполнена", approved_ui not in ("", "ещё не одобрен"), approved_ui)

    included = p.evaluate(
        "() => [...(document.querySelectorAll('.ac-comp .ac-zone')[0]?.querySelectorAll('.ac-file') ?? [])]"
        ".map(e => e.textContent.trim())")
    pr = next(s for s in sources if s["identifier"] == "AlexLvGulyaev/PromptReview")
    rules = md_paths(pr.get("include_patterns"))
    check("E2.3 зона ВКЛЮЧЕНО == одобренному составу PR",
          len(included) == len(rules) and sorted(included) == sorted(rules),
          f"UI={len(included)} rules={len(rules)}")

    btns = p.eval_on_selector_all(
        ".ac-strip button", "els => els.map(e => ({t: e.textContent.trim(), d: e.disabled}))")
    sync_btn = next((b for b in btns if "Синхронизировать KB" in b["t"]), None)
    check("E2.4 кнопка «Синхронизировать KB» активна", sync_btn is not None and not sync_btn["d"])


# ---------------------------------------------------------------------------

def print_summary() -> int:
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\nИтог: проверок {len(RESULTS)}, PASS {len(RESULTS) - len(fails)}, FAIL {len(fails)}")
    if fails:
        for code, _, note in fails:
            print(f"  ✗ {code}: {note}")
    return 0 if not fails else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=["E1", "E2"])
    args = parser.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.add_init_script(f"localStorage.setItem('ai_portfolio_admin_token', '{admin_token()}')")
        c = Console(page)
        if "E1" in args.only:
            e1(c)
        if "E2" in args.only:
            e2(c)
        browser.close()
    return print_summary()


if __name__ == "__main__":
    import sys
    sys.exit(main())