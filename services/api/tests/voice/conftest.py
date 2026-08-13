"""Voice-note test harness (§33.1, §25.4).

No vendor and no Mongo. The STT and TTS providers here replay RECORDED
exchanges — `tests/voice/fixtures/`, captured from the real Cartesia API by
`tests/voice/record.py` — for the same reason `tests/__fixtures__/today` and
the §32.5 recall vectors are recorded rather than authored: a hand-written
transcript is a transcript no engine produced, and every assertion taken from
it stays green through any regression in the thing that produces it.

`test_no_live_network.py` blocks non-loopback DNS and connect for the whole
suite, so a provider that quietly fell back to a live call would fail loudly
rather than pass slowly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sitara_api.voice.providers.base import (
    SynthesisRequest,
    SynthesisResult,
    Transcription,
    TranscriptionRequest,
    VoiceProviderName,
    VoiceProviderUnavailable,
)

FIXTURES = Path(__file__).parent / "fixtures"

#: 16 kHz mono s16le, per §34.6's binary frame. Any bytes will do for the fake
#: providers — what matters is that the pipeline carries the SAME bytes it was
#: handed, which is what §25.4's "replay plays the original" reduces to.
SAMPLE_PCM = b"\x00\x01" * 16_000  # one second


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json"
    if not path.exists():  # pragma: no cover - the skip message is the point
        pytest.skip(
            f"missing recorded fixture {path.name} — record it with "
            "`CARTESIA_API_KEY=... uv run python -m tests.voice.record`"
        )
    return json.loads(path.read_text(encoding="utf-8"))


class ReplayStt:
    """An STT provider that replays a recorded transcript.

    It records what it was ASKED, not only what it returned: the locale→language
    mapping is the one place this adapter can be wrong in a way no transcript
    reveals, so the tests assert on `calls` as well as on the text.
    """

    name = VoiceProviderName.CARTESIA

    def __init__(self, *transcripts: str, fail: Exception | None = None) -> None:
        self._queue = list(transcripts)
        self._fail = fail
        self.calls: list[TranscriptionRequest] = []

    async def transcribe(self, request: TranscriptionRequest) -> Transcription:
        self.calls.append(request)
        if self._fail is not None:
            raise self._fail
        text = self._queue.pop(0) if self._queue else "aaj ka din kaisa hai"
        return Transcription(
            text=text,
            provider=self.name,
            model="ink-whisper",
            detected_language=request.locale,
            duration_ms=1_000,
        )


class RecordingTts:
    """A TTS provider that records every text it was handed.

    That list is the whole of the second grounding test: §25.4 renders Tara's
    reply "from her TTS with transcript toggle", so if any string reaches this
    adapter that is not the validated turn text, the audio and the transcript
    are two different answers and the toggle is a lie.
    """

    name = VoiceProviderName.CARTESIA

    def __init__(self, *, fail: Exception | None = None) -> None:
        self._fail = fail
        self.texts: list[str] = []
        self.calls: list[SynthesisRequest] = []

    async def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        self.calls.append(request)
        self.texts.append(request.text)
        if self._fail is not None:
            raise self._fail
        return SynthesisResult(
            audio=SAMPLE_PCM,
            sample_rate_hz=16_000,
            provider=self.name,
            model="sonic-3.5",
            voice_id=request.voice_id,
        )


class InMemoryVoiceAssetStore:
    """Stands in for the CSFLE-backed store.

    It is deliberately NOT lenient: `put` refuses a policy/role combination the
    real collection refuses, because a fake that accepts what the real system
    rejects is a defect in the fake — the root CLAUDE.md rule, and the one M5
    broke by taking string ids where §6.4 requires objectId.
    """

    def __init__(self) -> None:
        self.assets: dict[str, dict[str, Any]] = {}
        self.deleted: list[str] = []

    async def put(self, asset: dict[str, Any]) -> str:
        from sitara_api.voice.storage import assert_storable

        assert_storable(asset)
        asset_id = asset.get("_id") or f"asset-{len(self.assets) + 1}"
        self.assets[str(asset_id)] = dict(asset, _id=asset_id)
        return str(asset_id)

    async def get(self, asset_id: str) -> dict[str, Any] | None:
        return self.assets.get(asset_id)

    async def hard_delete(self, asset_id: str) -> bool:
        if asset_id not in self.assets:
            return False
        del self.assets[asset_id]
        self.deleted.append(asset_id)
        return True


@pytest.fixture()
def stt() -> ReplayStt:
    return ReplayStt()


@pytest.fixture()
def tts() -> RecordingTts:
    return RecordingTts()


@pytest.fixture()
def asset_store() -> InMemoryVoiceAssetStore:
    return InMemoryVoiceAssetStore()


__all__ = [
    "FIXTURES",
    "SAMPLE_PCM",
    "InMemoryVoiceAssetStore",
    "RecordingTts",
    "ReplayStt",
    "VoiceProviderUnavailable",
    "load_fixture",
]
