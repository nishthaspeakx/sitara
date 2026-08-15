"""The §8 degradation ladder, rung by rung.

    cache → DivineAPI → internal Layer A → Prokerala → honest decline

This is the playbook's M3 acceptance: "kill the DivineAPI key and watch the
Prokerala fallback + honest degradation". Each rung down costs confidence, and
the bottom is an envelope, never a guess (§5.3).

The one rule that must survive every rung: nothing but DivineAPI is ever
written to the cache.
"""

import datetime as dt

import pytest
from bson import ObjectId
from sitara_schemas import ErrorCode
from sitara_schemas.facts import ConfidenceState, FactSource, Tradition

from sitara_api.errors import ApiError
from sitara_api.panchang.providers.base import ProviderName
from sitara_api.panchang.providers.breaker import CircuitBreaker
from sitara_api.panchang.providers.divineapi import DivineApiProvider
from sitara_api.panchang.providers.http import VendorClient
from sitara_api.panchang.providers.prokerala import ProkeralaProvider
from sitara_api.panchang.service import CalendarLayer, PanchangService
from tests.panchang.conftest import MUMBAI
from tests.panchang.replay import failing_transport, transport_for

pytestmark = pytest.mark.asyncio

ON = dt.date(2026, 1, 1)  # matches the recorded Prokerala fixtures


class FakeAstro:
    """Stands in for sitara-astro's /v1/facts/panchang. Deterministic, and it
    keeps the ladder test independent of whether the engine container is up."""

    def __init__(self, facts: list | None = None) -> None:
        self.facts = facts
        self.calls = 0

    async def panchang(self, local_date, place, tradition, **kwargs):  # noqa: ANN001, ANN003
        self.calls += 1
        return self.facts


def layer_a_facts() -> list:
    """Real Layer-A snapshots, built the way the engine builds them."""
    from sitara_schemas.facts import (
        FactKind,
        FactMethod,
        FactPrecision,
        FactSnapshot,
        Paksha,
        TithiBoundaryValue,
        TzMethod,
    )

    # Prokerala's recorded tithi ends 16:52:45 UTC; this sits 10 minutes later,
    # deliberately beyond the §5.2 2-min tolerance so the Layer-A authority
    # tests exercise a real disagreement rather than a coincidence.
    start = dt.datetime(2025, 12, 31, 20, 18, 29, tzinfo=dt.UTC)
    return [
        FactSnapshot(
            fact_id="fact:panchang.tithi.boundary/2026-01-01/te7u-amanta@v1",
            kind=FactKind.PANCHANG_TITHI_BOUNDARY,
            value=TithiBoundaryValue(
                tithi_index=10,
                paksha=Paksha.SHUKLA,
                starts_utc=start,
                ends_utc=dt.datetime(2026, 1, 1, 17, 2, 45, tzinfo=dt.UTC),
            ),
            precision=FactPrecision(tolerance=1.0, unit="second"),
            method=FactMethod(
                tradition=Tradition.AMANTA,
                tz=TzMethod(tz="Asia/Kolkata", utc_offset_seconds=19800),
            ),
            valid_from=start,
            valid_to=dt.datetime(2026, 1, 1, 17, 2, 45, tzinfo=dt.UTC),
            engine_semver="0.1.0",
            data_revision="swe=2.10;ephe=swiss_files;tzdata=2025.2",
            source=FactSource.LAYER_A,
        )
    ]


def provider(kind: str, transport, **credentials):  # noqa: ANN001, ANN003
    if kind == "divineapi":
        client = VendorClient(
            ProviderName.DIVINEAPI, "https://d.test", 1.0, CircuitBreaker("d"), transport=transport
        )
        return DivineApiProvider(
            client,
            api_key=credentials.get("api_key", "k"),
            auth_token=credentials.get("auth_token", "t"),
        )
    client = VendorClient(
        ProviderName.PROKERALA, "https://p.test", 1.0, CircuitBreaker("p"), transport=transport
    )
    return ProkeralaProvider(
        client,
        client_id=credentials.get("client_id", "id"),
        client_secret=credentials.get("client_secret", "secret"),
    )


