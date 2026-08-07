"""Layer D nightly comparison job — SPEC §5.2, §32.2.

Runs entirely off fixtures. What matters: the job persists what §32.2 requires
(disputed flag + a queued adjudication) and, critically, never lets a vendor
overrule Layer A.
"""

import datetime as dt

import pytest
from sitara_schemas.cache_keys import panchang_key
from sitara_schemas.facts import Tradition

from sitara_api.panchang.cache import CACHE_KIND_PANCHANG
from sitara_api.panchang.compare_job import ComparisonJob, SampleItem, next_day_sample
from sitara_api.panchang.providers.base import ProviderName
from sitara_api.panchang.providers.breaker import CircuitBreaker
from sitara_api.panchang.providers.divineapi import DivineApiProvider
from sitara_api.panchang.providers.http import VendorClient
from sitara_api.panchang.providers.prokerala import ProkeralaProvider
from tests.panchang.conftest import DELHI, MUMBAI
from tests.panchang.replay import failing_transport, load, transport_for
from tests.panchang.test_degradation import FakeAstro, layer_a_facts

pytestmark = pytest.mark.asyncio

ON = dt.date(2026, 8, 8)
ITEM = SampleItem(local_date=ON, place=MUMBAI, tradition=Tradition.AMANTA)


def divineapi(transport=None):  # noqa: ANN001, ANN201
    client = VendorClient(
        ProviderName.DIVINEAPI,
        "https://d.test",
        1.0,
        CircuitBreaker("d"),
        transport=transport or transport_for("divineapi"),
    )
    return DivineApiProvider(client, api_key="k", auth_token="t")


def prokerala(transport=None):  # noqa: ANN001, ANN201
    client = VendorClient(
        ProviderName.PROKERALA,
        "https://p.test",
        1.0,
        CircuitBreaker("p"),
        transport=transport or transport_for("prokerala"),
    )
    return ProkeralaProvider(client, client_id="id", client_secret="secret")


def skewed_prokerala(minutes: int):  # noqa: ANN201
    """Prokerala disagreeing with DivineAPI by `minutes` on the tithi end."""
    fixture = load("prokerala", "panchang")
    original = fixture["body"]["data"]["tithi"][0]["end"]
    shifted = dt.datetime.fromisoformat(original) + dt.timedelta(minutes=minutes)
    fixture["body"]["data"]["tithi"][0]["end"] = shifted.isoformat()
    return prokerala(transport_for("prokerala", ["token", "panchang"], {"panchang": fixture}))


async def seed_cache(cache) -> str:  # noqa: ANN001
    key = panchang_key(ON, MUMBAI.lat, MUMBAI.lon, Tradition.AMANTA, "divineapi")
    await cache.put(
        key,
        kind=CACHE_KIND_PANCHANG,
        local_date=ON,
        place=MUMBAI,
        tradition=Tradition.AMANTA,
        provider=ProviderName.DIVINEAPI,
        payload={"facts": []},
    )
    return key


class TestAgreement:
    async def test_agreeing_sources_queue_nothing(self, cache, db) -> None:  # noqa: ANN001
        job = ComparisonJob(cache, divineapi(), prokerala(), astro=None, db=db)
        report = await job.run([ITEM])
        assert report.sampled == 1
        assert report.disputed == 0
        assert report.adjudications_queued == 0
        assert await db.fact_adjudications.count_documents({}) == 0

    async def test_report_counts_every_comparison(self, cache, db) -> None:  # noqa: ANN001
        report = await ComparisonJob(cache, divineapi(), prokerala(), None, db).run([ITEM])
        assert report.compared == 3  # tithi + nakshatra + sunrise
        assert report.agreed == report.compared


