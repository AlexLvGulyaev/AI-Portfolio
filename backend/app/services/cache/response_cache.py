"""
Сервис кеширования ответов для AI Portfolio.

Расширенная версия кеша из PEcf09 с поддержкой:
- поиска;
- сохранения;
- проверки срока жизни (TTL);
- инвалидизации;
- статистики попаданий.

Источники:
- PEcf09: cache.py (JSON-кеш с персистентностью)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class CacheStats(BaseModel):
    """Статистика кеша."""

    total_hits: int = 0
    total_misses: int = 0
    total_sets: int = 0
    total_invalidations: int = 0
    total_expired: int = 0
    cache_size: int = 0

    @property
    def hit_rate(self) -> float:
        """Процент попаданий."""
        total = self.total_hits + self.total_misses
        if total == 0:
            return 0.0
        return (self.total_hits / total) * 100


class CacheEntry(BaseModel):
    """Запись в кеше."""

    query_hash: str
    query: str
    response: str
    created_at: float
    expires_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Проверяет, истёк ли срок жизни записи."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class ResponseCache:
    """
    Полноценный сервис кеширования ответов.

    Функции:
    - поиск ответов по запросу;
    - сохранение ответов с TTL;
    - проверка срока жизни записей;
    - инвалидизация записей;
    - статистика попаданий;
    - персистентность в JSON-файл.

    Источник: PEcf09 (cache.py) — расширенная версия.
    """

    def __init__(
        self,
        cache_file: str = "data/cache/response_cache.json",
        ttl_seconds: int = 86400,  # 24 часа по умолчанию
        enable_persistence: bool = True,
    ):
        """
        Инициализация кеша.

        Args:
            cache_file: Путь к файлу для персистентности
            ttl_seconds: Время жизни записей в секундах (0 = без ограничений)
            enable_persistence: Включить сохранение в файл
        """
        self.cache_file = Path(cache_file)
        self.ttl_seconds = ttl_seconds
        self.enable_persistence = enable_persistence
        self._cache: dict[str, CacheEntry] = {}
        self._stats = CacheStats()

        # Загружаем существующий кеш
        self._load_cache()

    def _get_cache_key(self, query: str) -> str:
        """
        Создаёт уникальный хеш для запроса.

        Использует SHA-256 для стабильного хеша.
        Нормализует запрос: убирает лишние пробелы, приводит к нижнему регистру.

        Источник: PEcf09 _get_cache_key()

        Args:
            query: Пользовательский запрос

        Returns:
            Хеш-строка для использования как ключ кеша
        """
        normalized_query = " ".join(query.lower().split())
        return hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[str]:
        """
        Получает ответ из кеша, если он есть и не истёк.

        Обновляет статистику попаданий/промахов.

        Args:
            query: Пользовательский запрос

        Returns:
            Закешированный ответ или None
        """
        cache_key = self._get_cache_key(query)

        if cache_key not in self._cache:
            self._stats.total_misses += 1
            return None

        entry = self._cache[cache_key]

        # Проверяем срок жизни
        if entry.is_expired():
            self._stats.total_expired += 1
            self._stats.total_misses += 1
            del self._cache[cache_key]
            self._save_cache()
            return None

        self._stats.total_hits += 1
        return entry.response

    def set(
        self,
        query: str,
        response: str,
        metadata: Optional[dict] = None,
        ttl_seconds: Optional[int] = None,
    ) -> str:
        """
        Сохраняет ответ в кеш.

        Args:
            query: Пользовательский запрос
            response: Ответ от LLM
            metadata: Дополнительные метаданные (model, provider, etc.)
            ttl_seconds: Время жизни записи (переопределяет значение по умолчанию)

        Returns:
            Хеш запроса
        """
        cache_key = self._get_cache_key(query)
        now = time.time()

        # Определяем время жизни
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expires_at = None
        if effective_ttl > 0:
            expires_at = now + effective_ttl

        entry = CacheEntry(
            query_hash=cache_key,
            query=query,
            response=response,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        self._cache[cache_key] = entry
        self._stats.total_sets += 1
        self._stats.cache_size = len(self._cache)

        # Сохраняем кеш на диск
        self._save_cache()

        return cache_key

    def invalidate(self, query: str) -> bool:
        """
        Инвалидирует запись в кеше.

        Args:
            query: Запрос для инвалидизации

        Returns:
            True если запись была найдена и удалена
        """
        cache_key = self._get_cache_key(query)

        if cache_key in self._cache:
            del self._cache[cache_key]
            self._stats.total_invalidations += 1
            self._stats.cache_size = len(self._cache)
            self._save_cache()
            return True

        return False

    def invalidate_all(self) -> int:
        """
        Инвалидирует все записи в кеше.

        Returns:
            Количество удалённых записей
        """
        count = len(self._cache)
        self._cache.clear()
        self._stats.total_invalidations += count
        self._stats.cache_size = 0
        self._save_cache()
        return count

    def cleanup_expired(self) -> int:
        """
        Удаляет все истёкшие записи.

        Returns:
            Количество удалённых записей
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            self._stats.total_expired += len(expired_keys)
            self._stats.cache_size = len(self._cache)
            self._save_cache()

        return len(expired_keys)

    def get_stats(self) -> CacheStats:
        """
        Возвращает статистику кеша.

        Returns:
            Объект со статистикой
        """
        self._stats.cache_size = len(self._cache)
        return self._stats

    def size(self) -> int:
        """
        Возвращает количество записей в кеше.

        Returns:
            Количество записей
        """
        return len(self._cache)

    def get_entry(self, query: str) -> Optional[CacheEntry]:
        """
        Получает полную запись из кеша.

        Args:
            query: Пользовательский запрос

        Returns:
            Запись кеша или None
        """
        cache_key = self._get_cache_key(query)
        return self._cache.get(cache_key)

    def _save_cache(self) -> None:
        """
        Сохраняет кеш в JSON-файл.

        Источник: PEcf09 _save_cache()
        """
        if not self.enable_persistence:
            return

        try:
            # Создаём директорию, если её нет
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Сериализуем кеш
            data = {
                "entries": {
                    key: entry.model_dump()
                    for key, entry in self._cache.items()
                },
                "stats": self._stats.model_dump(),
            }

            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            # Не падаем при ошибке сохранения
            print(f"⚠ Ошибка сохранения кеша: {e}")

    def _load_cache(self) -> None:
        """
        Загружает кеш из JSON-файла.

        Источник: PEcf09 _load_cache()
        """
        if not self.enable_persistence:
            return

        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Загружаем записи
            entries = data.get("entries", {})
            for key, entry_data in entries.items():
                self._cache[key] = CacheEntry(**entry_data)

            # Загружаем статистику
            stats_data = data.get("stats", {})
            self._stats = CacheStats(**stats_data)
            self._stats.cache_size = len(self._cache)

        except Exception as e:
            # Не падаем при ошибке загрузки
            print(f"⚠ Ошибка загрузки кеша: {e}")
            self._cache = {}
            self._stats = CacheStats()

    def clear(self) -> None:
        """
        Очищает весь кеш.

        Источник: PEcf09 clear()
        """
        self._cache.clear()
        self._stats = CacheStats()
        self._save_cache()