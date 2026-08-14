"""The ordering that makes a call's words survivable (M9-P10b, §25.3, §33.1).

`voice/service.py` and `calls/service.py` are the same rule applied to two
different irreplaceable things:

    voice note:  store the ORIGINAL AUDIO  →  transcribe  →  §9  →  synthesise
    live call:   transcribe  →  store the TRANSCRIPT  →  §9  →  synthesise

**Write the thing that cannot be recreated before the thing that can fail.**
A note's irreplaceable thing is the recording, and §28.3 says so out loud
("transcribe-fail → 'send as text?' original audio preserved"). A call's is the
transcript, because call audio is never stored at all — §13, §33.1, and §6.4's
validators on `voice_sessions` and `call_sessions` reject an audio field
structurally.

The failure this file exists to prevent is specific and was reachable until M9-P10b.
§9's `_persist` writes the user's message and the reply TOGETHER, at the end of
the turn. Under that ordering, an LLM outage between "she heard you" and "she
answered" erases what somebody said out loud — permanently, with no audio to
fall back on and no composer to resend from. A typed question survives the same
outage; a spoken one did not.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas import PlaybackPolicy, TranscriptStatus

from sitara_api.calls.service import CallTurnService
from sitara_api.chat_orchestration.store import InMemoryMessageStore
from sitara_api.chat_orchestration.types import TurnRequest
from sitara_api.voice.providers.base import VoiceProviderName, VoiceProviderUnavailable
from tests.chat.conftest import CONVERSATION_ID, USER_ID, build_env

NOW = dt.datetime(2026, 8, 14, 9, 30, tzinfo=dt.UTC)
SPOKEN = "what is Saturn doing today?"


def _request(text: str = SPOKEN, locale: str = "en") -> TurnRequest:
    return TurnRequest(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        text=text,
        locale=locale,
        now=NOW,
    )


class DeadPipeline:
    """§9, down. The shape of a provider outage, not of a validator failure —
    §8 is explicit that those degrade differently and only one queues a human."""

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, request: TurnRequest, *, on_stage=None):  # noqa: ANN001, ANN201
        self.calls += 1
        raise RuntimeError("anthropic is down")


class DeadTts:
    """Synthesis, down. §8's ladder: voice fails, text continues.

    `name` is the ENUM, not the string that happens to spell it. A fake whose
    shape does not satisfy `StreamingTtsProvider` is a fake that could accept
    what the real provider rejects — the root rule, and `pyright` is what makes
    it mechanical here rather than a thing to remember.
    """

    name = VoiceProviderName.CARTESIA

    def stream(self, request):  # noqa: ANN001, ANN201
        async def _fail():  # noqa: ANN202
            raise VoiceProviderUnavailable("sonic is down")
            yield b""  # pragma: no cover - makes this an async generator

        return _fail()


@pytest.mark.asyncio
async def test_the_transcript_is_in_the_thread_before_the_pipeline_runs() -> None:
    """The whole milestone, in one assertion.

    §9 dies. The user's spoken sentence must still be in `messages`, because it
    was written before §9 was called — not because anything recovered it, which
    nothing could.
    """
    store = InMemoryMessageStore()
    pipeline = DeadPipeline()
    service = CallTurnService(pipeline=pipeline, store=store, tts=None)

    spoken = await service.answer(_request())

    assert pipeline.calls == 1, "the pipeline really was reached and really did fail"
    assert spoken.turn is None
    assert spoken.failure == ("SYS_UNAVAILABLE", "errors.sys.unavailable")

    saved = [m for m in store.messages if m["role"] == "user"]
    assert [m["content"] for m in saved] == [SPOKEN]
    assert spoken.user_message_id, "the caller gets the id of the surviving turn"


@pytest.mark.asyncio
async def test_a_spoken_turn_is_not_written_as_a_typed_one() -> None:
    """§33.1's two fields, and why the defaults are wrong here.

    `not_applicable` means "this was never spoken" and `text_only` means "there
    is no audio and no control". Both are false for a call: it WAS spoken, and
    its audio was never stored by design rather than by absence.
    `transcript_only` is the member `voice.json` defines for exactly this —
    "the honest state, not a degraded one".

    Getting this wrong writes a call into the thread as though the user had
    typed it, which no validator would catch and which the transcript screen
    would render without complaint.
    """
    store = InMemoryMessageStore()
    service = CallTurnService(pipeline=DeadPipeline(), store=store, tts=None)

    await service.answer(_request())

    row = next(m for m in store.messages if m["role"] == "user")
    assert row["transcript_status"] == TranscriptStatus.READY.value
    assert row["playback_policy"] == PlaybackPolicy.TRANSCRIPT_ONLY.value
    # §25.4's promise rests on this being absent: there is no original to replay
    # because there never was one.
    assert row["source_audio_asset_id"] is None
    assert row["source_audio_expires_at"] is None


@pytest.mark.asyncio
async def test_the_user_turn_is_written_once_and_not_twice() -> None:
    """The other half of committing early.

    `_persist` writes the user's message at the end of a normal turn. If the
    call service commits it first and the pipeline writes it again, every call
    doubles every question in the transcript — a regression that looks like a
    rendering bug and is a storage one.
    """
    env = build_env()
    env.llm.script(
        "generation",
        "Saturn is moving through your 10th house today. Go slowly. "
        "[[fact:transit.saturn.house]]",
    )
    service = CallTurnService(pipeline=env.pipeline, store=env.store, tts=None)

    spoken = await service.answer(_request())

    assert spoken.turn is not None, "the real §9 pipeline answered"
    user_rows = [m for m in env.store.messages if m["role"] == "user"]
    assert len(user_rows) == 1, [m["content"] for m in user_rows]
    assert user_rows[0]["content"] == SPOKEN


@pytest.mark.asyncio
async def test_a_call_turn_visits_the_same_stages_as_a_typed_one() -> None:
    """§34.6's premise: a typed message and a spoken one are one event.

    Not "a similar pipeline" — `pipeline.run`, the method `POST /v1/chat/turn`
    calls. The moment there are two orchestrations there are two sets of
    validators to keep in step, and the one that drifts is the one nobody is
    looking at. `tests/voice/test_grounding_parity.py` holds this line for
    voice notes; this is the call's half of it.

    The two sequences are compared against EACH OTHER rather than against a
    list written here. A hardcoded list is a third declaration of §9's stage
    order that would have to be remembered when the order changes — and this
    test would then pass while asserting the wrong thing, which is the failure
    mode it exists to catch.
    """
    reply = (
        "Saturn is moving through your 10th house today. Go slowly. "
        "[[fact:transit.saturn.house]]"
    )

    typed_env = build_env()
    typed_env.llm.script("generation", reply)
    typed: list[str] = []
    await typed_env.pipeline.run(
        _request(), on_stage=lambda stage: typed.append(stage.value)
    )

    call_env = build_env()
    call_env.llm.script("generation", reply)
    service = CallTurnService(
        pipeline=call_env.pipeline, store=call_env.store, tts=None
    )
    spoken: list[str] = []
    await service.answer(_request(), on_stage=lambda stage: spoken.append(stage.value))

    assert spoken == typed, "a spoken turn took a different path through §9"
    assert typed, "the probe saw nothing at all — a green test over an empty list"


@pytest.mark.asyncio
async def test_synthesis_dying_never_costs_the_answer() -> None:
    """§8, §30.1: text always works.

    Her reply is already validated and already stored by the time synthesis is
    attempted. A dead synthesiser is a call that becomes a chat, never a turn
    that is lost — and `speak` raising is the honest signal for that, not a
    silent empty stream that would read as "she said nothing".
    """
    env = build_env()
    env.llm.script(
        "generation",
        "Saturn is moving through your 10th house today. Go slowly. "
        "[[fact:transit.saturn.house]]",
    )
    service = CallTurnService(pipeline=env.pipeline, store=env.store, tts=DeadTts())

    spoken = await service.answer(_request())
    assert spoken.turn is not None

    with pytest.raises(VoiceProviderUnavailable):
        async for _ in service.speak(spoken.turn, locale="en"):
            pass

    assert [m["role"] for m in env.store.messages] == ["user", "assistant"], (
        "both sides of the exchange survived the synthesiser"
    )


@pytest.mark.asyncio
async def test_synthesis_reads_the_presented_turn_and_never_a_draft() -> None:
    """The outbound half of "voice is not a §9 bypass".

    If `speak` read the model's draft rather than the presented turn, the audio
    would carry the sentence grounding REJECTED while the caption showed the one
    it accepted — and no validator downstream could see the difference, because
    by the time grounding runs the draft is already at the synthesiser.

    Checked by making the two texts differ: the draft carries a citation marker
    and the presented turn does not, so a synthesiser handed the wrong string
    would speak `[[fact:…]]` out loud.
    """
    env = build_env()
    draft = (
        "Saturn is moving through your 10th house today. Go slowly. "
        "[[fact:transit.saturn.house]]"
    )
    env.llm.script("generation", draft)

    spoken_texts: list[str] = []

    class RecordingTts:
        name = VoiceProviderName.CARTESIA

        def stream(self, request):  # noqa: ANN001, ANN201
            spoken_texts.append(request.text)

            async def _chunks():  # noqa: ANN202
                yield b"\x00\x01"

            return _chunks()

    service = CallTurnService(
        pipeline=env.pipeline, store=env.store, tts=RecordingTts(), voice_id="v1"
    )
    spoken = await service.answer(_request())
    assert spoken.turn is not None
    async for _ in service.speak(spoken.turn, locale="en"):
        pass

    assert spoken_texts, "the synthesiser was reached"
    assert "[[fact:" not in spoken_texts[0], "a citation marker was spoken aloud"
    assert spoken_texts[0] != draft


@pytest.mark.asyncio
async def test_words_that_lose_the_one_in_flight_race_are_still_recorded() -> None:
    """§7.3 caps a call at one in-flight utterance. It does not license losing one.

    Found in review. Speaking over her is not an edge case — §25.3 makes it the
    feature ("barge-in = just speak") — so a second utterance arriving while the
    first turn is still running is what a WORKING call produces. The media
    socket dropped that frame, and with call audio never stored (§13/§33.1) the
    words went with it.

    The turn is still not answered; §7.3 is right about that. What changed is
    that the sentence reaches the thread either way, so the user can see what
    they said and ask again. Same trade `answer` makes when §9 dies.
    """
    store = InMemoryMessageStore()
    service = CallTurnService(pipeline=DeadPipeline(), store=store, tts=None)

    # The utterance that loses the race takes this path directly — the socket
    # calls `commit_utterance` without `answer`.
    first = await service.commit_utterance(
        conversation_id=CONVERSATION_ID,
        text="and what about Thursday?",
        locale="en",
        now=NOW,
    )

    assert first
    rows = [m for m in store.messages if m["role"] == "user"]
    assert [m["content"] for m in rows] == ["and what about Thursday?"]
    # Still a spoken turn, not a typed one (§33.1).
    assert rows[0]["playback_policy"] == PlaybackPolicy.TRANSCRIPT_ONLY.value
