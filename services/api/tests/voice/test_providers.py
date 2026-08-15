"""The adapter contract (§3.2, §3.3) and the frame handling under it (§34.6).

Nothing here calls a vendor: `test_no_live_network.py` blocks non-loopback DNS
and connect for the whole suite, and the Cartesia adapters are exercised over a
transport whose responses are RECORDED — `tests/voice/fixtures/`, captured from
the real API by `tests/voice/record.py`.
"""

from __future__ import annotations

import httpx
import pytest

from sitara_api.voice.audio import (
    FrameError,
    NoteAssembler,
    build_frame,
    duration_ms,
    pcm_to_wav,
    wav_to_pcm,
)
from sitara_api.voice.providers.base import (
    SynthesisRequest,
    TranscriptionRequest,
    VoiceProviderName,
    VoiceProviderUnavailable,
    stt_language_for,
    supported_locales,
    tts_language_for,
)
from sitara_api.voice.providers.cartesia import CartesiaSttProvider, CartesiaTtsProvider
from sitara_api.voice.providers.voices import TARA_VOICES, voice_for

# Only the adapter round-trips are async; the frame and mapping tests are pure.
# A module-level asyncio mark would warn on every one of them.

PCM = b"\x00\x01" * 8_000  # half a second at 16 kHz


# --------------------------------------------------------------------------
# The locale→language map, which is the adapter's one silent failure mode
# --------------------------------------------------------------------------


def test_hinglish_transcribes_into_LATIN_script_not_devanagari() -> None:
    """The finding this milestone would otherwise have shipped.

    `locale.split("-")[0]` sends `hi-Latn` to `hi`, and Ink then returns the
    Indic span in Devanagari — verified live on 13 Aug 2026. Hinglish IS Latin
    script (§2.4), so every Hinglish thread would have filled with the wrong
    script while every accuracy metric stayed green: the transcript is a
    correct transcription, of the right words, in a script the user did not
    choose. Same shape as M6's `moon_nakshatra_note` — right-looking, wrong,
    and invisible to the tests that existed.
    """
    assert stt_language_for("hi-Latn") == "en"
    assert stt_language_for("hi") == "hi"
    assert stt_language_for("en") == "en"

    # And the guard against the "fix" that looks equivalent.
    assert stt_language_for("hi-Latn") != "hi-Latn".split("-")[0]


def test_the_tts_map_is_separate_and_differs_exactly_at_hinglish() -> None:
    """One map serving both directions is how the two get quietly made to
    agree. They genuinely differ: Hinglish is TRANSCRIBED as Latin (`en`) and
    SPOKEN with Hindi intonation (`hi`) — §3.3's "40–60% EN tokens; 'aaj ka
    din', 'rahu kaal' native"."""
    assert tts_language_for("hi-Latn") == "hi"
    assert stt_language_for("hi-Latn") == "en"
    for locale in ("en", "hi"):
        assert tts_language_for(locale) == stt_language_for(locale)


def test_an_unknown_locale_declines_rather_than_guessing() -> None:
    """§2.4: no silent fallback, ever. §3.3 maps eight launch languages and M9
    implements three; the other five decline until their row is built, because
    transcribing Tamil under `hi` would produce confident nonsense."""
    assert supported_locales() == ("en", "hi", "hi-Latn")
    for absent in ("ta", "te", "gu", "mr", "pa", "bn", "xx"):
        with pytest.raises(VoiceProviderUnavailable):
            stt_language_for(absent)


# --------------------------------------------------------------------------
# §34.6's binary frame
# --------------------------------------------------------------------------


def test_a_gap_in_the_sequence_fails_the_note() -> None:
    """The reason `NoteAssembler` exists.

    A note missing its middle still transcribes — into a fluent sentence the
    user never said, which then goes to §9 as their question and gets answered.
    There is no downstream validator that can catch this: §9 checks what TARA
    says, and the fabricated input is on the user's side of the turn.
    """
    assembler = NoteAssembler()
    assembler.add(build_frame(0, PCM))
    assembler.add(build_frame(1, PCM))
    with pytest.raises(FrameError, match="gap"):
        assembler.add(build_frame(3, PCM))  # 2 never arrived


def test_a_truncated_frame_is_refused() -> None:
    """A half sample shifts every subsequent sample by a byte and turns the
    rest of the note into noise — which STT transcribes as *something*."""
    assembler = NoteAssembler()
    with pytest.raises(FrameError, match="16-bit samples"):
        assembler.add(build_frame(0, b"\x00\x01\x02"))
    with pytest.raises(FrameError, match="header"):
        assembler.add(b"\x00\x01")


