"""Fact fixtures for §28.2's sixteen variants.

**What is fixed here, and what is not.** These are FACTS and account state —
a tithi, a nakshatra, a rahu-kaal window, a subscription in its grace period.
Everything downstream of them is real: `ranking.rank` picks the modules,
`BriefComposer` writes the sentences from the snapshots and cites them, and
`service.compose_brief` runs the §7.1 degradation ladder. The dev switcher and
the recorded §24.8 baselines therefore show what the engine actually emits.

Fixing the facts is not a shortcut, it is the only option: you cannot make it
be Diwali on demand, or make a provider fail on demand, or be four days into a
trial on demand. What you CAN refuse to fake is everything that reads them, and
that is the line this file draws.

The variants that are purely a client concern — `offline`, and the three
density modes — are absent by design. Offline is a failed fetch against a
cached payload, which the screen produces; density is a query parameter that
changes `ranking`'s output count. Neither is a different set of facts.
"""

from __future__ import annotations

import datetime as dt

from sitara_schemas.facts import (
    ConfidenceState,
    DayTimingKind,
    DayTimingValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    FestivalObservanceValue,
    Graha,
    HouseAssignmentValue,
    MoolankValue,
    Nakshatra,
    NakshatraBoundaryValue,
    Paksha,
    TimingQuality,
    TithiBoundaryValue,
    Tradition,
    TzMethod,
    build_fact_id,
)
from sitara_schemas.today import PlanState, TodayState, TodayTravel

from sitara_api.daily_guidance.service import BriefFacts

#: One ordinary day in Bengaluru, so every window and boundary below is a real
#: interval in a real zone rather than a UTC placeholder (§5.3).
IST = TzMethod(tz="Asia/Kolkata", utc_offset_seconds=19800)
USER_ID = "6a70000000000000000000a1"
LOCAL_DATE = "2026-08-12"
DAY_START = dt.datetime(2026, 8, 11, 18, 30, tzinfo=dt.UTC)  # 00:00 IST
DAY_END = dt.datetime(2026, 8, 12, 18, 29, tzinfo=dt.UTC)


def _snapshot(kind: FactKind, value, kind_path: str) -> FactSnapshot:  # noqa: ANN001
    return FactSnapshot(
        fact_id=build_fact_id(kind_path, LOCAL_DATE, USER_ID, 1),
        kind=kind,
        value=value,
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(ayanamsa="lahiri", tz=IST, rise_set="upper_limb_refracted"),
        valid_from=DAY_START,
        valid_to=DAY_END,
        engine_semver="0.1.0",
        data_revision="dev-fixture",
        confidence=ConfidenceState.VERIFIED,
    )


def tithi() -> FactSnapshot:
    return _snapshot(
        FactKind.PANCHANG_TITHI_BOUNDARY,
        TithiBoundaryValue(
            starts_utc=DAY_START, ends_utc=DAY_END, tithi_index=5, paksha=Paksha.SHUKLA
        ),
        "panchang.tithi.boundary",
    )


def nakshatra() -> FactSnapshot:
    return _snapshot(
        FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
        NakshatraBoundaryValue(
            starts_utc=DAY_START,
            ends_utc=DAY_END,
            nakshatra=Nakshatra.ROHINI,
            nakshatra_index=4,
        ),
        "panchang.nakshatra.boundary",
    )


def rahu_kaal() -> FactSnapshot:
    """09:00–10:30 IST — the caution window, and what `what_to_avoid` reads."""
    return _snapshot(
        FactKind.PANCHANG_DAY_TIMING,
        DayTimingValue(
            starts_utc=dt.datetime(2026, 8, 12, 3, 30, tzinfo=dt.UTC),
            ends_utc=dt.datetime(2026, 8, 12, 5, 0, tzinfo=dt.UTC),
            timing=DayTimingKind.RAHU_KAAL,
            quality=TimingQuality.INAUSPICIOUS,
        ),
        "panchang.day_timing.rahu_kaal",
    )


def abhijit() -> FactSnapshot:
    """11:45–12:35 IST — the favourable window."""
    return _snapshot(
        FactKind.PANCHANG_DAY_TIMING,
        DayTimingValue(
            starts_utc=dt.datetime(2026, 8, 12, 6, 15, tzinfo=dt.UTC),
            ends_utc=dt.datetime(2026, 8, 12, 7, 5, tzinfo=dt.UTC),
            timing=DayTimingKind.ABHIJIT,
            quality=TimingQuality.AUSPICIOUS,
        ),
        "panchang.day_timing.abhijit",
    )


