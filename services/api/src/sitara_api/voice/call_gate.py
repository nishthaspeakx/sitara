"""§33.5's conditional release gate, as a measurement harness.

§33.5 does not say live calls should be good. It says they ship **only if** six
measures pass, and that any miss means launch proceeds with text, voice notes
and Tara audio replies while calls roll out behind a flag later. That is a
pass/fail instrument, and this module is it.

Why this exists before the call screen
--------------------------------------

Because §33.5's list is the acceptance criteria, and acceptance criteria
written down after the fact get graded on the curve of what was built. Six
numbers with thresholds, readable from the first commit, means every commit
after this one is *measured* rather than assessed at the end by someone who
already knows what the code does.

It also makes the honest answer cheap. Today five of the six measures have no
data at all and the sixth cannot be run outside English — and this module says
so, per measure, instead of leaving a blank that reads as "fine so far".

What "not measurable yet" means, and why it is not a failure
-------------------------------------------------------------

Two of §33.5's measures — in-call safety interception "in all 3 languages", and
beta naturalness — cannot be run in `hi` or `hi-Latn` at all, because CC-010
leaves those locales with no streaming recogniser. There is nothing to
intercept and nothing to rate. `MeasureState.BLOCKED` is that state, and it is
deliberately distinct from `FAILING`: a measure that cannot run has not been
failed, and reporting it as a failure would make the gate look closer to
passing once the blocker lifts than it actually is.

`passes()` returns False while any measure is BLOCKED or UNMEASURED, which is
the whole point — §33.5 is a gate, and an unrun measure is not a passed one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sitara_api.voice.providers.routing import Modality, blocked_locales

#: §2.4's launch locales, which is the set §33.5's "all 3 languages" names.
LAUNCH_LOCALES: tuple[str, ...] = ("en", "hi", "hi-Latn")


class MeasureState(StrEnum):
    PASSING = "passing"
    FAILING = "failing"
    #: Runnable, never run. No data is not good news.
    UNMEASURED = "unmeasured"
    #: Cannot be run at all yet — a dependency outside this measure's control.
    #: Distinct from FAILING on purpose: see the module docstring.
    BLOCKED = "blocked"


class Direction(StrEnum):
    """Which way is good. Stated per measure so nobody has to infer it from a
    threshold's name — `first_audio_p95_s` at 1.2 is a ceiling, `barge_in` at
    0.95 is a floor, and reading one as the other inverts the gate."""

    AT_MOST = "at_most"
    AT_LEAST = "at_least"


@dataclass(frozen=True)
class Measure:
    """One of §33.5's six. `spec_quote` is verbatim so a reader can check the
    threshold against the sentence it came from without leaving the file."""

    id: str
    spec_quote: str
    threshold: float
    direction: Direction
    unit: str
    #: Locales this measure must be satisfied in. Most are global; the safety
    #: one is explicitly per-language in §33.5's own words.
    per_locale: bool = False
    #: Set when the measure cannot run, with the reason. A blocked measure
    #: never reports a number, because a number from one locale standing in for
    #: three is exactly the misreading this guards against.
    blocked_reason: str | None = None

    def evaluate(self, value: float | None) -> MeasureState:
        if self.blocked_reason is not None:
            return MeasureState.BLOCKED
        if value is None:
            return MeasureState.UNMEASURED
        if self.direction is Direction.AT_MOST:
            return MeasureState.PASSING if value <= self.threshold else MeasureState.FAILING
        return MeasureState.PASSING if value >= self.threshold else MeasureState.FAILING


def _indic_blocked() -> str | None:
    """The reason string the two language-bound measures carry, or None once
    the routing matrix says every launch locale has a streaming recogniser.

    Read from `routing.CAPABILITIES` rather than hardcoded, so this stops being
    blocked on the same commit that unblocks it — the same discipline the
    `call.indic_streaming_stt` release gate follows.
    """
    blocked = blocked_locales(Modality.STREAMING, LAUNCH_LOCALES)
    if not blocked:
        return None
    return (
        f"no streaming STT for {', '.join(blocked)} (CC-010) — there is nothing to "
        "measure in those locales until Sarvam's realtime arm lands"
    )


def measures() -> tuple[Measure, ...]:
    """§33.5's six, in the order the spec lists them."""
    indic = _indic_blocked()
    return (
        Measure(
            id="first_audio_p95_s",
            spec_quote="p95 first-response audio ≤1.2s",
            threshold=1.2,
            direction=Direction.AT_MOST,
            unit="seconds",
        ),
        Measure(
            id="barge_in_success",
            spec_quote="barge-in success ≥95%",
            threshold=0.95,
            direction=Direction.AT_LEAST,
            unit="ratio",
        ),
        Measure(
            id="network_recovery_success",
            spec_quote="network-recovery handoff success ≥98%",
            threshold=0.98,
            direction=Direction.AT_LEAST,
            unit="ratio",
        ),
        Measure(
            id="cost_per_call_user",
            spec_quote="cost per active call-user within the §7.3 model",
            # §1's unit ceiling: AI + voice ≤ ₹110 per paid user per month.
            # Calls are one part of that, so this is a sub-ceiling and the
            # §7.3 model is what sets it — recorded here so the number is not
            # invented at measurement time.
            threshold=110.0,
            direction=Direction.AT_MOST,
            unit="INR/user/month",
        ),
        Measure(
            id="safety_interception",
            spec_quote="in-call safety interception verified in all 3 languages",
            threshold=1.0,
            direction=Direction.AT_LEAST,
            unit="ratio verified",
            per_locale=True,
            blocked_reason=indic,
        ),
        Measure(
            id="call_naturalness",
            spec_quote="user-rated call naturalness ≥4.2/5 in beta",
            threshold=4.2,
            direction=Direction.AT_LEAST,
            unit="MOS",
            per_locale=True,
            blocked_reason=indic,
        ),
    )


