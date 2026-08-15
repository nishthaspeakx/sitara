"""§33.5's conditional release gate.

The gate is a pass/fail instrument, so the tests worth having are about the
ways it could quietly report "closer to shipping than we are": a missing
measure reading as a pass, a blocked measure reading as a failure, a threshold
compared the wrong way round.
"""

from __future__ import annotations

import pytest

from sitara_api.voice.call_gate import (
    LAUNCH_LOCALES,
    Direction,
    MeasureState,
    evaluate,
    measures,
    render,
)
from sitara_api.voice.providers.routing import (
    CAPABILITIES,
    Modality,
    Support,
    VoiceProviderName,
)

ALL_PASSING = {
    "first_audio_p95_s": 1.0,
    "barge_in_success": 0.97,
    "network_recovery_success": 0.99,
    "cost_per_call_user": 84.0,
    "safety_interception": 1.0,
    "call_naturalness": 4.4,
}


def test_the_six_measures_are_exactly_33_5s_six() -> None:
    ids = [m.id for m in measures()]
    assert ids == [
        "first_audio_p95_s",
        "barge_in_success",
        "network_recovery_success",
        "cost_per_call_user",
        "safety_interception",
        "call_naturalness",
    ]
    # Every one carries the sentence it came from, so a threshold can be
    # checked against the spec without leaving the file.
    assert all(m.spec_quote for m in measures())


def test_an_unmeasured_gate_does_not_pass() -> None:
    """The state the project is in today, and the one a gate most easily gets
    wrong: nothing measured must not read as nothing failing."""
    report = evaluate()
    assert not report.passes
    assert not report.failing
    assert set(report.unmeasured) | set(report.blocked) == {m.id for m in measures()}


def test_a_blocked_measure_is_not_a_failing_one() -> None:
    """CC-010 leaves hi/hi-Latn with no streaming recogniser, so there is
    nothing to intercept and nobody to rate. Reporting that as FAILING would
    make the gate look closer to passing once the blocker lifts than it is —
    a failure looks like something you fix, a blocker like something you wait
    for, and they are budgeted differently."""
    report = evaluate(ALL_PASSING)
    assert set(report.blocked) == {"safety_interception", "call_naturalness"}
    assert not report.failing
    assert not report.passes, "a blocked measure is not a passed one (§33.5)"


def test_the_language_bound_measures_unblock_from_the_routing_matrix() -> None:
    """The blocked reason is READ, not hardcoded, so the harness stops being
    blocked on the same commit that unblocks it. A hardcoded one would sit
    there red long after Sarvam landed."""
    cell = (VoiceProviderName.SARVAM, Modality.STREAMING)
    before = dict(CAPABILITIES[cell])
    try:
        CAPABILITIES[cell] = {loc: Support.IMPLEMENTED for loc in LAUNCH_LOCALES}
        report = evaluate(ALL_PASSING)
        assert not report.blocked
        assert report.passes
    finally:
        CAPABILITIES[cell] = before

    assert evaluate(ALL_PASSING).blocked, "the capability mutation leaked"


def test_a_ceiling_is_not_read_as_a_floor() -> None:
    """`first_audio_p95_s` at 1.2 is a maximum and `barge_in_success` at 0.95 a
    minimum. Inverting either silently reverses the gate for that measure."""
    latency = next(m for m in measures() if m.id == "first_audio_p95_s")
    barge = next(m for m in measures() if m.id == "barge_in_success")

    assert latency.direction is Direction.AT_MOST
    assert latency.evaluate(1.2) is MeasureState.PASSING
    assert latency.evaluate(1.3) is MeasureState.FAILING

    assert barge.direction is Direction.AT_LEAST
    assert barge.evaluate(0.95) is MeasureState.PASSING
    assert barge.evaluate(0.94) is MeasureState.FAILING


def test_a_missing_measure_is_not_defaulted_to_zero() -> None:
    """Zero would make the one ceiling pass and the four floors fail — noise
    that looks like a reading."""
    report = evaluate({"first_audio_p95_s": 1.0})
    assert report.results["first_audio_p95_s"] is MeasureState.PASSING
    assert report.results["cost_per_call_user"] is MeasureState.UNMEASURED
    assert report.values["cost_per_call_user"] is None


@pytest.mark.parametrize("measure_id", ["safety_interception", "call_naturalness"])
def test_the_per_language_measures_are_marked_as_such(measure_id: str) -> None:
    """§33.5 says "verified in all 3 languages" for safety, and beta ratings
    are per-locale too. A global number standing in for three is exactly the
    misreading the flag exists to prevent."""
    measure = next(m for m in measures() if m.id == measure_id)
    assert measure.per_locale


def test_the_report_states_the_blocker_in_words() -> None:
    """A human deciding whether to launch reads this. "DOES NOT PASS" with no
    reason is the kind of output people learn to scroll past."""
    text = render(evaluate(ALL_PASSING))
    assert "DOES NOT PASS" in text
    assert "BLOCKED" in text
    assert "CC-010" in text
    assert "Sarvam" in text
    # And §33.5's own consequence, so the reader knows what a miss costs.
    assert "behind a flag" in text