def moon_house() -> FactSnapshot:
    """The core card's fact — §28.2's "THE day's theme from her chart"."""
    return _snapshot(
        FactKind.TRANSIT_GRAHA_HOUSE,
        HouseAssignmentValue(graha=Graha.MOON, whole_sign_house=10, bhava=10),
        "transit.moon.house",
    )


def venus_house() -> FactSnapshot:
    return _snapshot(
        FactKind.TRANSIT_GRAHA_HOUSE,
        HouseAssignmentValue(graha=Graha.VENUS, whole_sign_house=7, bhava=7),
        "transit.venus.house",
    )


def moolank() -> FactSnapshot:
    return _snapshot(
        FactKind.NUMEROLOGY_MOOLANK,
        MoolankValue(value=8, birth_day=17, reduction_steps=(17, 8)),
        "numerology.moolank",
    )


def festival() -> FactSnapshot:
    return _snapshot(
        FactKind.FESTIVAL_OBSERVANCE,
        FestivalObservanceValue(
            festival_id="raksha_bandhan",
            date_local=dt.date.fromisoformat(LOCAL_DATE),
            region="in",
            tradition=Tradition.AMANTA,
        ),
        "festival.raksha_bandhan",
    )


#: A full, healthy morning: panchang + chart + numerology. Every module the
#: ranking engine can reach on a good day has its evidence here.
def full_facts() -> BriefFacts:
    return BriefFacts(
        snapshots=(
            tithi(),
            nakshatra(),
            rahu_kaal(),
            abhijit(),
            moon_house(),
            venus_house(),
            moolank(),
        ),
        confidence=ConfidenceState.VERIFIED,
    )


def festival_facts() -> BriefFacts:
    base = full_facts()
    return BriefFacts(
        snapshots=(*base.snapshots, festival()),
        confidence=base.confidence,
    )


def degraded_facts() -> BriefFacts:
    """§7.1's degrade: panchang in hand, no chart.

    `missing=("chart",)` is what makes the ladder land on VERIFIED_CORE_CARDS
    with a named reason rather than on a short brief with no explanation —
    "the panchang cell was cold" and "this person has no birth time" produce
    the same few cards and are not the same problem.
    """
    return BriefFacts(
        snapshots=(tithi(), nakshatra()),
        confidence=ConfidenceState.TRADITION_BASED_GENERAL,
        missing=("chart",),
        degraded=True,
    )


def no_birth_time_facts() -> BriefFacts:
    """A Moon-chart morning: panchang and numerology, no house assignments.

    §5.3 drops every lagna-sensitive claim when the birth time is a window, so
    the chart half is genuinely absent rather than approximated.
    """
    return BriefFacts(
        snapshots=(tithi(), nakshatra(), rahu_kaal(), abhijit(), moolank()),
        confidence=ConfidenceState.APPROXIMATE,
        missing=("chart",),
        degraded=True,
    )


def no_facts() -> BriefFacts:
    """Nothing at all — the brief FAILS, and §28.2 renders the honest state."""
    return BriefFacts(
        confidence=ConfidenceState.CANNOT_CALCULATE,
        missing=("panchang", "chart"),
        degraded=True,
    )


# ---------------------------------------------------------------------------
# The sixteen
# ---------------------------------------------------------------------------


def _state(**overrides) -> TodayState:  # noqa: ANN003
    base = {
        "first_session": False,
        "first_morning": False,
        "brief_time": "07:00",
        "travel": TodayTravel(active=False, city=None),
        "festival": None,
        "birthday": False,
        "birth_time_missing": False,
        "trial_day": None,
        "plan": PlanState.PREMIUM,
        # §30.6: hidden in P0. A dev switcher that turned it on would be
        # previewing a surface the build does not ship.
        "story_ring_enabled": False,
    }
    return TodayState(**{**base, **overrides})


