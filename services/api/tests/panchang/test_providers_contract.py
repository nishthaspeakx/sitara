"""Provider contract tests — SPEC §5.2 Layer B, §8, §34.4.

Every call replays a recorded fixture; nothing here reaches a live vendor.
What is under test is OUR side of the contract: that we normalise both vendors
into one vocabulary, that a vendor's body never escapes to a caller, and that
every failure mode lands on the §8 ladder rather than crashing.
"""

import datetime as dt

import pytest
from sitara_schemas.facts import DayTimingKind, MuhuratType, TimingQuality, Tradition

from sitara_api.panchang.providers.base import (
    MuhuratQuery,
    NormalisedPanchang,
    PanchangQuery,
    ProviderName,
)
from sitara_api.panchang.providers.breaker import CircuitBreaker
from sitara_api.panchang.providers.divineapi import DivineApiProvider
from sitara_api.panchang.providers.http import (
    ProviderMisconfigured,
    ProviderUnavailable,
    VendorClient,
)
from sitara_api.panchang.providers.prokerala import ProkeralaProvider
from tests.panchang.conftest import JAIPUR, MUMBAI
from tests.panchang.replay import (
    exploding_transport,
    failing_transport,
    load,
    transport_for,
)

pytestmark = pytest.mark.asyncio

# The date the Prokerala fixtures were RECORDED on: a sandbox account rejects
# every other date (error 1004), and the fixtures pin the shape, not the day.
ON = dt.date(2026, 1, 1)
QUERY = PanchangQuery(local_date=ON, place=MUMBAI, tradition=Tradition.AMANTA)
MUHURAT_QUERY = MuhuratQuery(
    muhurat_type=MuhuratType.MARRIAGE,
    date_from=dt.date(2026, 1, 1),
    date_to=dt.date(2026, 1, 1),
    place=JAIPUR,
)


def divineapi(
    transport=None, api_key: str | None = "k", auth_token: str | None = "t"
) -> DivineApiProvider:  # noqa: ANN001
    client = VendorClient(
        ProviderName.DIVINEAPI,
        "https://divineapi.test",
        2.0,
        CircuitBreaker("divineapi"),
        transport=transport or transport_for("divineapi"),
    )
    return DivineApiProvider(client, api_key=api_key, auth_token=auth_token)


def prokerala(
    transport=None, client_id: str | None = "id", client_secret: str | None = "secret"
) -> ProkeralaProvider:  # noqa: ANN001
    client = VendorClient(
        ProviderName.PROKERALA,
        "https://prokerala.test",
        2.0,
        CircuitBreaker("prokerala"),
        transport=transport or transport_for("prokerala"),
    )
    return ProkeralaProvider(client, client_id=client_id, client_secret=client_secret)


class TestDivineApiNormalisation:
    async def test_panchang(self) -> None:
        result = await divineapi().panchang(QUERY)
        assert isinstance(result, NormalisedPanchang)
        assert result.provider is ProviderName.DIVINEAPI
        # Shukla Trayodashi / Rohini on 2026-01-01, matching the recorded
        # Prokerala answer and our own engine.
        assert result.tithi.index == 13
        assert result.nakshatra.index == 4

    async def test_local_wall_clock_is_converted_to_utc(self) -> None:
        """The fixture says 07:15:38 with no offset. That is Mumbai local time;
        07:15:38 IST is 01:45:38 UTC. Getting this wrong is the §5.3
        wrong-timezone bug, and no vendor is trusted to do it for us (§5.2)."""
        result = await divineapi().panchang(QUERY)
        assert result.sunrise_utc == dt.datetime(2026, 1, 1, 1, 45, 38, tzinfo=dt.UTC)

    async def test_day_timings(self) -> None:
        result = await divineapi().day_timings(QUERY)
        kinds = [w.timing for w in result.windows]
        assert DayTimingKind.RAHU_KAAL in kinds
        assert kinds.count(DayTimingKind.CHOGHADIYA_DAY) == 8
        assert kinds.count(DayTimingKind.CHOGHADIYA_NIGHT) == 8

    async def test_choghadiya_quality_comes_from_the_name(self) -> None:
        """Quality is ours to assign from the name — a vendor's own label would
        be untranslated English in a user's face (§2.4)."""
        windows = await divineapi().day_timings(QUERY)
        amrit = [w for w in windows.windows if w.choghadiya and w.choghadiya.value == "amrit"]
        assert amrit and all(w.quality is TimingQuality.AUSPICIOUS for w in amrit)

    async def test_muhurat(self) -> None:
        result = await divineapi().muhurat(MUHURAT_QUERY)
        assert result.muhurat_type is MuhuratType.MARRIAGE
        assert len(result.windows) == 2
        assert all(w.ends_utc > w.starts_utc for w in result.windows)