def test_the_cap_stops_a_pocket_dial_becoming_an_unstorable_document() -> None:
    """MongoDB's document limit is 16 MB and §33.1 puts the bytes in a
    document. The cap is enforced server-side too: a client that ignores it is
    not a client we control."""
    assembler = NoteAssembler(max_duration_ms=100)
    with pytest.raises(FrameError, match="cap"):
        for seq in range(50):
            assembler.add(build_frame(seq, PCM))


def test_frames_reassemble_in_order_to_exactly_what_was_sent() -> None:
    assembler = NoteAssembler()
    chunks = [bytes([i, i]) * 100 for i in range(5)]
    for seq, chunk in enumerate(chunks):
        assembler.add(build_frame(seq, chunk))
    assert assembler.pcm() == b"".join(chunks)
    assert assembler.frame_count == 5


def test_wav_wrapping_never_touches_a_sample() -> None:
    """§25.4's "ORIGINAL recording" survives the container round-trip."""
    wav = pcm_to_wav(PCM, 16_000)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    pcm, rate = wav_to_pcm(wav)
    assert pcm == PCM
    assert rate == 16_000
    assert duration_ms(PCM, 16_000) == 500


def test_a_streaming_wav_with_an_unknown_length_still_reads() -> None:
    """Cartesia's TTS returns `RIFF` with size 0xFFFFFFFF and a `LIST`/`INFO`
    chunk before `data` — verified live. The fixed-offset-44 version of
    `wav_to_pcm` transcribed that metadata as audio."""
    body = pcm_to_wav(PCM, 16_000)
    listed = (
        body[:12]
        + b"LIST" + (4).to_bytes(4, "little") + b"INFO"
        + body[12:]
    )
    streaming = listed[:4] + b"\xff\xff\xff\xff" + listed[8:]
    pcm, rate = wav_to_pcm(streaming)
    assert pcm == PCM and rate == 16_000


# --------------------------------------------------------------------------
# The Cartesia adapters, over a recorded transport
# --------------------------------------------------------------------------


def transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_stt_normalises_inks_response_and_sends_the_mapped_language(
    monkeypatch,
) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["version"] = request.headers.get("Cartesia-Version")
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "type": "transcript",
                "duration": 1.2,
                "language": "en",
                "is_final": True,
                "request_id": "r1",
                "text": "  Mera Rahukaal kab hai aaj?  ",
            },
        )

    provider = CartesiaSttProvider("sk_test")
    monkeypatch.setattr(
        "httpx.AsyncClient", _client_factory(transport(handler))
    )

    result = await provider.transcribe(
        TranscriptionRequest(audio=PCM, sample_rate_hz=16_000, locale="hi-Latn")
    )

    assert result.text == "Mera Rahukaal kab hai aaj?"  # stripped, never reformatted
    assert result.provider is VoiceProviderName.CARTESIA
    assert result.duration_ms == 1200
    assert seen["url"].endswith("/stt")
    assert seen["version"] == "2026-03-01"
    # The §2.4 mapping reaches the vendor, not the raw locale.
    assert b'name="language"\r\n\r\nen' in seen["body"]
    assert b"hi-Latn" not in seen["body"]


