"""
Geo-обогащение посетителей по IP (mmdb-базы DB-IP Lite).

Базы (volume backend/data/geoip, в git не входят — DEPLOYMENT_GUIDE):
- country.mmdb — DB-IP Country Lite (CC BY 4.0, атрибуция db-ip.com);
- city.mmdb   — DB-IP City Lite (опционально; отсутствие файла —
  graceful fallback: город None).

Отдельные readers: городская база тяжёлая (~130 МБ), страна — нет;
если города нет, страна всё равно работает. Файл отсутствует или
битый — сервис отвечает None (гео-функции в консоли просто пустые,
канал не падает).
"""

from __future__ import annotations

import ipaddress
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

GEOIP_DIR = os.environ.get("GEOIP_DIR", "/app/data/geoip")
_COUNTRY_PATH = os.path.join(GEOIP_DIR, "country.mmdb")
_CITY_PATH = os.path.join(GEOIP_DIR, "city.mmdb")

_readers: dict[str, Any] = {}
_failed: set[str] = set()


def _reader(kind: str, path: str) -> Any:
    if kind in _readers:
        return _readers[kind]
    if kind in _failed:
        return None
    if not os.path.exists(path):
        _failed.add(kind)
        logger.warning("GeoIP: %s не найден (%s) — гео-обогащение отключено", kind, path)
        return None
    try:
        import maxminddb

        _readers[kind] = maxminddb.open_database(path)
    except Exception:  # noqa: BLE001 — битая база не должна ронять канал
        _failed.add(kind)
        logger.exception("GeoIP: не удалось открыть %s", path)
        return None
    return _readers[kind]


def _is_routable(ip: str) -> bool:
    """Гео-поиск имеет смысл только для публичных адресов."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def resolve_geo(ip: str | None) -> dict[str, Any] | None:
    """Страна + город по IP; None — если ip непубличный или баз нет.

    Страна берётся из country.mmdb (быстрая), город — из city.mmdb
    (может отсутствовать). Название страны — русское из базы (names.ru,
    fallback en); флаг считается на фронте из ISO-кода.
    """
    if not ip or not _is_routable(ip):
        return None
    country_reader = _reader("country", _COUNTRY_PATH)
    if country_reader is None:
        return None
    try:
        rec = country_reader.get(ip) or {}
        country = rec.get("country") or {}
        code = country.get("iso_code")
        if not code:
            return None
    except Exception:  # noqa: BLE001 — мусорный IP / битая запись
        return None

    names = country.get("names") or {}
    result: dict[str, Any] = {
        "country_code": code,
        "country": names.get("ru") or names.get("en"),
        "city": None,
    }
    city_reader = _reader("city", _CITY_PATH)
    if city_reader is not None:
        try:
            rec = city_reader.get(ip) or {}
            city = (rec.get("city") or {}).get("names") or {}
            result["city"] = city.get("ru") or city.get("en")
        except Exception:  # noqa: BLE001
            pass
    return result