class TestProkeralaNormalisation:
    async def test_panchang_matches_divineapi_vocabulary(self) -> None:
        """The whole point of the interface: two vendors, one shape, so Layer D
        can diff them at all."""
        divine_result = await divineapi().panchang(QUERY)
        prokerala_result = await prokerala().panchang(QUERY)
        assert type(divine_result) is type(prokerala_result)
        assert prokerala_result.provider is ProviderName.PROKERALA
        assert prokerala_result.tithi.index == divine_result.tithi.index

    async def test_offset_bearing_timestamps_are_trusted(self) -> None:
        result = await prokerala().panchang(QUERY)
        assert result.sunrise_utc == dt.datetime(2026, 1, 1, 1, 45, 38, tzinfo=dt.UTC)

    async def test_token_is_fetched_once_and_reused(self) -> None:
        """Re-authenticating per call would spend the Ruby tier's request
        budget on tokens instead of facts."""
        calls: list[str] = []

        import httpx

        base = transport_for("prokerala")

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return base.handler(request)  # type: ignore[attr-defined]

        provider = prokerala(transport=httpx.MockTransport(handler))
        await provider.panchang(QUERY)
        await provider.panchang(QUERY)
        assert calls.count("/token") == 1

    async def test_day_timings_are_choghadiya_not_bands(self) -> None:
        """RECORDED behaviour: Prokerala's choghadiya endpoint returns sixteen
        choghadiya parts and NO rahu-kaal/yamaganda/gulikai bands. Those bands
        therefore have no cross-check from this vendor, and the Layer-D job
        compares what exists rather than inventing what does not (§5.3)."""
        result = await prokerala().day_timings(QUERY)
        kinds = [w.timing for w in result.windows]
        assert kinds.count(DayTimingKind.CHOGHADIYA_DAY) == 8
        assert kinds.count(DayTimingKind.CHOGHADIYA_NIGHT) == 8
        assert DayTimingKind.RAHU_KAAL not in kinds

    async def test_recorded_choghadiya_matches_our_own_rule_table(self) -> None:
        """2026-01-01 is a Thursday. Our engine's tables and Prokerala's live
        answer agree on both sequences — independent corroboration of the
        tradition tables in services/astro (§5.2 Layer C)."""
        result = await prokerala().day_timings(QUERY)
        def names(kind: DayTimingKind) -> list[str]:
            out = []
            for window in result.windows:
                if window.timing is kind:
                    assert window.choghadiya is not None  # enforced by the model
                    out.append(window.choghadiya.value)
            return out

        day, night = names(DayTimingKind.CHOGHADIYA_DAY), names(DayTimingKind.CHOGHADIYA_NIGHT)
        assert day == ["shubh", "rog", "udveg", "char", "labh", "amrit", "kaal", "shubh"]
        assert night == ["amrit", "char", "rog", "kaal", "labh", "udveg", "shubh", "amrit"]

    async def test_typed_muhurat_is_declined_not_faked(self) -> None:
        """RECORDED: Prokerala has no typed muhurat finder — the endpoint
        ignores `type` and returns generic auspicious periods. Returning Brahma
        Muhurat to someone asking about a wedding would be a fabricated fact
        wearing the right label (§5.3, §5.2's provider table)."""
        from sitara_schemas.facts import MuhuratType as MT

        typed = MuhuratQuery(
            muhurat_type=MT.MARRIAGE,
            date_from=ON, date_to=ON, place=JAIPUR,
        )
        with pytest.raises(ProviderUnavailable, match="no typed muhurat finder"):
            await prokerala().muhurat(typed)

    async def test_generic_muhurat_flattens_period_lists(self) -> None:
        generic = MuhuratQuery(
            muhurat_type=MuhuratType.GENERAL, date_from=ON, date_to=ON, place=JAIPUR
        )
        result = await prokerala().muhurat(generic)
        assert len(result.windows) >= 3  # abhijit, amrit kaal, brahma muhurat
        assert all(w.ends_utc > w.starts_utc for w in result.windows)