def service(cache, *, divineapi=None, prokerala=None, astro=None) -> PanchangService:  # noqa: ANN001
    return PanchangService(cache=cache, divineapi=divineapi, prokerala=prokerala, astro=astro)


class TestRungOneDivineApi:
    async def test_healthy_divineapi_serves_and_caches(self, cache, db) -> None:  # noqa: ANN001
        result = await service(
            cache, divineapi=provider("divineapi", transport_for("divineapi"))
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert result.sources == (FactSource.DIVINEAPI,)
        assert result.degraded is False
        assert await db.panchang_cache.count_documents({}) == 1


class TestRungTwoInternalEngine:
    async def test_missing_key_falls_through_to_layer_a(self, cache) -> None:  # noqa: ANN001
        """Killing the key must degrade, not 500."""
        astro = FakeAstro(layer_a_facts())
        result = await service(
            cache,
            divineapi=provider("divineapi", transport_for("divineapi"), api_key=None),
            astro=astro,
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert astro.calls == 1
        assert result.sources == (FactSource.LAYER_A,)
        assert result.degraded is True

    async def test_divineapi_outage_falls_through_to_layer_a(self, cache) -> None:  # noqa: ANN001
        result = await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            astro=FakeAstro(layer_a_facts()),
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert result.sources == (FactSource.LAYER_A,)

    async def test_layer_a_fallback_is_not_cached(self, cache, db) -> None:  # noqa: ANN001
        """Our engine is authoritative for astronomy but NOT the system of
        record for calendar facts (§32.2 D1) — so this rung recomputes rather
        than occupying the DivineAPI cache row."""
        await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            astro=FakeAstro(layer_a_facts()),
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert await db.panchang_cache.count_documents({}) == 0

    async def test_layer_a_is_not_a_rung_it_is_the_authority(self, cache) -> None:  # noqa: ANN001
        """Decision D1 / §32.2: Layer A is consulted INDEPENDENTLY of the
        ladder, not as a step on it. So with DivineAPI down and Prokerala up we
        get both — our authoritative astronomy AND a calendar source — rather
        than dropping one of them because the other answered first.

        Layer A is always listed first: it owns the boundary instants."""
        astro = FakeAstro(layer_a_facts())
        result = await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            prokerala=provider("prokerala", transport_for("prokerala")),
            astro=astro,
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert astro.calls == 1
        assert result.sources == (FactSource.LAYER_A, FactSource.PROKERALA)

    async def test_a_vendor_never_displaces_layer_a_boundary_facts(self, cache) -> None:  # noqa: ANN001
        """The §32.2 closing line, enforced at the serving layer: a vendor
        cannot overrule validated astronomy merely by being the source we
        happened to reach."""
        from sitara_schemas.facts import FactKind

        result = await service(
            cache,
            divineapi=provider("divineapi", transport_for("divineapi")),
            astro=FakeAstro(layer_a_facts()),
        ).panchang(ON, MUMBAI, Tradition.AMANTA)

        tithi = [f for f in result.facts if f.kind is FactKind.PANCHANG_TITHI_BOUNDARY]
        assert len(tithi) == 1
        assert tithi[0].source is FactSource.LAYER_A
        # The vendor still supplies what Layer A did not compute.
        assert FactSource.DIVINEAPI in result.sources
        nakshatra = [f for f in result.facts if f.kind is FactKind.PANCHANG_NAKSHATRA_BOUNDARY]
        assert nakshatra and nakshatra[0].source is FactSource.DIVINEAPI


class TestRungThreeProkerala:
    async def test_prokerala_serves_when_engine_cannot(self, cache) -> None:  # noqa: ANN001
        result = await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            prokerala=provider("prokerala", transport_for("prokerala")),
            astro=FakeAstro(None),  # e.g. polar night: no honest answer
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert result.sources == (FactSource.PROKERALA,)
        assert result.degraded is True

    async def test_prokerala_is_never_written_to_the_cache(self, cache, db) -> None:  # noqa: ANN001
        """Its ToS forbids it being the system of record (§5.2). This is the
        assertion that keeps us compliant."""
        await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            prokerala=provider("prokerala", transport_for("prokerala")),
            astro=FakeAstro(None),
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert await db.panchang_cache.count_documents({}) == 0

    async def test_prokerala_answers_are_downgraded(self, cache) -> None:  # noqa: ANN001
        """§32.2: it is a cross-check oracle, not a system of record — anything
        it serves is explicitly less certain, and says so."""
        result = await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            prokerala=provider("prokerala", transport_for("prokerala")),
            astro=FakeAstro(None),
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert result.confidence is ConfidenceState.APPROXIMATE
        assert "never_cached_tos" in result.notes
        assert all(f.confidence is ConfidenceState.APPROXIMATE for f in result.facts)


class TestBottomOfTheLadder:
    async def test_everything_down_declines_honestly(self, cache) -> None:  # noqa: ANN001
        """§5.3: 'unverifiable calculation → no personalised guidance'. The
        bottom rung is an envelope, never a fabricated timing."""
        with pytest.raises(ApiError) as exc:
            await service(
                cache,
                divineapi=provider("divineapi", failing_transport(503)),
                prokerala=provider("prokerala", failing_transport(503)),
                astro=FakeAstro(None),
            ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert exc.value.code is ErrorCode.ASTRO_ENGINE_UNAVAILABLE

    async def test_no_providers_configured_at_all_declines(self, cache) -> None:  # noqa: ANN001
        with pytest.raises(ApiError):
            await service(cache).panchang(ON, MUMBAI, Tradition.AMANTA)

    async def test_nothing_is_cached_on_total_failure(self, cache, db) -> None:  # noqa: ANN001
        with pytest.raises(ApiError):
            await service(
                cache,
                divineapi=provider("divineapi", failing_transport(503)),
                prokerala=provider("prokerala", failing_transport(503)),
            ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert await db.panchang_cache.count_documents({}) == 0


class TestCacheShortCircuitsTheLadder:
    async def test_a_cached_row_is_served_without_touching_a_provider(self, cache) -> None:  # noqa: ANN001
        await service(
            cache, divineapi=provider("divineapi", transport_for("divineapi"))
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        # Every provider now fails; the cache must still answer.
        result = await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            prokerala=provider("prokerala", failing_transport(503)),
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert result.cached is True
        assert result.sources == (FactSource.DIVINEAPI,)

    async def test_a_disputed_cached_row_downgrades_confidence(self, cache) -> None:  # noqa: ANN001
        """§32.2: the fact keeps serving from DivineAPI, but guidance built on
        it downgrades its confidence state (§5.4)."""
        from sitara_schemas.cache_keys import panchang_key

        await service(
            cache, divineapi=provider("divineapi", transport_for("divineapi"))
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        key = panchang_key(ON, MUMBAI.lat, MUMBAI.lon, Tradition.AMANTA, "divineapi")
        await cache.mark_disputed(key, adjudication_id=ObjectId())

        result = await service(cache).panchang(ON, MUMBAI, Tradition.AMANTA)
        assert result.disputed is True
        assert result.confidence is ConfidenceState.APPROXIMATE
        assert result.sources == (FactSource.DIVINEAPI,)  # still served
        assert all(f.confidence is ConfidenceState.APPROXIMATE for f in result.facts)


class TestTheCalendarLayerReportsWhetherItWasReachable:
    """§5.3, applied to an ABSENCE.

    Nothing here is about panchang facts — Layer A supplies those and the
    ladder above already proves it. It is about a sentence S17 renders: "No
    observance falls today." That is a calendar claim, and a calendar claim
    needs a source exactly as much as naming a festival does. Layer A is
    authoritative for the deterministic astronomy and knows nothing about the
    calendar; a tithi does not tell you it is Raksha Bandhan.

    So `festival is None` has two causes that must not read alike, and the
    service is the only thing that knows which one happened.
    """

    async def test_it_starts_unknown_rather_than_available(self, cache) -> None:  # noqa: ANN001
        """UNKNOWN is not AVAILABLE. A brief read from the store makes no
        vendor call at all, so a fresh process has genuinely not asked — and
        optimism about a question nobody put is the false negative getting back
        in through the default."""
        assert service(cache).calendar_layer is CalendarLayer.UNKNOWN

    async def test_a_live_calendar_source_reports_available(self, cache) -> None:  # noqa: ANN001
        svc = service(cache, divineapi=provider("divineapi", transport_for("divineapi")))
        await svc.panchang(ON, MUMBAI, Tradition.AMANTA)
        assert svc.calendar_layer is CalendarLayer.AVAILABLE

    async def test_prokerala_alone_still_counts_as_a_calendar_source(self, cache) -> None:  # noqa: ANN001
        """It may never be cached and never wins a dispute, but it does know
        what day it is in a tradition — which is the only question here."""
        svc = service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            prokerala=provider("prokerala", transport_for("prokerala")),
            astro=FakeAstro(None),
        )
        await svc.panchang(ON, MUMBAI, Tradition.AMANTA)
        assert svc.calendar_layer is CalendarLayer.AVAILABLE

    async def test_a_cached_row_counts_because_a_vendor_wrote_it(self, cache) -> None:  # noqa: ANN001
        await service(
            cache, divineapi=provider("divineapi", transport_for("divineapi"))
        ).panchang(ON, MUMBAI, Tradition.AMANTA)
        svc = service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            prokerala=provider("prokerala", failing_transport(503)),
        )
        await svc.panchang(ON, MUMBAI, Tradition.AMANTA)
        assert svc.calendar_layer is CalendarLayer.AVAILABLE

    async def test_both_vendors_down_reports_unavailable_even_though_layer_a_answered(  # noqa: E501
        self, cache
    ) -> None:  # noqa: ANN001
        """The case this whole class exists for, and the one the deployment is
        actually in: the panchang is complete and correct from our own engine,
        the request succeeds, and NOTHING knows whether a festival falls
        today."""
        svc = service(
            cache,
            divineapi=provider("divineapi", failing_transport(404)),
            prokerala=provider("prokerala", failing_transport(400)),
            astro=FakeAstro(layer_a_facts()),
        )
        result = await svc.panchang(ON, MUMBAI, Tradition.AMANTA)

        # The astronomy is fine — that is the point.
        assert result.sources == (FactSource.LAYER_A,)
        assert result.facts
        # The calendar is not.
        assert svc.calendar_layer is CalendarLayer.UNAVAILABLE

    async def test_no_vendor_configured_is_unavailable_not_unknown(self, cache) -> None:  # noqa: ANN001
        """A deployment with no calendar vendor at all has been asked and has
        answered — there is no source. That is knowledge, not ignorance."""
        svc = service(cache, astro=FakeAstro(layer_a_facts()))
        await svc.panchang(ON, MUMBAI, Tradition.AMANTA)
        assert svc.calendar_layer is CalendarLayer.UNAVAILABLE


class TestDayTimingsLadder:
    async def test_day_timings_fall_back_to_the_internal_engine(self, cache) -> None:  # noqa: ANN001
        """This rung is why sunrise/sunset had to land in Layer A: without it
        the ladder's internal step would be empty for day timings."""
        from sitara_schemas.facts import (
            DayTimingKind,
            DayTimingValue,
            FactKind,
            FactMethod,
            FactPrecision,
            FactSnapshot,
            TimingQuality,
        )

        start = dt.datetime(2026, 1, 1, 4, 0, tzinfo=dt.UTC)
        facts = [
            FactSnapshot(
                fact_id="fact:panchang.day_timing.rahu_kaal/2026-01-01/te7u-amanta@v1",
                kind=FactKind.PANCHANG_DAY_TIMING,
                value=DayTimingValue(
                    timing=DayTimingKind.RAHU_KAAL,
                    quality=TimingQuality.INAUSPICIOUS,
                    starts_utc=start,
                    ends_utc=start + dt.timedelta(minutes=97),
                ),
                precision=FactPrecision(tolerance=1.0, unit="second"),
                method=FactMethod(tradition=Tradition.AMANTA),
                valid_from=start,
                valid_to=start + dt.timedelta(minutes=97),
                engine_semver="0.1.0",
                data_revision="swe=2.10",
                source=FactSource.LAYER_A,
            )
        ]
        result = await service(
            cache,
            divineapi=provider("divineapi", failing_transport(503)),
            astro=FakeAstro(facts),
        ).day_timings(ON, MUMBAI, Tradition.AMANTA)
        assert result.sources == (FactSource.LAYER_A,)
        assert result.degraded is True
