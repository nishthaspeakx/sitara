"""The §7.2 / §6.4 global caches.

Three things must hold or the cache becomes a liability: Prokerala is never
persisted (its ToS), no key is ever per-user (§34.2), and no row is ever shared
across cities or timezones (§30.2 acceptance).
"""

import datetime as dt

import pytest
from sitara_schemas.cache_keys import lat_band, muhurat_key, panchang_key, transits_key
from sitara_schemas.facts import MuhuratType, Tradition

from sitara_api.panchang.cache import (
    CACHE_KIND_MUHURAT,
    CACHE_KIND_PANCHANG,
    MUHURAT_TTL_DAYS,
    PANCHANG_TTL_DAYS,
    TRANSIT_TTL_DAYS,
    NotCacheable,
    PanchangCache,
    TransitCache,
)
from sitara_api.panchang.providers.base import ProviderName
from tests.panchang.conftest import DELHI, JAIPUR, MUMBAI

pytestmark = pytest.mark.asyncio

ON = dt.date(2026, 8, 8)


def key_for(place=MUMBAI, on=ON, provider="divineapi") -> str:
    return panchang_key(on, place.lat, place.lon, Tradition.AMANTA, provider)


async def store(cache: PanchangCache, place=MUMBAI, on=ON, **extra):
    return await cache.put(
        key_for(place, on),
        kind=CACHE_KIND_PANCHANG,
        local_date=on,
        place=place,
        tradition=Tradition.AMANTA,
        provider=ProviderName.DIVINEAPI,
        payload={"tithi_index": 12},
        **extra,
    )


class TestRoundTrip:
    async def test_put_then_get(self, cache: PanchangCache) -> None:
        await store(cache)
        doc = await cache.get(key_for())
        assert doc is not None
        assert doc["payload"]["tithi_index"] == 12
        assert doc["provider"] == "divineapi"

    async def test_miss_returns_none(self, cache: PanchangCache) -> None:
        assert await cache.get(key_for(on=dt.date(2099, 1, 1))) is None

    async def test_key_is_the_document_id(self, cache: PanchangCache) -> None:
        """The §7.2 key IS the identity — no second lookup path can drift."""
        doc = await store(cache)
        assert doc["_id"] == "panchang:2026-08-08:te7u:amanta:divineapi"

    async def test_rewrite_replaces_rather_than_duplicates(self, cache: PanchangCache) -> None:
        await store(cache)
        await store(cache)
        doc = await cache.get(key_for())
        assert doc is not None


class TestProkeralaIsNeverPersisted:
    """§5.2: 'its 24h-cache ToS is honoured: cross-check calls are ephemeral'.
    We honour it the strict way — Prokerala is never written at all."""

    async def test_writing_prokerala_raises(self, cache: PanchangCache) -> None:
        with pytest.raises(NotCacheable, match="ephemeral"):
            await cache.put(
                key_for(provider="prokerala"),
                kind=CACHE_KIND_PANCHANG,
                local_date=ON,
                place=MUMBAI,
                tradition=Tradition.AMANTA,
                provider=ProviderName.PROKERALA,
                payload={"tithi_index": 12},
            )

    async def test_the_refusal_is_loud_not_silent(self, cache: PanchangCache, db) -> None:
        """A silent drop would look like a permanent cache miss and nobody
        would ever notice the ToS breach was being attempted."""
        with pytest.raises(NotCacheable):
            await cache.put(
                key_for(provider="prokerala"),
                kind=CACHE_KIND_PANCHANG,
                local_date=ON,
                place=MUMBAI,
                tradition=Tradition.AMANTA,
                provider=ProviderName.PROKERALA,
                payload={},
            )
        assert await db.panchang_cache.count_documents({}) == 0


class TestNoUserKeys:
    async def test_a_user_scoped_key_is_refused(self, cache: PanchangCache) -> None:
        """§34.2: panchang is global. A per-user key in a shared collection
        would fan one person's data out to everyone reading the row."""
        with pytest.raises(NotCacheable, match="non-global"):
            await cache.put(
                "natal_chart:user123:v0.1.0:lahiri",
                kind=CACHE_KIND_PANCHANG,
                local_date=ON,
                place=MUMBAI,
                tradition=Tradition.AMANTA,
                provider=ProviderName.DIVINEAPI,
                payload={},
            )

    async def test_stored_documents_carry_no_identity(self, cache: PanchangCache) -> None:
        doc = await store(cache)
        assert not {"user_id", "subject", "firebase_uid"} & set(doc)


class TestIsolationBetweenPlaces:
    async def test_two_cities_do_not_share_a_row(self, cache: PanchangCache, db) -> None:
        """§30.2 acceptance: no cached timing ever crosses cities."""
        await store(cache, place=MUMBAI)
        await store(cache, place=DELHI)
        assert await db.panchang_cache.count_documents({}) == 2
        mumbai = await cache.get(key_for(MUMBAI))
        delhi = await cache.get(key_for(DELHI))
        assert mumbai is not None and delhi is not None
        assert mumbai["_id"] != delhi["_id"]
        assert mumbai["place_label"] != delhi["place_label"]

    async def test_traditions_do_not_share_a_row(self, cache: PanchangCache, db) -> None:
        await store(cache)
        await cache.put(
            panchang_key(ON, MUMBAI.lat, MUMBAI.lon, Tradition.PURNIMANTA, "divineapi"),
            kind=CACHE_KIND_PANCHANG,
            local_date=ON,
            place=MUMBAI,
            tradition=Tradition.PURNIMANTA,
            provider=ProviderName.DIVINEAPI,
            payload={"tithi_index": 27},
        )
        assert await db.panchang_cache.count_documents({}) == 2

    async def test_dates_do_not_share_a_row(self, cache: PanchangCache, db) -> None:
        await store(cache, on=ON)
        await store(cache, on=dt.date(2026, 8, 9))
        assert await db.panchang_cache.count_documents({}) == 2


