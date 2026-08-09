"""S13's composer — the reading, and every way it is allowed to fall short.

The composer is pure, so every degradation path here is a table row rather than
a mock: the failures have already happened by the time `compose` is called and
arrive as absent facts plus a named reason.

The first test is the one that matters most. CL-009's defect was a sentence that
named the Moon while citing the SUN's nakshatra — every gate green, the id in
the served payload, the name matching the fact it named, and the sentence false.
It reached a live run because the fixtures carried exactly one nakshatra fact.
These fixtures carry the Sun's FIRST, deliberately, so a composer that took "the
first nakshatra-shaped value" would fail here rather than in front of a user on
the first screen she is asked to trust.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest
from sitara_schemas.facts import (
    ConfidenceState,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    HouseAssignmentValue,
    Nakshatra,
    NakshatraValue,
    Paksha,
    TithiBoundaryValue,
    build_fact_id,
)

from sitara_api.astrology.service import ChartBundle
from sitara_api.onboarding import reading
from sitara_api.onboarding.types import DegradeReason, LineId, ReadingStatus, SourceState

USER_ID = "6a70000000000000000000a1"
DAY_START = dt.datetime(2026, 8, 11, 18, 30, tzinfo=dt.UTC)
DAY_END = dt.datetime(2026, 8, 12, 18, 29, tzinfo=dt.UTC)

CATALOGS = pathlib.Path(__file__).resolve().parents[4] / "packages/i18n/messages"


def _snapshot(kind: FactKind, value, path: str) -> FactSnapshot:  # noqa: ANN001
    return FactSnapshot(
        fact_id=build_fact_id(path, "natal", USER_ID, 1),
        kind=kind,
        value=value,
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(ayanamsa="lahiri"),
        valid_from=DAY_START,
        valid_to=None,
        engine_semver="0.1.0",
        data_revision="test",
    )


def sun_nakshatra() -> FactSnapshot:
    """Emitted FIRST by the engine, exactly as it is in production."""
    return _snapshot(
        FactKind.NATAL_GRAHA_NAKSHATRA,
        NakshatraValue(
            graha=Graha.SUN, nakshatra=Nakshatra.PURVA_BHADRAPADA, nakshatra_index=25, pada=1
        ),
        "natal.sun.nakshatra",
    )


def moon_nakshatra() -> FactSnapshot:
    return _snapshot(
        FactKind.NATAL_GRAHA_NAKSHATRA,
        NakshatraValue(graha=Graha.MOON, nakshatra=Nakshatra.ROHINI, nakshatra_index=4, pada=2),
        "natal.moon.nakshatra",
    )


def moon_house(house: int = 7) -> FactSnapshot:
    return _snapshot(
        FactKind.NATAL_GRAHA_HOUSE,
        HouseAssignmentValue(graha=Graha.MOON, whole_sign_house=house, bhava=house),
        "natal.moon.house",
    )


def saturn_house(house: int = 3) -> FactSnapshot:
    return _snapshot(
        FactKind.NATAL_GRAHA_HOUSE,
        HouseAssignmentValue(graha=Graha.SATURN, whole_sign_house=house, bhava=house),
        "natal.saturn.house",
    )


def tithi() -> FactSnapshot:
    return FactSnapshot(
        fact_id=build_fact_id("panchang.tithi.boundary", "2026-08-12", "global", 1),
        kind=FactKind.PANCHANG_TITHI_BOUNDARY,
        value=TithiBoundaryValue(
            starts_utc=DAY_START, ends_utc=DAY_END, tithi_index=5, paksha=Paksha.SHUKLA
        ),
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(ayanamsa="lahiri"),
        valid_from=DAY_START,
        valid_to=DAY_END,
        engine_semver="0.1.0",
        data_revision="test",
    )


def chart(*facts: FactSnapshot) -> ChartBundle:
    return ChartBundle(natal=facts)


def line(result, line_id: LineId):  # noqa: ANN001, ANN201
    """The composed line, or None when the composer declined to write it."""
    return next((line for line in result.lines if line.id is line_id), None)


def required_line(result, line_id: LineId):  # noqa: ANN001, ANN201
    """The line, asserted present — so a test reading `.house` off it says WHICH
    line was missing rather than failing on an attribute of None."""
    found = line(result, line_id)
    assert found is not None, f"expected a {line_id.value} line"
    return found


# ---------------------------------------------------------------------------
# The CL-009 shape
# ---------------------------------------------------------------------------


def test_the_moon_line_is_the_moons_nakshatra_when_the_sun_arrives_first() -> None:
    result = reading.compose(
        chart=chart(sun_nakshatra(), moon_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
    )
    moon_line = line(result, LineId.MOON_NAKSHATRA)
    assert moon_line is not None
    # Rohini is the MOON's. Purva Bhadrapada is the Sun's, and a reading that
    # printed it here would be false while citing a real fact in the payload.
    assert moon_line.values["nakshatra"] == "Rohini"
    assert moon_line.fact_ids == (moon_nakshatra().fact_id,)


def test_a_chart_with_only_the_suns_nakshatra_writes_no_moon_line() -> None:
    """Declining is the correct answer. §5.3 does not permit the nearest fact."""
    result = reading.compose(
        chart=chart(sun_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
    )
    assert line(result, LineId.MOON_NAKSHATRA) is None
    # …and the reading still stands on what it does have.
    assert line(result, LineId.OBSERVATION) is not None


def test_the_observation_prefers_the_moon_but_will_speak_about_saturn() -> None:
    with_moon = reading.compose(
        chart=chart(saturn_house(3), moon_house(7)),
        panchang=[],
        locale="en",
        time_accuracy="exact",
    )
    assert required_line(with_moon, LineId.OBSERVATION).house == 7

    # No lunar house assignment: a true sentence about Saturn beats no
    # observation, and both are honest.
    saturn_only = reading.compose(
        chart=chart(saturn_house(3)), panchang=[], locale="en", time_accuracy="exact"
    )
    assert required_line(saturn_only, LineId.OBSERVATION).house == 3


# ---------------------------------------------------------------------------
# Cite-or-die
# ---------------------------------------------------------------------------


def test_every_line_cites_at_least_one_fact_and_every_cited_fact_is_embedded() -> None:
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
    )
    assert result.lines
    embedded = {f.fact_id for f in result.facts}
    for composed in result.lines:
        assert composed.fact_ids, f"{composed.id} carries a claim with no citation"
        # §34.2: the snapshot is embedded at generation, not referenced by id
        # into a collection that does not exist.
        for fact_id in composed.fact_ids:
            assert fact_id in embedded


# ---------------------------------------------------------------------------
# §5.4's confidence table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("time_accuracy", "has_chart", "has_panchang", "expected"),
    [
        ("exact", True, True, ConfidenceState.VERIFIED),
        ("exact", True, False, ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA),
        ("unknown", True, True, ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA),
        ("approximate", True, True, ConfidenceState.APPROXIMATE),
        ("part_of_day", True, True, ConfidenceState.APPROXIMATE),
        ("exact", False, True, ConfidenceState.TRADITION_BASED_GENERAL),
        ("exact", False, False, ConfidenceState.CANNOT_CALCULATE),
    ],
)
def test_confidence_follows_the_spec_table(
    time_accuracy: str, has_chart: bool, has_panchang: bool, expected: ConfidenceState
) -> None:
    assert (
        reading.confidence_for(
            time_accuracy=time_accuracy, has_chart=has_chart, has_panchang=has_panchang
        )
        is expected
    )


def test_an_exact_birth_time_with_no_chart_is_not_verified() -> None:
    """The states are not independent, and reading the table in the wrong order
    gets this one wrong: knowing the birth time exactly says nothing about
    whether a chart was computed."""
    result = reading.compose(
        chart=None, panchang=[tithi()], locale="en", time_accuracy="exact"
    )
    assert result.confidence is ConfidenceState.TRADITION_BASED_GENERAL


# ---------------------------------------------------------------------------
# The degradation ladder
# ---------------------------------------------------------------------------


def test_no_birth_time_reads_the_moon_chart_and_says_so() -> None:
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale="en",
        time_accuracy="unknown",
    )
    assert result.status is ReadingStatus.PARTIAL
    assert "birth_time" in result.missing
    assert result.degrade_reason is DegradeReason.INSUFFICIENT_BIRTH_DATA
    assert result.confidence is ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA
    # The Moon lines survive — that IS the Moon-chart mode.
    assert line(result, LineId.MOON_NAKSHATRA) is not None


def test_engine_down_leaves_a_panchang_only_reading() -> None:
    result = reading.compose(
        chart=None,
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
        degrade_reason=DegradeReason.ENGINE_UNAVAILABLE,
    )
    assert result.status is ReadingStatus.PARTIAL
    assert [composed.id for composed in result.lines] == [LineId.PANCHANG]
    assert result.degrade_reason is DegradeReason.ENGINE_UNAVAILABLE


def test_panchang_down_leaves_the_chart_lines_and_invents_no_timings() -> None:
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[],
        locale="en",
        time_accuracy="exact",
    )
    assert line(result, LineId.PANCHANG) is None
    assert "panchang" in result.missing
    assert result.degrade_reason is DegradeReason.PANCHANG_UNAVAILABLE


def test_nothing_at_all_is_unavailable_rather_than_an_empty_complete() -> None:
    result = reading.compose(chart=None, panchang=[], locale="en", time_accuracy=None)
    assert result.status is ReadingStatus.UNAVAILABLE
    assert result.lines == ()
    assert result.confidence is ConfidenceState.CANNOT_CALCULATE


def test_an_explicit_timeout_outranks_a_reason_inferred_from_shape() -> None:
    """A slow engine and a down engine leave the same empty chart. Only the
    caller knows which happened, so an explicit reason always wins."""
    result = reading.compose(
        chart=None,
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
        degrade_reason=DegradeReason.TIMEOUT,
    )
    assert result.degrade_reason is DegradeReason.TIMEOUT


# ---------------------------------------------------------------------------
# §2.4 — the copy exists, in every launch locale
# ---------------------------------------------------------------------------


def _catalog(locale: str) -> dict:
    return json.loads((CATALOGS / f"{locale}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("locale", ["en", "hi", "hi-Latn"])
def test_every_degrade_reason_has_a_sentence_in_every_locale(locale: str) -> None:
    """A reason with no copy is a blank space on the most important screen."""
    degraded = _catalog(locale)["start"]["reading"]["degraded"]
    assert set(degraded) == {r.value for r in DegradeReason}
    for text in degraded.values():
        assert text.strip()


@pytest.mark.parametrize("locale", ["en", "hi", "hi-Latn"])
def test_every_house_has_an_observation_in_every_locale(locale: str) -> None:
    """`graha_house` can return any of the twelve, so all twelve must be
    writable — a chart landing on house 11 must not render an empty line."""
    observations = _catalog(locale)["start"]["reading"]["observation"]
    assert {int(k) for k in observations} == set(range(1, 13))
    for text in observations.values():
        assert "{graha}" in text, "the graha is the computed slot; it must appear"


@pytest.mark.parametrize("locale", ["en", "hi", "hi-Latn"])
def test_the_composer_renders_terms_in_the_asked_for_locale(locale: str) -> None:
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale=locale,
        time_accuracy="exact",
    )
    nakshatra = required_line(result, LineId.MOON_NAKSHATRA).values["nakshatra"]
    expected = _catalog(locale)["terms"]["nakshatra"]["rohini"]
    # §2.4: no silent English fallback — the Devanagari name, or no line.
    assert nakshatra == expected


# ---------------------------------------------------------------------------
# §30.4 — the source row is a CLAIM, and it was false
# ---------------------------------------------------------------------------
# Found by the M8 live acceptance run, not by this suite: both panchang vendors
# were unreachable, the calendar layer came from Layer A alone, and the ceremony
# still rendered "computed from your chart · verified against 2 sources ✓" with
# a `verified` chip beside it. Every fact was real and every citation resolved.
# Only a human looking at the served payload beside the sentence could see it.


def test_one_source_may_not_claim_two() -> None:
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
        source_state=SourceState.SINGLE,
    )
    assert result.source_state is SourceState.SINGLE
    # …and a reading is never more confident than its thinnest half: §5.4's
    # Verified row wants "engine parity clean", which one source cannot show.
    assert result.confidence is ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA


def test_two_agreeing_sources_may_claim_two() -> None:
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
        source_state=SourceState.DEFAULT,
    )
    assert result.source_state is SourceState.DEFAULT
    assert result.confidence is ConfidenceState.VERIFIED


def test_disputed_sources_are_carried_through_rather_than_smoothed_over() -> None:
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[tithi()],
        locale="en",
        time_accuracy="exact",
        source_state=SourceState.DISPUTED,
    )
    assert result.source_state is SourceState.DISPUTED
    assert result.confidence is not ConfidenceState.VERIFIED


def test_no_panchang_at_all_cannot_claim_a_second_source() -> None:
    """There is no second source to have agreed with, whatever the caller says."""
    result = reading.compose(
        chart=chart(moon_nakshatra(), moon_house()),
        panchang=[],
        locale="en",
        time_accuracy="exact",
        source_state=SourceState.DEFAULT,
    )
    assert result.source_state is SourceState.SINGLE