@dataclass
class GateReport:
    results: dict[str, MeasureState] = field(default_factory=dict)
    values: dict[str, float | None] = field(default_factory=dict)

    @property
    def passes(self) -> bool:
        """§33.5's own logic: calls ship ONLY IF every measure passes.

        An UNMEASURED or BLOCKED measure is not a pass. That is the sentence
        the spec wrote, and the reason this returns False today.
        """
        return bool(self.results) and all(
            state is MeasureState.PASSING for state in self.results.values()
        )

    @property
    def blocked(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.results.items() if v is MeasureState.BLOCKED)

    @property
    def unmeasured(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.results.items() if v is MeasureState.UNMEASURED)

    @property
    def failing(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.results.items() if v is MeasureState.FAILING)


def evaluate(observed: dict[str, float | None] | None = None) -> GateReport:
    """Score §33.5 against whatever has actually been measured.

    `observed` is deliberately sparse: a measure absent from it is UNMEASURED,
    not zero. Defaulting a missing measure to 0 would make the cost ceiling
    pass and the four floors fail, which is noise rather than a reading.
    """
    observed = observed or {}
    report = GateReport()
    for measure in measures():
        value = observed.get(measure.id)
        report.values[measure.id] = value
        report.results[measure.id] = measure.evaluate(value)
    return report


def render(report: GateReport) -> str:
    """The §33.5 table, for `/shipcheck` and for a human deciding to launch."""
    lines = [
        "§33.5 — live-call conditional release gate",
        "calls ship ONLY IF every measure passes; any miss → launch with text,",
        "voice notes and Tara audio replies, calls behind a flag (§33.5).",
        "",
        f"{'measure':<26} {'state':<11} {'observed':>12}  threshold",
        "-" * 72,
    ]
    for measure in measures():
        state = report.results[measure.id]
        value = report.values.get(measure.id)
        shown = "—" if value is None else f"{value:g}"
        arrow = "≤" if measure.direction is Direction.AT_MOST else "≥"
        lines.append(
            f"{measure.id:<26} {state.value:<11} {shown:>12}  "
            f"{arrow}{measure.threshold:g} {measure.unit}"
        )
    lines.append("")
    if report.blocked:
        reason = next(m.blocked_reason for m in measures() if m.blocked_reason)
        lines.append(f"BLOCKED ({', '.join(report.blocked)}): {reason}")
    if report.unmeasured:
        lines.append(f"UNMEASURED: {', '.join(report.unmeasured)} — no data is not good news.")
    lines.append(f"gate: {'PASSES' if report.passes else 'DOES NOT PASS'}")
    return "\n".join(lines)


def main() -> int:  # pragma: no cover - operator entry point
    print(render(evaluate()))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