#: variant → (facts, local_time, state overrides, skip_polish)
#:
#: `local_time` is DATA (see `today.json`): the night takeover and the sky band
#: are pinned by the fixture, so a baseline does not depend on when CI ran.
VARIANTS: dict[str, tuple] = {
    "first_session": (no_facts(), "09:10", {"first_session": True}, True),
    "first_morning": (full_facts(), "07:05", {"first_morning": True}, True),
    "normal_morning": (full_facts(), "08:30", {}, True),
    "afternoon": (full_facts(), "14:20", {}, True),
    "evening": (full_facts(), "18:10", {}, True),
    "night": (full_facts(), "21:15", {}, True),
    "festival": (
        festival_facts(),
        "08:30",
        {"festival": True},  # resolved in-locale by the router
        True,
    ),
    "birthday": (full_facts(), "08:30", {"birthday": True}, True),
    "travel": (
        full_facts(),
        "08:30",
        {"travel": TodayTravel(active=True, city="London")},
        True,
    ),
    "missing_birth_time": (
        no_birth_time_facts(),
        "08:30",
        {"birth_time_missing": True},
        True,
    ),
    # The screen's own state, not the engine's: a failed fetch over a cached
    # payload. Recorded from a healthy morning so the cache has something true
    # in it, exactly as a real one would.
    "offline": (full_facts(), "08:30", {}, True),
    # The ONE variant that must run the polish stage: §7.1's degrade is
    # reached through diagram 5's grounding `fail` edge (see UngroundedLLM).
    "provider_degraded": (degraded_facts(), "08:30", {}, False),
    "trial": (full_facts(), "08:30", {"plan": PlanState.TRIAL, "trial_day": 4}, True),
    "premium": (full_facts(), "08:30", {"plan": PlanState.PREMIUM}, True),
    "free": (full_facts(), "08:30", {"plan": PlanState.FREE}, True),
    "payment_grace": (full_facts(), "08:30", {"plan": PlanState.GRACE}, True),
    # NOT one of §28.2's sixteen — §32.1's own named screenshot case: "the
    # design-QA screenshot suite adds the worst-case combination
    # (grace+travel+festival+trial) per locale; core-card dominance rule §28.2
    # verified against it". Four rules fire at once here, which is the morning
    # nobody has in front of them while writing a component.
    "worst_case": (
        festival_facts(),
        "08:30",
        {
            "plan": PlanState.GRACE,
            "travel": TodayTravel(active=True, city="London"),
            "festival": True,
            "trial_day": 6,
            # Present, and expected to be SUPPRESSED — §32.1 yields the chip to
            # any banner, and this is the case that proves it.
            "birth_time_missing": True,
        },
        True,
    ),
}


class UngroundedLLM:
    """A model that strips every citation. The one stub in this file.

    §7.1's degrade to verified core cards has exactly two triggers, and only one
    of them can be reproduced from facts: "facts too thin" needs a fact set the
    ranking engine declines entirely, which by construction also leaves
    `core_cards` with nothing, so it lands on FAILED rather than on the degrade.
    The trigger §28.2's provider-degraded variant is actually about is diagram
    5's `fail` edge — "a polish pass in which EVERY line failed grounding".

    A model that will not stop rewriting the facts is a failure mode no real
    provider produces on demand, which is the one thing a stub is legitimately
    for. Everything downstream of it is real: the grounding validator really
    rejects these lines, the single corrective regeneration really runs and
    really fails again, and `compose_brief` really falls back to `core_cards`.
    """

    model = "dev-ungrounded"

    async def complete(self, request):  # noqa: ANN001, ANN201
        import json as _json

        from sitara_api.chat_orchestration.llm import LLMResponse

        payload = _json.loads(request.messages[0]["content"])
        lines = [
            # The citation goes; the astrological claim stays. That is exactly
            # what cite-or-die exists to catch.
            {"index": line["index"], "text": _strip_markers(line["text"])}
            for line in payload["lines"]
        ]
        parsed = {"lines": lines}
        return LLMResponse(
            text=_json.dumps(parsed), model=self.model, parsed=parsed
        )


def _strip_markers(text: str) -> str:
    import re

    return re.sub(r"\s*\[\[[^\]]+\]\]", "", text)


def state_for(variant: str, locale: str, brief) -> TodayState:  # noqa: ANN001
    """The account state for a variant, with the festival named in-locale.

    The festival is resolved by the router's own `festival_from` against the
    real brief, not hand-built here: §2.4's "a vendor's English festival name
    never reaches a user" is enforced there, and a fixture that bypassed it
    could preview a banner the product would refuse to raise.
    """
    from sitara_api.daily_guidance.today_state import festival_from

    _, _, overrides, _ = VARIANTS[variant]
    overrides = dict(overrides)
    if overrides.get("festival") is True:
        overrides["festival"] = festival_from(brief, locale)
    return _state(**overrides)
