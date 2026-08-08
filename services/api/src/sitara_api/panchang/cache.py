"""The §7.2 global astrology caches (§6.4 collections).

`panchang_cache` and `transit_cache` are GLOBAL and location-keyed — never
per-user (§34.2). One document serves every user in a city on a date, which is
what makes the §7.1 morning burst affordable.

Two rules are enforced here rather than trusted to callers:

1. **Prokerala is never persisted.** Its ToS requires caches to refresh within
   24h and purge on termination, so §5.2 honours it the strict way: cross-check
   calls are ephemeral and cannot become the system of record. A write attempt
   is a bug, so it raises rather than silently dropping.
2. **Only global keys.** A key carrying a user id would fan one person's data
   out to everyone sharing the row.

Because Prokerala rows never exist and Layer-A fallbacks are recomputed rather
than stored, exactly one provider (DivineAPI) ever occupies a panchang row —
which is why §6.4's `uniq (date, geo, tradition)` index holds as written even
though the §7.2 key also names a provider.
"""

import datetime as dt
from typing import Any

from sitara_schemas.cache_keys import geohash, is_global_key
from sitara_schemas.facts import Tradition

from sitara_api.db import MongoDb
from sitara_api.db.documents import stamp
from sitara_api.panchang.providers.base import ProviderName, ResolvedPlace

PANCHANG_TTL_DAYS = 90  # §7.2
MUHURAT_TTL_DAYS = 30  # §7.2
TRANSIT_TTL_DAYS = 400  # §7.2

CACHE_KIND_PANCHANG = "panchang"
CACHE_KIND_MUHURAT = "muhurat"
CACHE_KIND_FESTIVAL = "festival"


class NotCacheable(Exception):
    """Raised when something asks the cache to store what it must not.

    Loud on purpose: silently discarding the write would make a ToS breach or a
    per-user key look like a cache miss forever, and nobody would notice.
    """


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class PanchangCache:
    """Durable Mongo cache for panchang, muhurat and festival payloads."""

    def __init__(
        self,
        db: MongoDb,
        panchang_ttl_days: int = PANCHANG_TTL_DAYS,
        muhurat_ttl_days: int = MUHURAT_TTL_DAYS,
    ) -> None:
        self._db = db
        self._ttl = {
            CACHE_KIND_PANCHANG: panchang_ttl_days,
            CACHE_KIND_MUHURAT: muhurat_ttl_days,
            CACHE_KIND_FESTIVAL: panchang_ttl_days,
        }

    async def get(self, key: str) -> dict[str, Any] | None:
        doc = await self._db.panchang_cache.find_one({"_id": key})
        if doc is None:
            return None
        # Mongo's TTL reaper runs on its own schedule; never serve a row that is
        # logically expired just because the sweeper has not reached it.
        expires_at = doc.get("expires_at")
        if expires_at is not None and _ensure_utc(expires_at) <= _utcnow():
            return None
        return doc

    async def put(
        self,
        key: str,
        *,
        kind: str,
        local_date: dt.date,
        place: ResolvedPlace,
        tradition: Tradition,
        provider: ProviderName,
        payload: dict[str, Any],
        disputed: bool = False,
    ) -> dict[str, Any]:
        if provider is ProviderName.PROKERALA:
            raise NotCacheable(
                "Prokerala cross-check calls are ephemeral by ToS (§5.2) — it "
                "cannot be the system of record"
            )
        if not is_global_key(key):
            raise NotCacheable(f"refusing to cache a non-global key: {key!r}")
        if kind not in self._ttl:
            raise NotCacheable(f"unknown cache kind: {kind!r}")

        now = _utcnow()
        document = {
            "_id": key,
            "kind": kind,
            "date": local_date.isoformat(),
            "geo": geohash(place.lat, place.lon),
            "tradition": tradition.value,
            "provider": provider.value,
            "place_label": place.label,
            "place_tz": place.tz,
            "payload": payload,
            "disputed": disputed,
            "cached_at": now,
            "expires_at": now + dt.timedelta(days=self._ttl[kind]),
        }
        # §6.4 requires created_at/updated_at/schema_v on every document; the
        # collection validator enforces it.
        stamp(document, now=now)
        await self._db.panchang_cache.replace_one({"_id": key}, document, upsert=True)
        return document

    async def mark_disputed(self, key: str, adjudication_id: Any = None) -> bool:
        """§32.2: a disputed fact keeps serving from DivineAPI but is flagged,
        so guidance built on it downgrades its confidence state (§5.4)."""
        update: dict[str, Any] = {
            "disputed": True,
            "disputed_at": _utcnow(),
            "updated_at": _utcnow(),
        }
        if adjudication_id is not None:
            update["adjudication_id"] = adjudication_id
        result = await self._db.panchang_cache.update_one({"_id": key}, {"$set": update})
        return result.matched_count == 1

    async def invalidate(self, key: str) -> bool:
        result = await self._db.panchang_cache.delete_one({"_id": key})
        return result.deleted_count == 1


class TransitCache:
    """Global planetary facts per date+latitude band (§7.2, 400-day TTL)."""

    def __init__(self, db: MongoDb, ttl_days: int = TRANSIT_TTL_DAYS) -> None:
        self._db = db
        self._ttl_days = ttl_days

    async def get(self, key: str) -> dict[str, Any] | None:
        doc = await self._db.transit_cache.find_one({"_id": key})
        if doc is None:
            return None
        expires_at = doc.get("expires_at")
        if expires_at is not None and _ensure_utc(expires_at) <= _utcnow():
            return None
        return doc

    async def put(
        self, key: str, *, local_date: dt.date, band: str, engine_semver: str, payload: Any
    ) -> dict[str, Any]:
        if not is_global_key(key):
            raise NotCacheable(f"refusing to cache a non-global key: {key!r}")
        now = _utcnow()
        document = {
            "_id": key,
            "date": local_date.isoformat(),
            "band": band,
            "engine_semver": engine_semver,
            "payload": payload,
            "cached_at": now,
            "expires_at": now + dt.timedelta(days=self._ttl_days),
        }
        stamp(document, now=now)
        await self._db.transit_cache.replace_one({"_id": key}, document, upsert=True)
        return document


def _ensure_utc(value: dt.datetime) -> dt.datetime:
    """Motor returns naive UTC datetimes by default."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)
