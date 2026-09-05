"""
Deterministic portfolio registry.

Source of Truth — production table `project_cards` (NOT Chroma, NOT dialog
history, NOT hardcoded lists). Provides:

- visible cards (is_visible = true, ORDER BY display_order);
- version marker (content hash — for cache key versioning);
- query intent classification (listing / count / filtered-listing / project);
- project resolution (title/slug derived aliases, no hand-written alias tables).

The registry never duplicates project facts: cards carry only what is stored
in `project_cards`. Cards are NOT indexed as RAG documents (KB composition
stays untouched).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RegistryCard:
    """Видимая карточка проекта из project_cards."""

    slug: str
    title: str
    short_description: str
    category: str
    tags: list[str] = field(default_factory=list)
    display_order: int = 0
    external_url: Optional[str] = None

    def aliases(self) -> list[str]:
        """Механические алиасы, выведенные из данных карточки (без ручных списков)."""
        return [a for a, _ in self.alias_variants()]

    def alias_variants(self) -> list[tuple[str, int]]:
        """
        Алиасы с приоритетом: 0 = canonical title/slug, 1 = slug со пробелами,
        2 = заголовок до тире, 3 = хвост заголовка после тире
        («LoRA Fine-Tuning» у LoRA-карточки).

        Приоритет разрешает коллизии: упоминание «HR Assistant» указывает на
        базовую карточку; упоминание «LoRA Fine-Tuning» — на LoRA-карточку.
        """
        variants: dict[str, int] = {
            self._norm(self.title): 0,
            self._norm(self.slug): 0,
        }
        slug_spaced = self._norm(self.slug.replace("-", " ").replace("_", " "))
        if slug_spaced:
            variants.setdefault(slug_spaced, 1)
        # «HR Assistant — LoRA Fine-Tuning» → head «HR Assistant», tail «LoRA Fine-Tuning»
        title_parts = re.split(r"\s[—–]\s", self.title)
        if len(title_parts) > 1:
            head = title_parts[0].strip()
            tail = title_parts[-1].strip()
            if head and self._norm(head) not in variants:
                variants[self._norm(head)] = 2
            if tail and self._norm(tail) not in variants:
                variants[self._norm(tail)] = 3
        return [(a, p) for a, p in variants.items() if a]

    @staticmethod
    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s or "").lower().replace("ё", "е")
        return re.sub(r"\s+", " ", s).strip()

    @property
    def initialism(self) -> str:
        """
        Механическая аббревиатура из заглавных букв слов заголовка
        («HR Assistant» → «HRA», «Lead Qualification MVP» → «LQM»).
        """
        letters = []
        for word in re.split(r"[\s—–-]+", self.title):
            caps = "".join(ch for ch in word if ch.isupper())
            if caps:
                letters.append(caps)
        return "".join(letters).lower()


# Deterministic intent patterns (normalized query). Match the INTENT, not
# exact benchmark strings. Filter markers demote a listing question to a
# multi-project (filtered) query — answered via diversified retrieval.
LISTING_PATTERNS = [
    r"\bкакие проекты\b",
    r"\bкакие кейсы\b",
    r"\bкакие решения\b",
    r"\bперечисли\b",
    r"\bсписок (проектов|кейсов|решений)\b",
    r"\bвсе проекты\b",
    r"\bвсе кейсы\b",
    r"\bсколько (проектов|кейсов)\b",
    r"\bчто (есть|входит|представлено)\b",
    r"\bчто (ты |вы )?(умеешь|знаешь|делаешь)\b",
    r"\bполный список\b",
    r"\bпокажи (все|список)\b",
    r"\bпроекты портфолио\b",
    r"\bпортфол(ь|и)\w*\b.*\b(проект|кейс|состав)\b",
    r"\bпортфел",
    r"\bпортфолио\b",
    r"^\s*(проекты|кейсы)\s*\??\s*$",
]

# A question that names projects AND asks for a subset/relation is NOT a
# plain listing — it needs documents from several projects. Bare
# interrogatives (какой/какая/какие/чем) are NOT markers: «какие проекты
# есть в портфолио» must stay a listing, real filters have their own verbs.
FILTER_MARKERS = [
    r"\bсвязан\w*\b", r"\bиспольз\w*\b", r"\bработает с\b", r"\bпомогают\b",
    r"\bподдерживает\b", r"\bобрабатыва\w*\b", r"\bу которых\b", r"\bумеет\b",
    r"\bотлича\w*\b", r"\bсравн\w*\b", r"\bгде\b", r"\bподходящ\w*\b",
    r"\bвыбер\w*\b", r"\bкакой из\b", r"\bиз них\b",
]


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", s)


class PortfolioRegistry:
    """Реестр портфеля из project_cards с детерминированной маршрутизацией."""

    def __init__(self, db, include_hidden: bool = False):
        """
        include_hidden=False — публичный канал: видимые карточки, скрытые
        не резолвятся. include_hidden=True — канал владельца (admin
        chat-preview): скрытые карточки отдаются как обычные, чтобы владелец
        видел, как ассистент ответит после публикации (следствие §5.1 п. 9).
        """
        self._db = db
        self._include_hidden = include_hidden
        self._cards: list[RegistryCard] = []
        self._version: str = ""
        self._repos: list[str] = []
        self.load()

    def load(self) -> None:
        """Загружает карточки из project_cards (SOT)."""
        from sqlalchemy import text

        # Мета-карточка платформы ("Это Я", 022) не входит в чат-реестр
        # ни в одном режиме: её назначение — управление документацией и
        # включением в KB, а не знание ассистента о проектах.
        visibility = "" if self._include_hidden else " WHERE is_visible = true "
        visibility += " AND is_meta = false " if visibility else " WHERE is_meta = false "
        rows = self._db.execute(
            text(
                "SELECT slug, title, short_description, category, tags, "
                "display_order, external_url "
                f"FROM project_cards{visibility} "
                "ORDER BY display_order"
            )
        ).fetchall()
        cards = [
            RegistryCard(
                slug=row.slug,
                title=row.title,
                short_description=row.short_description or "",
                category=row.category or "",
                tags=list(row.tags) if row.tags else [],
                display_order=int(row.display_order or 0),
                external_url=row.external_url,
            )
            for row in rows
        ]
        self._cards = cards
        # Репозитории допущенных KB-источников (для project-scoped retrieval
        # и repo-производных аббревиатур).
        try:
            source_rows = self._db.execute(
                text(
                    "SELECT identifier FROM knowledge_sources "
                    "WHERE source_type = 'github_repo' AND is_enabled = true "
                    "AND admission_status = 'approved'"
                )
            ).fetchall()
            self._repos = [r.identifier for r in source_rows if r.identifier]
        except Exception:
            self._repos = []
        # Репозитории скрытых карточек (owner decision 29.08.2026, variant B1):
        # документы этих источников лежат в KB, но публичному чату не
        # отдаются — retrieval guard убирает их из выборки. Скрытость
        # карточки = отсутствие на витрине И отсутствие в ассистенте для
        # клиента; админ-канал (позже: /admin chat-preview) смотрит без
        # этого фильтра.
        try:
            hidden_rows = self._db.execute(
                text(
                    "SELECT ks.identifier FROM knowledge_sources ks "
                    "JOIN project_cards pc ON pc.id = ks.project_card_id "
                    "WHERE pc.is_visible = false "
                    # Мета-карточка ("Это Я", 022) — исключение из B1: она
                    # невидима на витрине, но её документы (метапак) —
                    # публичные знания для зрителя, не отложенный релиз.
                    "AND pc.is_meta = false "
                    "AND ks.source_type = 'github_repo' AND ks.is_enabled = true "
                    "AND ks.admission_status = 'approved'"
                )
            ).fetchall()
            self._hidden_repos = [r.identifier for r in hidden_rows if r.identifier]
        except Exception:
            self._hidden_repos = []
        # Скрытые карточки (owner decision 29.08.2026): названия для явного
        # отрицания «есть ли в портфолио проект X?» — вопрос существования по
        # скрытой карточке не должен деградировать в перечисление витрины.
        try:
            hidden_card_rows = self._db.execute(
                text(
                    "SELECT slug, title, display_order FROM project_cards "
                    "WHERE is_visible = false AND is_meta = false "
                    "ORDER BY display_order"
                )
            ).fetchall()
            self._hidden_cards = [
                RegistryCard(
                    slug=row.slug,
                    title=row.title,
                    short_description="",
                    category="",
                    tags=[],
                    display_order=int(row.display_order or 0),
                )
                for row in hidden_card_rows
                if row.slug not in {c.slug for c in cards}
            ]
        except Exception:
            self._hidden_cards = []
        # Уникальные аббревиатуры (initialisms) ≥2 букв: неоднозначные
        # (совпадающие у нескольких карточек) не регистрируются. Порог ≥2
        # (кейс 05.09, решение владельца): «Assistant Flow» → «af»,
        # «Retail Group» → «rg» — 2-буквенные сокращения в живых запросах
        # реальны («в кейсе AF?» не резолвился и уходил в page-fallback).
        # Ложные срабатывания отсечены границами слов в resolve/resolve_all.
        # Два механических вывода: заглавные буквы заголовка («HR Assistant»
        # → «hra») и первые буквы слов KB-репозитория («Lead-Qualification-MVP»
        # → «lqm» — заголовок даёт лишь 2 буквы).
        init_counts: dict[str, int] = {}
        card_variants: dict[str, list[tuple[str, RegistryCard]]] = {}
        for c in cards:
            seen: set[str] = set()
            ini = c.initialism
            if len(ini) >= 2:
                seen.add(ini)
            repo = self.repo_for_card(c)
            if repo:
                rini = self._repo_initialism(repo.rsplit("/", 1)[-1])
                if len(rini) >= 2:
                    seen.add(rini)
            for v in seen:
                init_counts[v] = init_counts.get(v, 0) + 1
            card_variants[c.slug] = [(v, c) for v in seen]
        self._initialisms: dict[str, RegistryCard] = {}
        for variants in card_variants.values():
            for ini, card in variants:
                if init_counts.get(ini) == 1:
                    self._initialisms.setdefault(ini, card)
        # Стабильная версия реестра: состав + порядок + описания (+ скрытые
        # карточки — они меняют ответы об отсутствующих проектах).
        payload = "\n".join(
            f"{c.display_order}|{c.slug}|{c.title}|{c.short_description}" for c in cards
        ) + "\n" + "\n".join(
            f"hidden|{c.slug}|{c.title}" for c in self._hidden_cards
        )
        self._version = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @property
    def cards(self) -> list[RegistryCard]:
        return self._cards

    @property
    def version(self) -> str:
        """Версия реестра (для версионирования кеша детерминированных ответов)."""
        return self._version

    def count(self) -> int:
        return len(self._cards)

    @property
    def repos(self) -> list[str]:
        """Допущенные KB-источники (identifier = repo в метаданных чанков)."""
        return self._repos

    @property
    def hidden_repos(self) -> list[str]:
        """Репозитории скрытых карточек — публичному retrieval не отдаются."""
        return self._hidden_repos

    def public_repos(self, repos: Optional[list[str]] = None) -> list[str]:
        """Список репо для public-поиска: без hidden-репозиториев.

        Без аргумента фильтрует self.repos; по умолчанию удаляет из
        переданного. Для админ-канала (когда появится) фильтр не
        применяется — тот список собирает сам вызывающий.
        """
        hidden = set(self._hidden_repos)
        base = repos if repos is not None else self._repos
        return [r for r in base if r not in hidden]

    def public_guard(self) -> Optional[dict]:
        """Chroma where-фильтр для не-реестровых (глобальных) поисков.

        None когда скрывать нечего — where не добавляется вовсе.
        """
        if not self._hidden_repos:
            return None
        return {"repo": {"$nin": list(self._hidden_repos)}}

    @staticmethod
    def _repo_name(identifier: str) -> str:
        return identifier.rsplit("/", 1)[-1].lower()

    def repo_for_card(self, card: RegistryCard) -> Optional[str]:
        """
        KB-репозиторий карточки: механический маппинг slug → identifier.

        HRA и HRA LoRA используют один репозиторий (slug-префикс);
        lead-qualification ↔ Lead-Qualification-MVP (repo-префикс).
        """
        for identifier in self._repos:
            repo_name = identifier.rsplit("/", 1)[-1].lower()
            if card.slug == repo_name or card.slug.startswith(repo_name + "-"):
                return identifier
        # Репозиторий является расширением slug (Lead-Qualification-MVP)
        for identifier in self._repos:
            repo_name = identifier.rsplit("/", 1)[-1].lower()
            if repo_name.startswith(card.slug + "-"):
                return identifier
        # Fallback: slug и имя репозитория совпадают без дефисов (PromptReview)
        for identifier in self._repos:
            repo_name = identifier.rsplit("/", 1)[-1].lower()
            if card.slug.replace("-", "") == repo_name.replace("-", ""):
                return identifier
        return None

    @staticmethod
    def _repo_initialism(repo_name: str) -> str:
        """Аббревиатура репозитория: первые буквы слов («Lead-Qualification-MVP» → «lqm»)."""
        return "".join(
            w[0] for w in re.split(r"[^0-9a-zA-Z]+", repo_name or "") if w
        ).lower()

    # ---------- deterministic answers ----------

    def get_by_slug(self, slug: str) -> RegistryCard | None:
        """Карточка по точному slug (для контекста страницы кейса); None — нет в реестре."""
        return next((c for c in self._cards if c.slug == slug), None)

    def render_list(self) -> str:
        """Полный список проектов: ровно текущие видимые карточки."""
        lines = [f"В портфолио {len(self._cards)} проектов:"]
        for c in self._cards:
            desc = f" — {c.short_description}" if c.short_description else ""
            lines.append(f"{c.display_order}. {c.title}{desc}")
        return "\n".join(lines)

    def render_names(self) -> str:
        """Только названия (для вопроса «сколько проектов»)."""
        return ", ".join(c.title for c in self._cards)

    def render_count(self) -> str:
        return (f"В портфолио {len(self._cards)} проектов: {self.render_names()}.")

    def render_hidden_absent(self, title: str) -> str:
        """Явное отрицание для названной скрытой карточки (класс H).

        Маркеры отказа согласованы с refusal_markers публичного eval-сета
        («не найден», «не представлен», «не входит в состав»).
        """
        return (
            f"Проект «{title}» не найден в составе портфолио — "
            f"он не представлен в списке {len(self._cards)} проектов, "
            f"входящих в состав портфолио."
        )

    # ---------- classification ----------

    def classify(self, query: str) -> str:
        """
        Детерминированная классификация маршрута.

        Returns:
            "listing"  — полный список/состав портфеля (детерминированный ответ)
            "count"    — сколько проектов (детерминированный ответ)
            "filtered" — вопрос о подмножестве проектов (диверсифицированный
                         retrieval по всем репозиториям)
            "unknown"  — обычный retrieval
        """
        q = norm_text(query)
        is_listing = any(re.search(p, q) for p in LISTING_PATTERNS)
        # Вопрос о подмножестве проектов: «какие проекты…», «у каких проектов…»
        is_plural_project_q = bool(re.search(
            r"\b(какие|каких)\s+(проект\w*|кейс\w*|решени\w*)\b", q
        ))
        if not is_listing and not is_plural_project_q:
            return "unknown"
        # Тематический квалификатор: «какие кейсы про мониторинг конкурентов»,
        # «решения для HR» — вопрос о теме, а не запрос полного списка.
        # Детерминированный listing/count по всей витрине здесь — неверный
        # ответ (кейс 02.09: вопрос про мониторинг конкурентов получал
        # дамп всех 13 проектов). Тему решают retrieval + честный ответ LLM.
        if re.search(r"\b(про|об|о|для|под)\s+[\w-]{3,}", q):
            return "filtered" if is_plural_project_q else "unknown"
        # «сколько»-вопросы
        if re.search(r"\bсколько\b", q):
            return "count"
        # Фильтр-маркеры означают вопрос о подмножестве/свойствах — не полный
        # список. Ответ строится из документов нескольких репозиториев.
        if any(re.search(m, q) for m in FILTER_MARKERS):
            return "filtered"
        if is_plural_project_q and not is_listing:
            # «У каких проектов есть веб-интерфейс?» — подмножество, не список
            return "filtered" if re.search(r"\bу каких\b|\bкакие из\b", q) else "unknown"
        # «какие проекты» + «отличается/сравни» уже отсечены маркерами.
        if re.search(r"\bпроект\w*\b|\bкейс\w*\b|\bпортфол\w*\b", q):
            return "listing"
        return "unknown"

    # ---------- resolution ----------

    @staticmethod
    def _alias_match(alias: str, q: str) -> bool:
        """Совпадение алиаса: короткие — по границам слов, длинные — подстрокой."""
        if len(alias) < 4:
            return bool(re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", q))
        return alias in q

    def resolve_hidden(self, query: str) -> Optional[str]:
        """
        Скрытая карточка, названная в запросе (поверхность узкая: только
        алиасы скрытых карточек — title/slug, без общих эвристик).

        Возвращает title для явного отрицания. На админ-канале
        (include_hidden=True) скрытые карточки попадают в _cards и здесь
        отбрасываются — предпросмотр не должен превращаться в отказ.
        """
        if not self._hidden_cards:
            return None
        q = norm_text(query)
        best: Optional[RegistryCard] = None
        best_key: tuple[int, int] | None = None
        for card in self._hidden_cards:
            for alias, pr in card.alias_variants():
                if not self._alias_match(alias, q):
                    continue
                key = (len(alias), -pr)
                if best_key is None or key > best_key:
                    best = card
                    best_key = key
        return best.title if best else None

    def resolve(self, query: str) -> Optional[RegistryCard]:
        """
        Разрешает упоминание проекта в запросе через реестр.

        Совпадение — по canonical title или slug-алиасам карточки (данные
        project_cards), с границами слов. История диалога не участвует.
        Приоритет: более длинный алиас, при равной длине — более каноничный
        (title/slug > slug со пробелами > заголовок до тире).
        """
        q = norm_text(query)
        best: Optional[RegistryCard] = None
        best_key: tuple[int, int] | None = None
        for card in self._cards:
            for alias, pr in card.alias_variants():
                if not self._alias_match(alias, q):
                    continue
                key = (len(alias), -pr)
                if best_key is None or key > best_key:
                    best = card
                    best_key = key
        # Уникальные аббревиатуры (HRA, LQM, TIB): приоритет ниже любого алиаса
        for ini, card in self._initialisms.items():
            if re.search(r"(?<!\w)" + re.escape(ini) + r"(?!\w)", q):
                key = (len(ini), -4)
                if best_key is None or key > best_key:
                    best = card
                    best_key = key
        return best

    def resolve_all(self, query: str) -> list[RegistryCard]:
        """
        Все карточки, упомянутые в запросе (для межпроектных вопросов).

        Коллизии алиасов разрешаются приоритетом: алиас принадлежит карточке
        с более каноничным совпадением. Порядок — по display_order.
        """
        q = norm_text(query)
        alias_owner: dict[str, tuple[int, RegistryCard]] = {}
        for card in self._cards:
            for alias, pr in card.alias_variants():
                if not self._alias_match(alias, q):
                    continue
                cur = alias_owner.get(alias)
                if cur is None or pr < cur[0]:
                    alias_owner[alias] = (pr, card)
        # Уникальные аббревиатуры (HRA, LQM): уникальность гарантирует владельца
        for ini, card in self._initialisms.items():
            if re.search(r"(?<!\w)" + re.escape(ini) + r"(?!\w)", q):
                alias_owner.setdefault(ini, (4, card))
        matched: dict[str, RegistryCard] = {c.slug: c for _, c in alias_owner.values()}
        return sorted(matched.values(), key=lambda c: c.display_order)