class TestTtl:
    async def test_panchang_ttl_is_ninety_days(self, cache: PanchangCache) -> None:
        doc = await store(cache)
        span = doc["expires_at"] - doc["cached_at"]
        assert span == dt.timedelta(days=PANCHANG_TTL_DAYS)

    async def test_muhurat_ttl_is_thirty_days(self, cache: PanchangCache) -> None:
        doc = await cache.put(
            muhurat_key(MuhuratType.MARRIAGE, ON, ON, JAIPUR.lat, JAIPUR.lon),
            kind=CACHE_KIND_MUHURAT,
            local_date=ON,
            place=JAIPUR,
            tradition=Tradition.AMANTA,
            provider=ProviderName.DIVINEAPI,
            payload={"windows": []},
        )
        assert doc["expires_at"] - doc["cached_at"] == dt.timedelta(days=MUHURAT_TTL_DAYS)

    async def test_expired_row_is_not_served(self, cache: PanchangCache, db) -> None:
        """Mongo's TTL reaper runs on its own schedule — a logically expired
        row must never be served just because the sweeper has not swept."""
        await store(cache)
        await db.panchang_cache.update_one(
            {"_id": key_for()},
            {"$set": {"expires_at": dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)}},
        )
        assert await cache.get(key_for()) is None

    async def test_ttl_index_exists(self, db) -> None:
        indexes = await db.panchang_cache.index_information()
        assert any(idx.get("expireAfterSeconds") == 0 for idx in indexes.values())


class TestUniqueIndex:
    async def test_uniq_date_geo_tradition_is_scoped_to_panchang(self, db) -> None:
        """§6.4's constraint. It is partial because muhurat and festival rows
        share the collection under different §7.2 key grammars."""
        indexes = await db.panchang_cache.index_information()
        uniq = indexes["uniq_date_geo_tradition_panchang"]
        assert uniq["unique"] is True
        assert uniq["partialFilterExpression"] == {"kind": CACHE_KIND_PANCHANG}

    async def test_two_muhurat_types_coexist_for_one_day_and_place(
        self, cache: PanchangCache, db
    ) -> None:
        """The partial scope earns its keep here: without it, the second write
        would collide with the first on (date, geo, tradition)."""
        for muhurat_type in (MuhuratType.MARRIAGE, MuhuratType.VEHICLE):
            await cache.put(
                muhurat_key(muhurat_type, ON, ON, JAIPUR.lat, JAIPUR.lon),
                kind=CACHE_KIND_MUHURAT,
                local_date=ON,
                place=JAIPUR,
                tradition=Tradition.AMANTA,
                provider=ProviderName.DIVINEAPI,
                payload={"windows": []},
            )
        assert await db.panchang_cache.count_documents({"kind": CACHE_KIND_MUHURAT}) == 2


class TestDisputedFlag:
    async def test_marking_disputed(self, cache: PanchangCache) -> None:
        """§32.2: the fact keeps serving from DivineAPI, but flagged so
        guidance built on it downgrades confidence (§5.4)."""
        await store(cache)
        assert await cache.mark_disputed(key_for(), adjudication_id="adj-1") is True
        doc = await cache.get(key_for())
        assert doc is not None
        assert doc["disputed"] is True
        assert doc["adjudication_id"] == "adj-1"
        # Still served — a dispute downgrades confidence, it does not withdraw
        # the fact.
        assert doc["payload"]["tithi_index"] == 12

    async def test_marking_an_absent_key_reports_failure(self, cache: PanchangCache) -> None:
        assert await cache.mark_disputed("panchang:2099-01-01:zzzz:amanta:divineapi") is False

    async def test_rows_default_to_undisputed(self, cache: PanchangCache) -> None:
        doc = await store(cache)
        assert doc["disputed"] is False


class TestTransitCache:
    async def test_round_trip(self, transit_cache: TransitCache) -> None:
        key = transits_key(ON, MUMBAI.lat, "v0.1.0")
        await transit_cache.put(
            key, local_date=ON, band=lat_band(MUMBAI.lat), engine_semver="v0.1.0", payload=[1, 2]
        )
        doc = await transit_cache.get(key)
        assert doc is not None
        assert doc["band"] == "n10"

    async def test_ttl_is_four_hundred_days(self, transit_cache: TransitCache) -> None:
        key = transits_key(ON, MUMBAI.lat, "v0.1.0")
        doc = await transit_cache.put(
            key, local_date=ON, band="n10", engine_semver="v0.1.0", payload=[]
        )
        assert doc["expires_at"] - doc["cached_at"] == dt.timedelta(days=TRANSIT_TTL_DAYS)

    async def test_engine_version_is_part_of_the_identity(
        self, transit_cache: TransitCache, db
    ) -> None:
        """§7.2 puts engine_v in the key: an engine bump must not silently
        serve facts computed by the previous version (§32.8)."""
        for version in ("v0.1.0", "v0.2.0"):
            await transit_cache.put(
                transits_key(ON, MUMBAI.lat, version),
                local_date=ON,
                band="n10",
                engine_semver=version,
                payload=[],
            )
        assert await db.transit_cache.count_documents({}) == 2

    async def test_rejects_non_global_key(self, transit_cache: TransitCache) -> None:
        with pytest.raises(NotCacheable):
            await transit_cache.put(
                "natal_chart:user123:v0.1.0:lahiri",
                local_date=ON,
                band="n10",
                engine_semver="v0.1.0",
                payload=[],
            )
