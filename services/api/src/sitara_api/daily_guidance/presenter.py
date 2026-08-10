"""`Brief` → §28.2's wire payload.

Pure over its inputs, and that is the point: everything here is a rendering
decision, and rendering decisions are the ones worth being able to test without
a database, a clock or a network.

Three rules govern the file.

**Fact IDs stop here.** §30.4 keeps them internal — "fact-IDs remain internal
(logs/admin) and never render to users" — so the payload has no field one could
travel in (`packages/schemas/src/today.json`, and a parity test asserts the
absence). What crosses instead is what §30.4 actually asks for: three layers of
plain language. The markers are stripped from every sentence with the chat
pipeline's own `strip_citations`, so there is one definition of "stripped" in
the service rather than a second regex here.

**Confidence is per module, not per screen.** §5.4's state is a property of the
evidence, and a brief can hold a verified panchang line beside a
tradition-general one. Taking the brief's overall state for every card would
overstate the weak ones and understate the strong ones; both are dishonest, and
the understating kind is the one nobody reports.

**A detail line is rendered from the snapshot or omitted.** §30.4's expander is
"nakshatra/tithi/transit specifics in readable terms", which means reading the
value — never paraphrasing the sentence above it, which would be a summary
dressed as a source.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sitara_schemas.facts import (
    BhagyankValue,
    ConfidenceState,
    DayTimingValue,
    FactSnapshot,
    FestivalObservanceValue,
    HouseAssignmentValue,
    MoolankValue,
    MuhuratWindowValue,
    NakshatraBoundaryValue,
    NakshatraValue,
    TithiBoundaryValue,
)
from sitara_schemas.today import (
    TimingQuality,
    TodayModule,
    TodayPanchangEntry,
    TodayTarasLine,
    TodayTiming,
    TodayTrust,
)

from sitara_api.chat_orchestration.grounding import strip_citations
from sitara_api.daily_guidance.templates import TarasLine, localised_term
from sitara_api.daily_guidance.types import Brief, ComposedModule
from sitara_api.localisation import MissingString, resolve

logger = logging.getLogger(__name__)

#: §5.4's states from strongest to weakest. A module's state is the WEAKEST of
#: the snapshots it stands on: a sentence is only as sound as its softest
#: source, and rounding up is how "approximate" quietly becomes "verified".
_STRENGTH: tuple[ConfidenceState, ...] = (
    ConfidenceState.VERIFIED,
    ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA,
    ConfidenceState.APPROXIMATE,
    ConfidenceState.TRADITION_BASED_GENERAL,
    ConfidenceState.CANNOT_CALCULATE,
)


def module_confidence(
    module: ComposedModule, fallback: ConfidenceState
) -> ConfidenceState:
    declared = [s.confidence for s in module.snapshots if s.confidence is not None]
    if not declared:
        return fallback
    return max(declared, key=_STRENGTH.index)


# ---------------------------------------------------------------------------
# §30.4's three layers
# ---------------------------------------------------------------------------


def _sources_line(state: ConfidenceState, locale: str) -> str:
    """VerifiedSourceRow's sentence, from the confidence state.

    **Not from the snapshot count.** The first cut read `len(module.snapshots)`,
    and the recorded fixtures caught what that produces: a Trust Sheet whose
    plain line said "checked against two sources" directly above a source row
    saying "one source available today". Two sentences, one card, contradicting
    each other — because a module's snapshot count is how many DIFFERENT facts
    it stands on (a tithi and a nakshatra), not how many sources agreed on one.

    Corroboration is already encoded in the confidence state: §32.2 downgrades a
    fact precisely when its sources disagreed. Reading it here means the two
    lines cannot contradict, because they are derived from the same thing.

    `disputed` is absent on purpose — a disputed fact is downgraded and queued
    for adjudication upstream (§32.2), so it never reaches a rendered module
    wearing its own label.
    """
    key = (
        "ui.source.verified_two"
        if state is ConfidenceState.VERIFIED
        else "ui.source.single"
    )
    return _resolve_or_empty(key, locale)


def _plain_line(text: str) -> str:
    """§30.4 layer 1 — the CLAIM, in the words the reader just tapped.

    §30.4's own worked example opens exactly this way: "Today the Moon moves
    through your 10th house — work themes rise. Your birth time is exact, so
    this is precise." The claim first, the precision qualifier after — and the
    qualifier already has a home in layer 2, on the ConfidenceChip.

    The first cut put the CONFIDENCE description here instead, and the rendered
    sheet showed why that is wrong: layer 1 read "computed from your chart and
    checked against two sources", the sources row beneath it read "Computed from
    your chart · verified against 2 sources", and the chip beside that read the
    first sentence again. Three layers, one sentence, said three times — a Trust
    Sheet that looks thorough and tells a reader nothing they did not already
    have. The layers must each carry something the others do not: what was
    claimed, how we know it, and what the fact actually holds.
    """
    return text


def _detail(snapshot: FactSnapshot, locale: str) -> str | None:
    """One readable specific, straight off the value.

    Returns None for a value shape with no reader — which drops the line rather
    than inventing a label for it. §30.4's expander is for enthusiasts; a blank
    row would tell them less than no row.
    """
    value = snapshot.value
    if isinstance(value, TithiBoundaryValue):
        paksha = localised_term("paksha", value.paksha.value, locale)
        if paksha is None:
            return None
        return f"{_label('tithi', locale)} · {paksha} {value.tithi_index}"
    if isinstance(value, NakshatraBoundaryValue):
        name = localised_term("nakshatra", value.nakshatra.value, locale)
        return None if name is None else f"{_label('nakshatra', locale)} · {name}"
    if isinstance(value, NakshatraValue):
        name = localised_term("nakshatra", value.nakshatra.value, locale)
        graha = localised_term("graha", value.graha.value, locale)
        if name is None or graha is None:
            return None
        return f"{graha} · {name}"
    if isinstance(value, HouseAssignmentValue):
        graha = localised_term("graha", value.graha.value, locale)
        house = localised_term("ordinal_house", str(value.whole_sign_house), locale)
        if graha is None or house is None:
            return None
        return f"{graha} · {house}"
    if isinstance(value, MoolankValue | BhagyankValue):
        # `ui.module.number`, not `ui.panchang.*` — a numerology value is not a
        # panchang element and the panchang catalogue has no label for it.
        return f"{_resolve_or_empty('ui.module.number', locale)} · {value.value}"
    if isinstance(value, DayTimingValue | MuhuratWindowValue):
        return _window_detail(snapshot, value, locale)
    if isinstance(value, FestivalObservanceValue):
        # Festival names live under their own `festivals.*` namespace, not in
        # the closed-term catalogue — and §2.4's rule holds here too: a vendor's
        # English name never reaches a user, so an unnamed festival gets no
        # detail line rather than an English one.
        return _resolve_or_none(f"festivals.{value.festival_id}", locale)
    return None


def _window_detail(
    snapshot: FactSnapshot,
    value: DayTimingValue | MuhuratWindowValue,
    locale: str,
) -> str | None:
    """A window, rendered in the FACT's own zone.

    The same rule the composer follows, for the same reason: a time in the
    wrong zone is a lie that also happens to be a number mismatch.
    """
    from sitara_api.daily_guidance.templates import _clock

    span = f"{_clock(value.starts_utc, snapshot)}–{_clock(value.ends_utc, snapshot)}"
    if isinstance(value, DayTimingValue):
        name = localised_term("day_timing", value.timing.value, locale)
        return span if name is None else f"{name} · {span}"
    return span


def _resolve_or_none(key: str, locale: str) -> str | None:
    try:
        return resolve(key, locale)
    except MissingString:
        return None


def _label(kind: str, locale: str) -> str:
    return _resolve_or_empty(f"ui.panchang.{kind}", locale)


def _resolve_or_empty(key: str, locale: str) -> str:
    """§2.4 rule 7: decline rather than fall back to English.

    An empty trust line loses a reader some context. A trust line that silently
    switches language on a Hindi user loses them the claim that the whole app is
    theirs, which is the more expensive of the two.
    """
    try:
        return resolve(key, locale)
    except MissingString:
        logger.warning("trust string missing", extra={"key": key, "locale": locale})
        return ""


def trust_for(
    module: ComposedModule, state: ConfidenceState, locale: str, *, text: str
) -> TodayTrust:
    details = [d for d in (_detail(s, locale) for s in module.snapshots) if d]
    return TodayTrust(
        plain=_plain_line(text),
        sources_line=_sources_line(state, locale),
        details=tuple(details),
    )


# ---------------------------------------------------------------------------
# The payload pieces
# ---------------------------------------------------------------------------


def present_module(module: ComposedModule, brief: Brief, locale: str) -> TodayModule:
    state = module_confidence(module, brief.confidence or ConfidenceState.VERIFIED)
    text = strip_citations(module.rendered)
    return TodayModule(
        module=module.module,
        text=text,
        confidence=state,
        trust=trust_for(module, state, locale, text=text),
    )


def present_taras_line(line: TarasLine | None) -> TodayTarasLine | None:
    if line is None:
        return None
    return TodayTarasLine(text=strip_citations(line.text), confidence=line.confidence)


def present_timings(
    snapshots: Sequence[FactSnapshot], locale: str
) -> tuple[TodayTiming, ...]:
    """S16's day (§28.2 item 6 → `/today/timings`).

    Every window the day's facts carry, in clock order, rendered in the FACT's
    own zone — the same rule the composer follows, and for the same reason: a
    time in the wrong zone is a lie that also happens to be a number mismatch.

    Minutes-from-midnight travels beside the formatted range because `TimingBar`
    plots on a time-of-day axis (§29.4's dataviz rules) and deriving minutes
    from a rendered string on the client would put the zone conversion in two
    places, one of which would eventually be wrong.
    """
    from sitara_api.daily_guidance.templates import _clock

    out: list[TodayTiming] = []
    for snapshot in snapshots:
        value = snapshot.value
        if not isinstance(value, DayTimingValue | MuhuratWindowValue):
            continue
        starts = _clock(value.starts_utc, snapshot)
        ends = _clock(value.ends_utc, snapshot)
        if isinstance(value, DayTimingValue):
            name = localised_term("day_timing", value.timing.value, locale)
            if name is None:
                # §2.4: an unnamed window is a bar with no label. Drop it rather
                # than plot an English name on a Devanagari axis.
                logger.warning(
                    "timing unnamed in locale",
                    extra={"timing": value.timing.value, "locale": locale},
                )
                continue
        else:
            # A muhurat has no `DayTimingKind` to name it. `ui.timing.chart_label`
            # is the day's own label rather than the legend word "favourable",
            # which is the QUALITY and already renders beside every band — a
            # window named after its own colour tells a reader nothing.
            name = _resolve_or_empty("ui.timing.chart_label", locale)

        starts_minute = _minutes(starts)
        ends_minute = _minutes(ends)
        if ends_minute <= starts_minute:
            # The window crosses midnight — a night choghadiya running 23:00 to
            # 00:45 belongs partly to tomorrow. `TimingBar` plots a single
            # 24-hour axis and computes `width = end - start`, so the raw pair
            # produced a NEGATIVE width: an invalid CSS declaration, dropped by
            # the browser, leaving the band unrendered at the right-hand edge.
            # Truncating at the day boundary is the honest shape for a
            # today-axis; `range` still carries the true end time.
            ends_minute = _DAY_MINUTES

        out.append(
            TodayTiming(
                name=name,
                starts_minute=starts_minute,
                ends_minute=ends_minute,
                range=f"{starts}–{ends}",
                quality=TimingQuality(value.quality.value),
            )
        )
    return tuple(sorted(out, key=lambda t: t.starts_minute))


#: A day, on `TimingBar`'s axis.
_DAY_MINUTES = 24 * 60


def _minutes(clock: str) -> int:
    hours, minutes = (int(part) for part in clock.split(":"))
    return hours * 60 + minutes


def present_panchang(
    snapshots: Sequence[FactSnapshot], locale: str
) -> tuple[TodayPanchangEntry, ...]:
    """§28.2 item (6)'s summary row, in §5.2's own order.

    Only the entries whose fact is actually in hand. A row that showed "Tithi —"
    with nothing after it would be the panchang equivalent of an empty card.
    """
    entries: list[TodayPanchangEntry] = []
    for snapshot in snapshots:
        value = snapshot.value
        if isinstance(value, TithiBoundaryValue):
            paksha = localised_term("paksha", value.paksha.value, locale)
            if paksha is not None:
                entries.append(
                    TodayPanchangEntry(
                        label_key="ui.panchang.tithi", value=f"{paksha} {value.tithi_index}"
                    )
                )
        elif isinstance(value, NakshatraBoundaryValue):
            name = localised_term("nakshatra", value.nakshatra.value, locale)
            if name is not None:
                entries.append(
                    TodayPanchangEntry(label_key="ui.panchang.nakshatra", value=name)
                )
    return tuple(entries)
