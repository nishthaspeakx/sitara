"""Record what Cartesia's STREAMING endpoints actually send (M9-P10b, §25.3).

    CARTESIA_API_KEY=... uv run python -m tests.voice.record_streaming

Companion to `tests/voice/record.py`, which does the same job for the BATCH
endpoints. They are separate scripts because they verify separate claims:
`record.py` scores a synthetic round-trip's accuracy, and this one answers a
narrower and more urgent question — **are the frame shapes in
`voice/providers/cartesia.py`'s streaming half real?**

Why that question is urgent
----------------------------

Everything in the streaming adapters was written from vendor documentation. No
live streaming call has ever been made. The whole test suite is green and every
field name in those two loops could still be wrong, because a suite that never
reaches a vendor cannot disagree with one.

And this is not a cosmetic gap. §33.5 gates whether calls ship on p95
first-response audio and barge-in success, both properties of the streaming path
and of nothing else. "Cartesia is verified" is true of the batch endpoints and
says nothing about either measure.

What this writes, and what makes it useful
-------------------------------------------

`fixtures/streaming_en.json`, holding the RAW frames both sockets sent, before
the adapter interpreted them. Raw is the point: a normalised record would be a
record of what we already believe. `test_streaming_provenance.py` reads this
file and stops skipping once it exists, asserting the four things the adapter
branches on — `type == "transcript"`, `is_final`, and Sonic's `chunk`/`done`.

If a frame name turns out to be different, the fixture is the evidence and the
fix is one line in each loop.

**English only.** CC-010: Ink's streaming endpoint recognises `en` and nothing
else, so `hi`/`hi-Latn` have no streaming recogniser to record. That is the
ruling, not a shortcut — `routing.resolve(STREAMING, "hi")` returns no provider
and this script would have nothing to call.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from sitara_api.voice.providers.base import (
    VoiceProviderUnavailable,
    stt_language_for,
)
from sitara_api.voice.providers.cartesia import (
    CARTESIA_VERSION,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    _ws_url,
)

FIXTURES = Path(__file__).parent / "fixtures"
RECORD = FIXTURES / "streaming_en.json"

#: Cartesia's public voice, NOT Tara's. §3.2's anchor artist is a contracted
#: clone that does not exist yet and CC-008 governs her likeness — same rule
#: and same id `record.py` uses, for the same reason.
BAKEOFF_VOICE_ID = "87748186-23bb-4158-a1eb-332911b0b708"

UTTERANCE = "What does my chart say about starting a new job on Monday?"


async def record_tts(api_key: str) -> tuple[list[dict[str, Any]], bytes, float]:
    """Sonic's websocket, recorded frame by frame.

    Returns the JSON frames, the PCM they carried, and **time to first audio
    byte** — which is not §33.5's measure (that one runs from the user's
    finalised utterance, through §9, to audio leaving for them) but is its
    largest single component and the one a vendor controls.
    """
    import websockets

    frames: list[dict[str, Any]] = []
    audio = bytearray()

    # The adapter's own URL builder and body, so what is recorded is what the
    # adapter sends. Rebuilding the request here would record a different
    # client's conversation.
    url = _ws_url(
        "https://api.cartesia.ai", "/tts/websocket", {"cartesia_version": CARTESIA_VERSION}
    )
    body = {
        "model_id": DEFAULT_TTS_MODEL,
        "transcript": "Saturn is moving through your tenth house today. Go slowly.",
        "voice": {"mode": "id", "id": BAKEOFF_VOICE_ID},
        "language": "en",
        "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 16_000},
        "continue": False,
    }
    started = time.monotonic()
    first_audio: float | None = None
    async with websockets.connect(
        url,
        additional_headers={
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {api_key}",
        },
    ) as socket:
        await socket.send(json.dumps(body))
        async for message in socket:
            if isinstance(message, bytes):
                if first_audio is None:
                    first_audio = time.monotonic() - started
                audio.extend(message)
                frames.append({"type": "<binary>", "byte_length": len(message)})
                continue
            frame = json.loads(message)
            if first_audio is None and frame.get("type") == "chunk":
                first_audio = time.monotonic() - started
            # Redact the payload, keep the SHAPE. §13 keeps vendor payloads out
            # of anything committed, and a base64 blob would make the fixture
            # unreadable while proving nothing the length does not.
            recorded = {k: v for k, v in frame.items() if k != "data"}
            if "data" in frame:
                recorded["data_length"] = len(frame["data"])
                audio.extend(base64.b64decode(frame["data"]))
            frames.append(recorded)
            if frame.get("type") in ("done", "error"):
                break

    return frames, bytes(audio), first_audio or 0.0


async def record_stt(api_key: str, pcm: bytes) -> list[dict[str, Any]]:
    """Ink's websocket, fed Sonic's own output.

    A synthetic round trip, and its limits are `record.py`'s limits: studio
    speech is cleaner than a phone in a kitchen, so anything measured here is a
    FLOOR on the error rate rather than an estimate of it. What it does verify
    honestly is the thing this script exists for — the frame shapes.
    """
    import websockets

    url = _ws_url(
        "https://api.cartesia.ai",
        "/stt/websocket",
        {
            "model": DEFAULT_STT_MODEL,
            "language": stt_language_for("en"),
            "encoding": "pcm_s16le",
            "sample_rate": "16000",
        },
    )
    frames: list[dict[str, Any]] = []

    async with websockets.connect(
        url,
        additional_headers={
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {api_key}",
        },
    ) as socket:

        async def feed() -> None:
            # 100 ms at a time, paced — a call streams in real time and a
            # recogniser fed a whole utterance at once may never emit an
            # interim result, which is exactly the frame we most need to see.
            chunk = 16_000 * 2 // 10
            for offset in range(0, len(pcm), chunk):
                await socket.send(pcm[offset : offset + chunk])
                await asyncio.sleep(0.1)
            await socket.send("finalize")

        pump = asyncio.create_task(feed())
        try:
            async for message in socket:
                if isinstance(message, bytes):
                    frames.append({"type": "<unexpected binary>", "byte_length": len(message)})
                    continue
                frame = json.loads(message)
                frames.append(frame)
                if frame.get("type") in ("done", "error"):
                    break
        finally:
            pump.cancel()

    return frames


async def main() -> int:
    api_key = os.environ.get("CARTESIA_API_KEY")
    if not api_key:
        print("CARTESIA_API_KEY is not set — nothing to record.", file=sys.stderr)
        return 2

    try:
        tts_frames, pcm, first_audio_s = await record_tts(api_key)
        stt_frames = await record_stt(api_key, pcm)
    except (VoiceProviderUnavailable, OSError) as exc:
        print(f"the live check did not complete: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    transcripts = [f.get("text") for f in stt_frames if f.get("type") == "transcript"]
    record = {
        "_recording": {
            "status": "recorded",
            # Stamped from the wall clock at record time. This is the only
            # thing in the file a reader has to trust rather than verify.
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cartesia_version": CARTESIA_VERSION,
            "stt_model": DEFAULT_STT_MODEL,
            "tts_model": DEFAULT_TTS_MODEL,
            "note": (
                "Raw frames from both streaming websockets, payloads redacted to "
                "lengths (§13). Synthetic round trip: Sonic's output fed to Ink, so "
                "any accuracy read off this is a FLOOR, not an estimate. What it "
                "verifies is the frame SHAPES the adapter branches on."
            ),
        },
        "prompt": UTTERANCE,
        "tts_first_audio_seconds": round(first_audio_s, 3),
        "tts_frames": tts_frames,
        "stt_frames": stt_frames,
        "stt_transcripts": transcripts,
    }
    FIXTURES.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {RECORD}")
    print(f"  tts first audio: {first_audio_s:.3f}s  ({len(pcm)} bytes)")
    finals = sum(1 for f in stt_frames if f.get("is_final"))
    print(f"  stt frames: {len(stt_frames)}  finals: {finals}")
    print(f"  heard: {transcripts[-1] if transcripts else '(nothing)'}")
    print()
    print("§33.5 note: this measures a VENDOR round trip, not the gate's")
    print("first-response measure, which runs from the user's finalised utterance")
    print("through §9 to audio leaving for them. Read it as a floor.")
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(asyncio.run(main()))
