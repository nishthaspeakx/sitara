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
    ConfidenceState,
    DayTimingValue,
    FactSnapshot,
    MuhuratWindowValue,
    NakshatraBoundaryValue,
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

from sitara_api import trust
from sitara_api.chat_orchestration.grounding import strip_citations
from sitara_api.daily_guidance.templates import TarasLine, localised_term
from sitara_api.daily_guidance.types import Brief, ComposedModule

logger = logging.getLogger(__name__)

def module_confidence(
    module: ComposedModule, fallback: ConfidenceState
) -> ConfidenceState:
    """§5.4's weakest-snapshot rule, over a composed module's own snapshots."""
    return trust.weakest(module.snapshots, fallback)


def trust_for(
    module: ComposedModule, state: ConfidenceState, locale: str, *, text: str
) -> TodayTrust:
    """§30.4's three layers, in the shape §28.2's payload carries them.

    The rendering itself is `sitara_api.trust` — §25.4 puts the same sheet
    behind a chat bubble's citation underline, so a second copy here would be
    two implementations of one spec section, diverging quietly.
    """
    rendered = trust.layers(module.snapshots, state, locale, text=text)
    return TodayTrust(
        plain=rendered.plain,
        sources_line=rendered.sources_line,
        details=rendered.details,
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
            name = trust.resolve_or_empty("ui.timing.chart_label", locale)

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