@pytest.mark.asyncio
async def test_stt_treats_an_empty_transcript_as_a_failure(monkeypatch) -> None:
    """Handing §9 an empty string runs the whole pipeline on nothing and
    answers a question the user never asked."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"type": "transcript", "text": "   "})

    provider = CartesiaSttProvider("sk_test")
    monkeypatch.setattr("httpx.AsyncClient", _client_factory(transport(handler)))

    with pytest.raises(VoiceProviderUnavailable, match="no transcript"):
        await provider.transcribe(
            TranscriptionRequest(audio=PCM, sample_rate_hz=16_000, locale="en")
        )


@pytest.mark.asyncio
async def test_stt_raises_the_envelopes_code_not_the_vendor_body(monkeypatch) -> None:
    """§34.4/§2.4: an upstream body must never reach a log or a screen."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "quota exceeded for org acme"})

    provider = CartesiaSttProvider("sk_test")
    monkeypatch.setattr("httpx.AsyncClient", _client_factory(transport(handler)))

    with pytest.raises(VoiceProviderUnavailable) as excinfo:
        await provider.transcribe(
            TranscriptionRequest(audio=PCM, sample_rate_hz=16_000, locale="en")
        )
    assert "acme" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_tts_asks_for_exactly_the_ws_binary_frame_format(monkeypatch) -> None:
    """§34.6's frame is 16 kHz mono s16le. Her reply and the user's note are
    then the same format on the wire and in storage — one decoder on the
    client, one codec value in Mongo."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=PCM)

    provider = CartesiaTtsProvider("sk_test")
    monkeypatch.setattr("httpx.AsyncClient", _client_factory(transport(handler)))

    result = await provider.synthesise(
        SynthesisRequest(text="Aaj ka din accha hai.", locale="hi-Latn")
    )

    assert result.audio == PCM
    assert result.sample_rate_hz == 16_000
    body = seen["body"]
    assert body["output_format"] == {
        "container": "raw",
        "encoding": "pcm_s16le",
        "sample_rate": 16_000,
    }
    assert body["language"] == "hi"  # spoken with Hindi intonation (§3.3)
    # Resolved from the LOCALE, not from a value threaded down from settings.
    # hi-Latn deliberately shares hi's voice: Hinglish is spoken Hindi with
    # English words in it (`providers/voices.py`).
    assert body["voice"] == {"mode": "id", "id": TARA_VOICES["hi-Latn"]}
    assert TARA_VOICES["hi-Latn"] == TARA_VOICES["hi"]


@pytest.mark.asyncio
async def test_tts_refuses_to_pick_a_stranger_voice_for_tara() -> None:
    """§2.4/§3.2/CC-008: an unvoiced locale DECLINES.

    The failure this prevents is not silence — it is Tara answering a Tamil
    user fluently in a Hindi woman's voice, with every accuracy metric green.
    A locale earns a voice through the §12 gate, never by falling back to a
    neighbour's.
    """
    provider = CartesiaTtsProvider("sk_test")
    with pytest.raises(VoiceProviderUnavailable, match="no Tara voice for locale"):
        await provider.synthesise(SynthesisRequest(text="vanakkam", locale="ta"))


@pytest.mark.asyncio
async def test_every_launch_locale_has_a_voice() -> None:
    """§2.4 ships a language 100% or not at all, and a language Tara cannot
    speak in is not shipped."""
    for locale in ("en", "hi", "hi-Latn"):
        assert voice_for(locale)


def test_an_unconfigured_key_fails_at_construction_not_mid_turn() -> None:
    """A blank key is "provider down", and the honest moment to say so is
    boot — the same rule `build_pipeline` follows for ANTHROPIC_API_KEY."""
    for factory in (CartesiaSttProvider, CartesiaTtsProvider):
        with pytest.raises(VoiceProviderUnavailable, match="CARTESIA_API_KEY"):
            factory("")


#: Captured BEFORE any monkeypatch: `_client_factory` replaces the name
#: `httpx.AsyncClient`, so a factory that referred to it by name would call
#: itself. That is a RecursionError inside the adapter under test, which reads
#: like a bug in the adapter.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(mock_transport: httpx.MockTransport):
    """`httpx.AsyncClient(...)` with the transport swapped in.

    The adapters construct their own client per call (so a timeout is per
    request), which is the shape `panchang/providers/http.py` uses too.
    """

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=mock_transport, **kwargs)

    return factory


# --------------------------------------------------------------------------
# The recorded exchanges — real vendor responses, replayed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "hi", "hi-Latn"])
def test_the_recorded_response_parses_and_kept_its_script(locale: str) -> None:
    """Replays what Cartesia actually returned on 13 Aug 2026.

    The script assertion is the one a WER number cannot make: a transcript can
    be word-perfect and still be wrong for its locale. `hi-Latn` IS Hinglish
    (§2.4), so Devanagari there is the violation the locale exists to prevent —
    and it is exactly what `locale.split("-")[0]` produces.
    """
    import unicodedata

    from sitara_api.voice.providers.cartesia import _transcription_from
    from tests.voice.conftest import load_fixture

    fixture = load_fixture(f"stt_{locale}")
    assert fixture["stt_language_sent"] == stt_language_for(locale)

    result = _transcription_from(fixture["response"], model="ink-whisper")
    assert result.text

    has_devanagari = any(
        "DEVANAGARI" in unicodedata.name(c, "") for c in result.text if c.isalpha()
    )
    assert has_devanagari is (locale == "hi"), (
        f"{locale}: transcript script does not match the locale — got {result.text!r}"
    )