class TestCrossVendorAgreement:
    async def test_the_two_fixtures_agree_within_tolerance(self) -> None:
        """Sanity check on the fixtures themselves: they represent a NORMAL
        day, so the adjudicator's disputed path is exercised by deliberately
        skewed data, not by fixture drift."""
        from sitara_api.panchang.adjudicate import BOUNDARY_TOLERANCE

        a = await divineapi().panchang(QUERY)
        b = await prokerala().panchang(QUERY)
        assert abs(a.tithi.ends_utc - b.tithi.ends_utc) <= BOUNDARY_TOLERANCE
        assert abs(a.nakshatra.ends_utc - b.nakshatra.ends_utc) <= BOUNDARY_TOLERANCE


class TestFailureModes:
    async def test_missing_credentials_degrade_like_an_outage(self) -> None:
        """The playbook's acceptance: kill the key and watch the fallback. A
        missing key must not 500 — it must hand over to the §8 ladder."""
        with pytest.raises(ProviderMisconfigured):
            await divineapi(api_key=None).panchang(QUERY)
        with pytest.raises(ProviderMisconfigured):
            await prokerala(client_id=None).panchang(QUERY)

    @pytest.mark.parametrize("status", [500, 502, 503])
    async def test_upstream_5xx_is_unavailable(self, status: int) -> None:
        with pytest.raises(ProviderUnavailable):
            await divineapi(transport=failing_transport(status)).panchang(QUERY)

    async def test_connection_error_is_unavailable(self) -> None:
        with pytest.raises(ProviderUnavailable):
            await divineapi(transport=exploding_transport()).panchang(QUERY)

    async def test_rejected_credentials_are_unavailable(self) -> None:
        with pytest.raises(ProviderUnavailable):
            await divineapi(transport=failing_transport(401)).panchang(QUERY)

    async def test_unrecognised_shape_is_an_outage_not_a_fact(self) -> None:
        """A 200 we cannot fully parse must never become a served timing —
        that would be asserting a claim we cannot vouch for (§5.3)."""
        broken = load("divineapi", "panchang")
        broken["body"]["data"].pop("tithi")
        with pytest.raises(ProviderUnavailable, match="unrecognised"):
            await divineapi(
                transport=transport_for("divineapi", ["panchang"], {"panchang": broken})
            ).panchang(QUERY)

    async def test_unparseable_timestamp_is_rejected(self) -> None:
        broken = load("divineapi", "panchang")
        broken["body"]["data"]["tithi"]["end"] = "sometime next tuesday"
        with pytest.raises(ProviderUnavailable):
            await divineapi(
                transport=transport_for("divineapi", ["panchang"], {"panchang": broken})
            ).panchang(QUERY)

    async def test_repeated_failures_open_the_breaker(self) -> None:
        """§8: fail fast after 5 errors/30s."""
        provider = divineapi(transport=failing_transport(503))
        for _ in range(5):
            with pytest.raises(ProviderUnavailable):
                await provider.panchang(QUERY)
        with pytest.raises(ProviderUnavailable, match="circuit open"):
            await provider.panchang(QUERY)


class TestNoVendorLeakage:
    async def test_vendor_body_never_reaches_the_caller(self) -> None:
        """§34.4: callers see our taxonomy, never an upstream body."""
        with pytest.raises(ProviderUnavailable) as exc:
            await divineapi(transport=failing_transport(503)).panchang(QUERY)
        assert "upstream" not in str(exc.value).lower() or "error" not in str(exc.value)
        assert "{" not in str(exc.value)

    async def test_failures_do_not_log_the_request(self, caplog) -> None:  # noqa: ANN001
        """§13: a panchang request carries coordinates. Logging the body would
        put a location trace in the log stream."""
        import logging

        caplog.set_level(logging.WARNING)
        with pytest.raises(ProviderUnavailable):
            await divineapi(transport=failing_transport(503)).panchang(QUERY)
        logged = " ".join(record.getMessage() for record in caplog.records)
        assert "19.076" not in logged
        assert "72.8777" not in logged
