"""The honest marker for the streaming adapters (§25.3, CC-009, M10).

Same instrument as `tests/panchang/fixtures/README.md`'s
`test_all_fixtures_recorded_from_live_api`, and here for the same reason: this
suite must be able to say, without anyone reading a docstring, which vendor
shapes somebody has actually SEEN.

The batch pair (`POST /stt`, `POST /tts/bytes`) was verified live on
13 Aug 2026 and has recorded fixtures. The streaming pair was written from
documentation in M10 and **no live streaming call has been made**. That is the
DivineAPI standing, not the Prokerala one.

Why it matters more here than it looks. §33.5's release gate turns on two
numbers — p95 first-response audio ≤1.2s and barge-in success ≥95% — that are
properties of the STREAMING path and of nothing else. A batch verification says
nothing about either. So "Cartesia is verified" is true and, for the purpose of
the gate this milestone exists to feed, means nothing.

**This test SKIPS while the recording is missing and turns green by itself once
it is not.** Deleting the skip to make the suite look complete would delete the
only mechanical statement that the streaming shapes are guesses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
STREAMING_RECORD = FIXTURES / "streaming_en.json"

RECORD_COMMAND = "CARTESIA_API_KEY=... uv run python -m tests.voice.record_streaming"


def test_the_streaming_shapes_are_read_and_not_seen() -> None:
    """Skips until someone has run the live check. That is the point."""
    if not STREAMING_RECORD.exists():
        pytest.skip(
            "Cartesia's STREAMING endpoints are UNVERIFIED — the frame shapes in "
            "`voice/providers/cartesia.py` come from the vendor's documentation and "
            "no live streaming call has been made. §33.5's first-audio and barge-in "
            f"measures cannot be read off a batch verification. Record with:\n  {RECORD_COMMAND}"
        )

    record = json.loads(STREAMING_RECORD.read_text(encoding="utf-8"))
    recording = record["_recording"]
    assert recording["status"] == "recorded", recording
    assert recording["recorded_at"], "a recording with no date is a claim with no evidence"

    # The four things the adapter would be wrong about if the docs were wrong,
    # asserted against what the vendor actually sent. Each maps to a line in
    # `CartesiaSttStream._events` / `CartesiaStreamingTtsProvider.stream`.
    stt_types = {frame.get("type") for frame in record["stt_frames"]}
    assert "transcript" in stt_types, "the adapter branches on type == 'transcript'"
    assert any("is_final" in frame for frame in record["stt_frames"]), (
        "the adapter's only branch is is_final; without it every partial is a turn"
    )
    tts_types = {frame.get("type") for frame in record["tts_frames"]}
    assert tts_types & {"chunk", "done"}, "the adapter branches on chunk/done"


def test_the_call_gate_is_not_told_the_streaming_path_is_verified() -> None:
    """A guard on the guard.

    §33.5's harness reports UNMEASURED for the two latency-shaped measures until
    a real call produces a number. An adapter landing is not a measurement, and
    the failure mode worth blocking is somebody wiring a plausible constant into
    `evaluate()` so the table stops looking empty. The gate must still refuse.
    """
    from sitara_api.voice.call_gate import evaluate

    report = evaluate()
    assert not report.passes
    assert "first_audio_p95_s" in (*report.unmeasured, *report.blocked, *report.failing)
