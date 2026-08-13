"""§30.4's three layers, rendered from fact snapshots.

This lived inside `daily_guidance/presenter.py` until S18, because Today was
the only surface with a Trust Sheet on it. It is not daily-guidance's business:
§30.4 says "every astrological claim reachable to a Trust Sheet in ≤1 tap", and
§25.4 puts fact-citation underlines inside chat bubbles — the same sheet, the
same three layers, behind a claim in a different surface.

So the rendering moved here rather than being imported across a bounded-context
boundary or, worse, written twice. A second `_detail` would drift the way every
duplicated closed set in this repo has drifted: silently, until a screen showed
the difference.

The two callers keep their own wire shapes (`TodayTrust`, `ChatTrust`) and wrap
`TrustLayers`; only the rendering is shared.

Three rules govern this file, carried over intact:

**Fact IDs stop here.** §30.4 keeps them internal. `TrustLayers` has no field
one could travel in, and neither does either wire shape.

**A detail line is rendered from the snapshot or omitted.** §30.4's expander is
"nakshatra/tithi/transit specifics in readable terms", which means reading the
value — never paraphrasing the sentence above it, which would be a summary
dressed as a source.

**Each layer must say something the others do not** — what was claimed, how we
know it, what the fact holds. The first cut put the confidence description in
layer 1, and the rendered sheet said one sentence three times.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sitara_schemas.facts import (
    BhagyankValue,
    ConfidenceState,
    DashaPeriodValue,
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

from sitara_api.localisation import MissingString, resolve

logger = logging.getLogger(__name__)

#: §5.4's states from strongest to weakest. A claim's state is the WEAKEST of
#: the snapshots it stands on: a sentence is only as sound as its softest
#: source, and rounding up is how "approximate" quietly becomes "verified".
STRENGTH: tuple[ConfidenceState, ...] = (
    ConfidenceState.VERIFIED,
    ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA,
    ConfidenceState.APPROXIMATE,
    ConfidenceState.TRADITION_BASED_GENERAL,
    ConfidenceState.CANNOT_CALCULATE,
)


def weakest(
    snapshots: Sequence[FactSnapshot], fallback: ConfidenceState
) -> ConfidenceState:
    """The confidence a sentence standing on these snapshots may claim."""
    declared = [s.confidence for s in snapshots if s.confidence is not None]
    if not declared:
        return fallback
    return max(declared, key=STRENGTH.index)


@dataclass(frozen=True)
class TrustLayers:
    """§30.4's three layers, already localised. No field can carry a fact ID."""

    plain: str
    sources_line: str
    details: tuple[str, ...]


def layers(
    snapshots: Sequence[FactSnapshot],
    state: ConfidenceState,
    locale: str,
    *,
    text: str,
) -> TrustLayers:
    details = [d for d in (detail(s, locale) for s in snapshots) if d]
    return TrustLayers(
        plain=plain_line(text),
        sources_line=sources_line(state, locale),
        details=tuple(details),
    )


# ---------------------------------------------------------------------------
# Layer 1 — the claim
# ---------------------------------------------------------------------------


def plain_line(text: str) -> str:
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
    have.
    """
    return text


# ---------------------------------------------------------------------------
# Layer 2 — how we know it
# ---------------------------------------------------------------------------


def sources_line(state: ConfidenceState, locale: str) -> str:
    """VerifiedSourceRow's sentence, from the confidence state.

    **Not from the snapshot count.** The first cut read `len(snapshots)`, and
    the recorded fixtures caught what that produces: a Trust Sheet whose plain
    line said "checked against two sources" directly above a source row saying
    "one source available today". Two sentences, one card, contradicting each
    other — because a snapshot count is how many DIFFERENT facts a sentence
    stands on (a tithi and a nakshatra), not how many sources agreed on one.

    Corroboration is already encoded in the confidence state: §32.2 downgrades a
    fact precisely when its sources disagreed. Reading it here means the two
    lines cannot contradict, because they are derived from the same thing.

    `disputed` is absent on purpose — a disputed fact is downgraded and queued
    for adjudication upstream (§32.2), so it never reaches a rendered claim
    wearing its own label.
    """
    key = (
        "ui.source.verified_two"
        if state is ConfidenceState.VERIFIED
        else "ui.source.single"
    )
    return resolve_or_empty(key, locale)


# ---------------------------------------------------------------------------
# Layer 3 — what the fact holds
# ---------------------------------------------------------------------------


def detail(snapshot: FactSnapshot, locale: str) -> str | None:
    """One readable specific, straight off the value.

    Returns None for a value shape with no reader — which drops the line rather
    than inventing a label for it. §30.4's expander is for enthusiasts; a blank
    row would tell them less than no row.
    """
    from sitara_api.daily_guidance.templates import localised_term

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
    if isinstance(value, DashaPeriodValue):
        # A dasha-backed claim had NO layer 3 at all until the first live
        # conversation: Today's modules never stand on a dasha fact, so this
        # renderer — written for Today — had no branch for one. Chat does, and
        # constantly: "you are in a Jupiter mahadasha" is the single most
        # common grounded sentence a real model produced. The sheet opened on
        # a claim, a sources line, and nothing under "see the details".
        lord = localised_term("graha", value.lord.value, locale)
        level = localised_term("dasha_level", value.level.value, locale)
        if lord is None or level is None:
            return None
        return f"{lord} · {level}"
    if isinstance(value, MoolankValue | BhagyankValue):
        # `ui.module.number`, not `ui.panchang.*` — a numerology value is not a
        # panchang element and the panchang catalogue has no label for it.
        return f"{resolve_or_empty('ui.module.number', locale)} · {value.value}"
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
    from sitara_api.daily_guidance.templates import _clock, localised_term

    span = f"{_clock(value.starts_utc, snapshot)}–{_clock(value.ends_utc, snapshot)}"
    if isinstance(value, DayTimingValue):
        name = localised_term("day_timing", value.timing.value, locale)
        return span if name is None else f"{name} · {span}"
    return span


# ---------------------------------------------------------------------------
# Localisation helpers
# ---------------------------------------------------------------------------


def _resolve_or_none(key: str, locale: str) -> str | None:
    try:
        return resolve(key, locale)
    except MissingString:
        return None


def _label(kind: str, locale: str) -> str:
    return resolve_or_empty(f"ui.panchang.{kind}", locale)


def resolve_or_empty(key: str, locale: str) -> str:
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
