"""S13 — the first reading (§24.4, §0.17 minute 3).

    "the first reading — moon sign + one true, specific, chart-derived
    observation phrased as a question she can feel + today's panchang in one
    warm line"

Three sentences. Every one of them is composed from a `FactSnapshot` and cites
it, and no model is involved at any point.

**Why there is no LLM here, when the morning brief has one.** §7.1's polish
stage rewrites already-true text and is guarded by the grounding validator; it
is a good trade for a brief the user reads every day. The ceremony is a
different trade. It runs ONCE, inside a moment §0.17 measures in seconds, and a
polish pass adds a model round-trip to the latency budget plus a second way to
fail (polish that misses grounding) to a screen whose whole job is to not fail.
Template composition alone is what §7.1 already calls "verified core cards" —
complete, cited, and the fastest correct thing we can do.

**Why the observation is house-keyed.** §0.17 wants an observation that is
SPECIFIC — "You tend to carry everyone's worries as your own, don't you?" — and
a single generic sentence with a graha slot is not that. So the copy is twelve
sentences, one per bhava, and only the graha is a computed slot. The catalogs
own the sentences; this module owns which one is true for this person.

**Fact selection is role-aware, and is not this module's own.** It imports the
brief composer's readers. `moon_nakshatra` returns the MOON's nakshatra and no
other body's, which is the M6 fix for a sentence that named the Moon and cited
the Sun. Re-deriving "the first nakshatra-shaped value" here would reintroduce
that defect on the first screen a user ever trusts.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence

from sitara_schemas.facts import ConfidenceState, FactSnapshot, Tradition

from sitara_api.astrology.chart_adapter import ChartEngineUnavailable, InsufficientBirthData
from sitara_api.astrology.service import AstrologyFacade, ChartBundle
from sitara_api.daily_guidance.templates import graha_house, localised_term, moon_nakshatra
from sitara_api.onboarding.types import (
    DegradeReason,
    FirstReading,
    LineId,
    ReadingLine,
    ReadingStatus,
    SourceState,
)

logger = logging.getLogger(__name__)

#: Which body the minute-3 observation is about, in order of preference.
#:
#: The Moon first because §0.17's example — carrying everyone's worries — is a
#: lunar observation, and because the Moon is the body a reading without a birth
#: time can still speak about honestly (§5.4's Moon-chart mode). Venus and the
#: Sun follow so a chart missing a lunar house assignment still yields a true
#: sentence. `graha_house` falls back to whatever assignment exists after that:
#: a true sentence about Saturn beats no observation, and both are honest.
OBSERVATION_PREFERENCE = ("moon", "venus", "sun")


def confidence_for(
    *, time_accuracy: str | None, has_chart: bool, has_panchang: bool
) -> ConfidenceState:
    """§5.4's table, applied to the ceremony.

    Read it in this order — the first true row wins — because the states are
    not independent: a user with an exact birth time and no chart is
    `tradition_general`, not `verified`, and asking about the birth time first
    would have said otherwise.
    """
    if not has_chart:
        # Panchang alone is exactly §5.4's "no chart needed / panchang-only"
        # row: true, and not a personal reading. Saying so is the point.
        return ConfidenceState.TRADITION_BASED_GENERAL if has_panchang else ConfidenceState.CANNOT_CALCULATE
    if time_accuracy == "exact":
        return ConfidenceState.VERIFIED if has_panchang else ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA
    if time_accuracy == "unknown":
        # §5.4: "date+place, no exact time" → the Moon chart, stated.
        return ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA
    # approximate and part_of_day are both "a window", and §5.4 gives a window
    # its own state rather than rounding it up to the exact one.
    return ConfidenceState.APPROXIMATE


def compose(
    *,
    chart: ChartBundle | None,
    panchang: Sequence[FactSnapshot],
    locale: str,
    time_accuracy: str | None,
    degrade_reason: DegradeReason | None = None,
    source_state: SourceState = SourceState.DEFAULT,
) -> FirstReading:
    """Build the reading from whatever facts arrived.

    Pure: no I/O, no clock, no database. Everything that can fail has already
    failed by the time this is called, and is expressed as absent facts plus a
    `degrade_reason` — which is what makes every degradation path in
    `tests/onboarding/test_reading.py` a table row rather than a mock.
    """
    natal = tuple(chart.natal) if chart else ()
    lines: list[ReadingLine] = []
    cited: list[FactSnapshot] = []

    # ── 1. the Moon, and only the Moon ──────────────────────────────────────
    found_moon = moon_nakshatra(natal)
    if found_moon is not None:
        snapshot, slug = found_moon
        name = localised_term("nakshatra", slug, locale)
        if name is None:
            # §2.4: a term with no Devanagari name is a line that cannot be
            # written in this language today, not a line to write in English.
            logger.warning("reading term missing", extra={"slug": slug, "locale": locale})
        else:
            lines.append(
                ReadingLine(
                    id=LineId.MOON_NAKSHATRA,
                    values={"nakshatra": name},
                    fact_ids=(snapshot.fact_id,),
                )
            )
            cited.append(snapshot)

    # ── 2. the observation §0.17 asks for ───────────────────────────────────
    found_house = graha_house(natal, prefer=OBSERVATION_PREFERENCE)
    if found_house is not None:
        snapshot, graha_slug, house = found_house
        graha = localised_term("graha", graha_slug, locale)
        if graha is None:
            logger.warning("reading term missing", extra={"slug": graha_slug, "locale": locale})
        else:
            lines.append(
                ReadingLine(
                    id=LineId.OBSERVATION,
                    values={"graha": graha},
                    fact_ids=(snapshot.fact_id,),
                    house=house,
                )
            )
            cited.append(snapshot)

    # ── 3. today, in one warm line ──────────────────────────────────────────
    found_tithi = _tithi(panchang)
    if found_tithi is not None:
        snapshot, tithi_index, paksha_slug = found_tithi
        paksha = localised_term("paksha", paksha_slug, locale)
        if paksha is None:
            logger.warning("reading term missing", extra={"slug": paksha_slug, "locale": locale})
        else:
            lines.append(
                ReadingLine(
                    id=LineId.PANCHANG,
                    values={"paksha": paksha, "tithi": str(tithi_index)},
                    fact_ids=(snapshot.fact_id,),
                )
            )
            cited.append(snapshot)

    has_chart = any(line.id is not LineId.PANCHANG for line in lines)
    has_panchang = any(line.id is LineId.PANCHANG for line in lines)
    confidence = confidence_for(
        time_accuracy=time_accuracy, has_chart=has_chart, has_panchang=has_panchang
    )
    # A reading can never be more confident than its thinnest half. When only
    # one calendar source answered, §5.4's Verified row — "engine parity clean"
    # — is not satisfied, whatever the birth time says. Found by the M8 live
    # run, where both vendors were down and the ceremony still claimed both.
    if source_state is not SourceState.DEFAULT and confidence is ConfidenceState.VERIFIED:
        confidence = ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA

    missing: list[str] = []
    if not has_chart:
        missing.append("natal_chart")
    if not has_panchang:
        missing.append("panchang")
    if time_accuracy == "unknown":
        missing.append("birth_time")

    if not lines:
        status = ReadingStatus.UNAVAILABLE
    elif missing or degrade_reason is not None:
        status = ReadingStatus.PARTIAL
    else:
        status = ReadingStatus.COMPLETE

    # An explicit reason from the caller (a timeout, a named outage) always
    # wins: it says WHY, where the shape of the facts can only say WHAT.
    reason = degrade_reason or _reason_from(missing, time_accuracy)

    return FirstReading(
        status=status,
        confidence=confidence,
        # With no panchang at all there is no second source to speak of, and
        # the row must not imply one.
        source_state=source_state if has_panchang else SourceState.SINGLE,
        lines=tuple(lines),
        # §34.2 — the snapshots that were CITED, embedded. Not the whole bundle:
        # a fact nothing spoke about is not part of this artefact.
        facts=tuple(cited),
        missing=tuple(missing),
        degrade_reason=reason,
    )


def _reason_from(missing: Sequence[str], time_accuracy: str | None) -> DegradeReason | None:
    """Name the most useful single reason, most actionable first.

    A missing birth time comes first because it is the only one the USER can
    do something about (§28.2's add-birth-time affordance); an outage she can
    only be told about honestly.
    """
    if "birth_time" in missing and time_accuracy == "unknown":
        return DegradeReason.INSUFFICIENT_BIRTH_DATA
    if "natal_chart" in missing:
        return DegradeReason.ENGINE_UNAVAILABLE
    if "panchang" in missing:
        return DegradeReason.PANCHANG_UNAVAILABLE
    return None


def _tithi(snapshots: Sequence[FactSnapshot]) -> tuple[FactSnapshot, int, str] | None:
    """The day's tithi. Imported shape, kept local to avoid widening the brief
    composer's public surface for one caller."""
    from sitara_schemas.facts import TithiBoundaryValue

    for snapshot in snapshots:
        value = snapshot.value
        if isinstance(value, TithiBoundaryValue):
            return snapshot, value.tithi_index, value.paksha.value
    return None


async def gather(
    *,
    facade: AstrologyFacade | None,
    panchang_service: object | None,
    user_id: str,
    local_date: dt.date,
    timezone: str,
    place: object | None,
    tradition: Tradition = Tradition.AMANTA,
) -> tuple[ChartBundle | None, tuple[FactSnapshot, ...], DegradeReason | None, SourceState]:
    """Fetch both halves, and let neither take the other down.

    The two failure modes are genuinely independent — the chart engine can be
    down on a morning when DivineAPI is fine, and a user can have no birth time
    when every provider is healthy. `CompositeBriefFacts` makes the same split
    for the same reason; the ceremony repeats the shape rather than sharing the
    class because a brief degrades to a stored artefact and this degrades to a
    screen the user is looking at right now.
    """
    chart: ChartBundle | None = None
    reason: DegradeReason | None = None

    if facade is not None:
        try:
            chart = await facade.chart_for(
                user_id,
                local_date=local_date.isoformat(),
                timezone=timezone,
                # The ceremony speaks about the natal chart only. Transits cost
                # an engine call and say nothing §0.17 asks for.
                include_transits=False,
            )
        except InsufficientBirthData:
            reason = DegradeReason.INSUFFICIENT_BIRTH_DATA
        except ChartEngineUnavailable:
            reason = DegradeReason.ENGINE_UNAVAILABLE
        except Exception:  # noqa: BLE001
            logger.exception("first reading: chart half failed")
            reason = DegradeReason.ENGINE_UNAVAILABLE

    panchang: tuple[FactSnapshot, ...] = ()
    source_state = SourceState.SINGLE
    if panchang_service is not None and place is not None:
        try:
            result = await panchang_service.panchang(  # type: ignore[attr-defined]
                local_date, place, tradition
            )
            panchang = tuple(result.facts)
            # §30.4's badge is only allowed to say "2 sources" when two
            # independent sources actually answered and agreed.
            if result.disputed:
                source_state = SourceState.DISPUTED
            elif result.degraded or len(result.sources) < 2:
                source_state = SourceState.SINGLE
            else:
                source_state = SourceState.DEFAULT
        except Exception:  # noqa: BLE001
            logger.warning("first reading: panchang half failed")
            # Only claim this as THE reason when the chart half is fine —
            # otherwise the more actionable chart reason should survive.
            if reason is None:
                reason = DegradeReason.PANCHANG_UNAVAILABLE

    return chart, panchang, reason, source_state