class TestVendorDisagreement:
    async def test_beyond_tolerance_queues_an_adjudication(self, cache, db) -> None:  # noqa: ANN001
        """§32.2: 'queues Jyotish adjudication'."""
        await seed_cache(cache)
        job = ComparisonJob(cache, divineapi(), skewed_prokerala(30), None, db)
        report = await job.run([ITEM])
        assert report.disputed >= 1
        assert report.adjudications_queued >= 1
        record = await db.fact_adjudications.find_one({})
        assert record is not None
        assert record["status"] == "pending"
        assert record["served_source"] == "divineapi"
        # The fixtures already sit 60 s apart (a normal day), so a +30 min skew
        # is a 1860 s gap. The recorded delta is what the reviewer sees.
        assert record["delta_seconds"] == pytest.approx(1860, abs=1)
        assert record["tolerance_seconds"] == 120

    async def test_the_disputed_row_is_flagged_but_still_served(self, cache, db) -> None:  # noqa: ANN001
        """§32.2: 'the fact serves from DivineAPI, downgrades confidence, and
        queues adjudication' — flagged, not withdrawn."""
        key = await seed_cache(cache)
        await ComparisonJob(cache, divineapi(), skewed_prokerala(30), None, db).run([ITEM])
        doc = await cache.get(key)
        assert doc is not None
        assert doc["disputed"] is True
        assert doc["adjudication_id"] is not None

    async def test_within_tolerance_is_not_disputed(self, cache, db) -> None:  # noqa: ANN001
        await seed_cache(cache)
        report = await ComparisonJob(cache, divineapi(), skewed_prokerala(1), None, db).run([ITEM])
        assert report.disputed == 0

    async def test_both_readings_are_preserved_for_the_reviewer(self, cache, db) -> None:  # noqa: ANN001
        """A vendor's answer can change under us; the reviewer must see what we
        actually got, not a re-query (§34.2's snapshot principle)."""
        await seed_cache(cache)
        await ComparisonJob(cache, divineapi(), skewed_prokerala(30), None, db).run([ITEM])
        record = await db.fact_adjudications.find_one({})
        assert set(record["readings"]) == {"divineapi", "prokerala"}


class TestLayerAAuthority:
    async def test_two_vendors_agreeing_cannot_overrule_layer_a(self, cache, db) -> None:  # noqa: ANN001
        """The §32.2 closing line, at the job level: the boundary instants are
        chart-class, so a Layer-A/vendor gap raises a REVIEW FLAG and nothing
        is disputed or queued — our engine is already the answer."""
        job = ComparisonJob(
            cache, divineapi(), prokerala(), astro=FakeAstro(layer_a_facts()), db=db
        )
        report = await job.run([ITEM])
        assert report.review_flagged >= 1  # layer_a tithi differs from the vendors
        assert report.disputed == 0
        assert report.adjudications_queued == 0
        assert await db.fact_adjudications.count_documents({}) == 0

    async def test_a_chart_flag_does_not_mark_the_cache_disputed(self, cache, db) -> None:  # noqa: ANN001
        key = await seed_cache(cache)
        await ComparisonJob(cache, divineapi(), prokerala(), FakeAstro(layer_a_facts()), db).run(
            [ITEM]
        )
        doc = await cache.get(key)
        assert doc is not None
        assert doc["disputed"] is False


class TestResilience:
    async def test_an_unreachable_vendor_is_counted_not_fatal(self, cache, db) -> None:  # noqa: ANN001
        """A comparison run must survive a provider outage — the job exists to
        watch providers, so it cannot die when one misbehaves."""
        report = await ComparisonJob(
            cache, divineapi(failing_transport(503)), prokerala(), None, db
        ).run([ITEM])
        assert report.unreachable.get("divineapi") == 1
        assert report.sampled == 1

    async def test_all_sources_down_skips_the_item(self, cache, db) -> None:  # noqa: ANN001
        report = await ComparisonJob(
            cache,
            divineapi(failing_transport(503)),
            prokerala(failing_transport(503)),
            None,
            db,
        ).run([ITEM])
        assert report.skipped
        assert report.compared == 0

    async def test_dry_run_persists_nothing(self, cache, db) -> None:  # noqa: ANN001
        key = await seed_cache(cache)
        report = await ComparisonJob(cache, divineapi(), skewed_prokerala(30), None, db).run(
            [ITEM], dry_run=True
        )
        assert report.adjudications_queued >= 1  # counted…
        assert await db.fact_adjudications.count_documents({}) == 0  # …but not written
        doc = await cache.get(key)
        assert doc is not None and doc["disputed"] is False

    async def test_multiple_items_are_all_visited(self, cache, db) -> None:  # noqa: ANN001
        items = [ITEM, SampleItem(local_date=ON, place=DELHI)]
        report = await ComparisonJob(cache, divineapi(), prokerala(), None, db).run(items)
        assert report.sampled == 2
        assert report.compared == 6


class TestSampling:
    """Pure helpers — async only because the module-level asyncio mark applies."""

    async def test_sample_needs_no_user_records(self) -> None:
        """§34.2: panchang is global, so the unit of comparison is
        date+place+tradition. The job reads nobody's profile."""
        sample = next_day_sample([MUMBAI, DELHI], ON, limit=5)
        assert len(sample) == 2
        assert all(isinstance(item, SampleItem) for item in sample)
        assert not any(hasattr(item, "user_id") for item in sample)

    async def test_limit_is_respected(self) -> None:
        assert len(next_day_sample([MUMBAI, DELHI], ON, limit=1)) == 1
