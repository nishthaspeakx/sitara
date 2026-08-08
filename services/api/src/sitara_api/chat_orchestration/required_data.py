"""Stage 4 — required-data check and the §5.4 confidence state.

§5.3 steps 2–3: "check required data (birth date/time/place, current location)
→ sufficiency decision (drives the confidence state)". §5.4 then says
confidence is computed "in step 3/6" — twice, because a disputed fact arriving
at step 6 can only downgrade what step 3 decided. `downgrade_for_facts` is
that second computation.

Nothing here is fabricated upward. A missing birth time produces the Moon-chart
framing, not a guessed lagna.
"""

from __future__ import annotations

from sitara_schemas.facts import ConfidenceState

from sitara_api.chat_orchestration.types import (
    CHARTLESS_INTENTS,
    BirthProfile,
    DataSufficiency,
    FactTool,
    Intent,
    IntentDecision,
    ValidatedFacts,
)

#: Tools that need a chart, and therefore a birth date and place.
_CHART_TOOLS: frozenset[FactTool] = frozenset(
    {FactTool.NATAL_CHART, FactTool.TRANSITS}
)
#: Numerology needs the DATE only — the date alone is exact, so no time is
#: missing and the reading is not downgraded for lacking one (§5.5, §22.10).
_DATE_ONLY_TOOLS: frozenset[FactTool] = frozenset({FactTool.NUMEROLOGY_PROFILE})
#: Place-anchored calendar facts need a place, never a birth chart.
_PLACE_TOOLS: frozenset[FactTool] = frozenset(
    {FactTool.PANCHANG_DAY, FactTool.PANCHANG_DAY_TIMINGS, FactTool.MUHURAT_WINDOW}
)


def assess(
    decision: IntentDecision,
    profile: BirthProfile,
    *,
    has_current_location: bool,
) -> DataSufficiency:
    """§5.3 step 3, producing the §5.4 row this turn is entitled to."""
    tools = set(decision.tools)
    missing: list[str] = []

    if tools & _PLACE_TOOLS and not has_current_location:
        missing.append("current_location")

    needs_chart = bool(tools & _CHART_TOOLS)
    needs_date = needs_chart or bool(tools & _DATE_ONLY_TOOLS)

    if needs_date and not profile.has_date:
        missing.append("birth_date")
    if needs_chart and not profile.has_place:
        missing.append("birth_place")

    if missing:
        # §5.3: missing data → Tara asks or declines, in-locale. Never a guess.
        return DataSufficiency(ConfidenceState.CANNOT_CALCULATE, tuple(missing))

    if not needs_chart:
        if tools & _DATE_ONLY_TOOLS:
            # Exact date, exact numbers — nothing about this is approximate.
            return DataSufficiency(ConfidenceState.VERIFIED)
        if decision.intent in CHARTLESS_INTENTS or not tools:
            return DataSufficiency(ConfidenceState.TRADITION_BASED_GENERAL)
        return DataSufficiency(ConfidenceState.TRADITION_BASED_GENERAL)

    if profile.has_exact_time:
        return DataSufficiency(ConfidenceState.VERIFIED)
    if profile.has_time_window:
        # A window is not a time: §5.4's "birth time is within a window".
        return DataSufficiency(ConfidenceState.APPROXIMATE)
    # Date + place, no time at all: Moon chart rather than precise Lagna timing.
    return DataSufficiency(ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA)


#: Lower is weaker. Used only to take a minimum — never to promote.
_RANK: dict[ConfidenceState, int] = {
    ConfidenceState.CANNOT_CALCULATE: 0,
    ConfidenceState.TRADITION_BASED_GENERAL: 1,
    ConfidenceState.APPROXIMATE: 2,
    ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA: 3,
    ConfidenceState.VERIFIED: 4,
}


def downgrade_for_facts(current: ConfidenceState, facts: ValidatedFacts) -> ConfidenceState:
    """§5.4 step 6: a disputed fact in play caps the turn at Approximate.

    Only ever weakens. §32.2/§35.3: a Layer-A↔vendor gap on deterministic
    astronomy raises a review flag and must NOT land here — the panchang
    service already resolves that before a snapshot carries `disputed`.
    """
    candidates = [current]
    if facts.disputed:
        candidates.append(ConfidenceState.APPROXIMATE)
    candidates.extend(f.confidence for f in facts.snapshots if f.confidence is not None)
    return min(candidates, key=lambda state: _RANK[state])


def is_small_talk(intent: Intent) -> bool:
    from sitara_api.chat_orchestration.types import SMALL_TALK_INTENTS

    return intent in SMALL_TALK_INTENTS
