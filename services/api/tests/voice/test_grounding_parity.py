"""Voice is not a bypass (§9, §25.4, §33.1).

The acceptance test for this milestone, and it points in two directions —
because "voice bypasses the validators" has two quite different shapes and only
one of them is obvious.

**Inbound.** A question asked out loud is the same question typed. §34.6 already
says so at the protocol level ("a typed message is the same event a spoken one
produces after STT: a finalised caption"), and §9's pipeline must therefore see
no difference at all. A voice path that reached the model by another door would
be a second orchestration to keep the validators in step with, and the one that
drifts is the one nobody is looking at.

**Outbound, and this is the subtle one.** §25.4 has Tara reply as a voice note
"rendered from her TTS with transcript toggle". If synthesis ran on the model's
draft rather than on the validated turn, the audio would carry the sentence
grounding rejected while the toggle showed the sentence it accepted — two
different answers in one bubble, with the honest-looking one on the screen and
the fabricated one in the user's ear. Nothing in the grounding validator can see
that: by the time it runs, the draft has already been handed to the synthesiser.

So the rule is not "TTS happens after validation" as an ordering someone
maintains. It is that the synthesiser is only ever reachable with the text the
presenter produced, and these tests hold that line from the outside.
"""

from __future__ import annotations

import pytest

from sitara_api.chat_orchestration.types import Stage
from sitara_api.voice.service import VoiceNoteRequest, VoiceNoteService
from tests.chat.conftest import SATURN_FACT_ID, VENUS_FACT_ID, build_env, run_turn
from tests.voice.conftest import (
    SAMPLE_PCM,
    InMemoryVoiceAssetStore,
    RecordingTts,
    ReplayStt,
)

pytestmark = pytest.mark.asyncio

# The served payload holds Saturn in the 10th and nothing else. Every sentence
# below that says otherwise is a fabrication the validator has to catch —
# whether the question that provoked it was typed or spoken.
QUESTION = "What's Saturn doing for me today?"
FABRICATED = (
    "Right now Venus is transiting your 7th house, so relationships feel warm today "
    f"[[{VENUS_FACT_ID}]]."
)
WRONG_NUMBER = f"Saturn is moving through your 4th house today [[{SATURN_FACT_ID}]]."
GROUNDED = (
    "Right now Saturn is moving through your 10th house, "
    f"so work themes rise today [[{SATURN_FACT_ID}]]."
)


def build_voice(env, *, transcript: str, tts: RecordingTts | None = None, **kwargs):
    """A voice service over the SAME pipeline the text path uses.

    Note what is not here: no second pipeline, no second validator set, no
    "voice mode" flag on the turn. The service transcribes and then calls
    `pipeline.run` — the same method `POST /v1/chat/turn` calls.

    An asset store is wired by DEFAULT because a deployment without one is not
    a real state: §33.1's storage is what makes voice notes shippable at all.
    Defaulting it off here would have quietly turned every synthesis assertion
    below into a test of nothing.
    """
    kwargs.setdefault("asset_store", InMemoryVoiceAssetStore())
    return VoiceNoteService(
        stt=ReplayStt(transcript),
        tts=tts if tts is not None else RecordingTts(),
        pipeline=env.pipeline,
        **kwargs,
    )


def stored_audio(asset: dict) -> bytes:
    """`bson.Binary.__eq__` returns False against plain `bytes` — it compares
    subtype too, and only to another Binary. So `stored["audio"] == pcm` is
    False for identical bytes, which is a trap worth naming once here rather
    than meeting again in a production equality check that never fires."""
    return bytes(asset["audio"])


async def speak(env, service: VoiceNoteService, **overrides):
    from tests.chat.conftest import CONVERSATION_ID, NOW, USER_ID

    request = VoiceNoteRequest(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        audio=overrides.pop("audio", SAMPLE_PCM),
        sample_rate_hz=16_000,
        locale=overrides.pop("locale", "en"),
        client_message_id="c1",
        now=overrides.pop("now", NOW),
        profile=overrides.pop("profile", env.profile),
        place_label="Delhi",
        **overrides,
    )
    return await service.handle(request)


# --------------------------------------------------------------------------
# Inbound: the transcript meets every validator the keyboard does
# --------------------------------------------------------------------------


async def test_a_spoken_question_and_a_typed_one_take_the_same_ladder() -> None:
    """The same fabrication, twice, from two doors — and one outcome.

    Both runs script the identical model failure: fabricate, then fabricate
    again. §9 allows exactly one corrective regeneration, so both must land on
    the safe fallback line with a review row — same regeneration count, same
    message key, same empty fact list, same fabricated text nowhere near the
    user. Asserting the two RESULTS match is stronger than asserting the voice
    one is correct: it cannot pass by the voice path having its own idea of
    what correct is.
    """
    typed_env = build_env()
    typed_env.llm.script("generate", FABRICATED, WRONG_NUMBER)
    typed = await run_turn(typed_env, QUESTION)

    spoken_env = build_env()
    spoken_env.llm.script("generate", FABRICATED, WRONG_NUMBER)
    service = build_voice(spoken_env, transcript=QUESTION)
    spoken = await speak(spoken_env, service)

    assert spoken.transcript == QUESTION
    for field in ("text", "message_key", "regenerations", "review_queued", "fact_ids"):
        assert getattr(spoken.turn, field) == getattr(typed, field), field

    assert spoken.turn.message_key == "chat.fallback.safe_line"
    assert spoken.turn.review_queued
    assert "Venus" not in spoken.turn.text
    assert "4th house" not in spoken.turn.text
    assert spoken.turn.fact_ids == ()

    # The ladder does not loop, and it does not loop a second time for voice.
    assert len(spoken_env.trace.spans_for(Stage.GENERATION)) == 2
    assert spoken_env.review_queue.entries[0].stage is Stage.GROUNDING


async def test_a_spoken_question_runs_every_stage_the_typed_one_runs() -> None:
    """Stage-for-stage, not merely outcome-for-outcome.

    A voice path could produce the right answer while skipping the L1 safety
    pre-check or the fear-selling lint — the fabrication tests above would all
    still pass. §9's stage order IS the mandatory pipeline, so the honest
    assertion is that the spoken turn visited the same stages in the same
    order.
    """
    typed_env = build_env()
    typed_env.llm.script("generate", GROUNDED)
    await run_turn(typed_env, QUESTION)
    typed_stages = [e["stage"] for e in typed_env.trace.events if "stage" in e]

    spoken_env = build_env()
    spoken_env.llm.script("generate", GROUNDED)
    await speak(spoken_env, build_voice(spoken_env, transcript=QUESTION))
    spoken_stages = [e["stage"] for e in spoken_env.trace.events if "stage" in e]

    assert spoken_stages == typed_stages


async def test_a_transcript_carrying_a_claim_is_still_only_a_QUESTION() -> None:
    """A user may SAY anything; grounding gates what Tara says back.

    Worth pinning because it is the one way this test file could be written
    wrong: cite-or-die constrains the reply, not the user's own words, so a
    voice note in which the user asserts an astrological claim must not be
    rejected — it must be answered, and the ANSWER must be grounded.
    """
    env = build_env()
    env.llm.script("generate", GROUNDED)
    claim = "I read that Saturn is in my 7th house right now, is that why work is hard?"

    result = await speak(env, build_voice(env, transcript=claim))

    assert result.transcript == claim
    assert not result.turn.review_queued
    assert result.turn.fact_ids == (SATURN_FACT_ID,)
    # She answered from the served fact, not from the premise she was handed.
    assert "10th house" in result.turn.text


# --------------------------------------------------------------------------
# Outbound: the synthesiser only ever sees validated text
# --------------------------------------------------------------------------


async def test_the_synthesiser_never_receives_a_rejected_draft() -> None:
    """§25.4's transcript toggle must show the words the audio says.

    The model fabricates twice, so the turn falls back. If synthesis were wired
    to the draft, the fabricated sentence would be in the user's ear while the
    toggle showed the fallback line. `RecordingTts.texts` is every string that
    reached the adapter, so this asserts on the whole history rather than on
    the final call.
    """
    env = build_env()
    env.llm.script("generate", FABRICATED, WRONG_NUMBER)
    tts = RecordingTts()

    result = await speak(env, build_voice(env, transcript=QUESTION, tts=tts))

    assert FABRICATED not in tts.texts
    assert WRONG_NUMBER not in tts.texts
    for spoken in tts.texts:
        assert "Venus" not in spoken and "4th house" not in spoken
    assert tts.texts == [result.turn.text]


async def test_the_synthesised_audio_and_the_transcript_are_one_text() -> None:
    """The happy path, and the invariant stated positively.

    Exactly one synthesis, of exactly the presented turn text — the string the
    bubble renders. Not the raw generation (which still carries `[[fact:…]]`
    markers), because audio reading citation markers aloud would be its own
    defect, and not a re-generation.
    """
    env = build_env()
    env.llm.script("generate", GROUNDED)
    tts = RecordingTts()

    result = await speak(env, build_voice(env, transcript=QUESTION, tts=tts))

    assert len(tts.texts) == 1
    assert tts.texts[0] == result.turn.text
    assert "[[" not in tts.texts[0]
    assert SATURN_FACT_ID not in tts.texts[0]
    assert result.tts_audio_asset_id is not None


async def test_a_failed_synthesis_never_costs_the_user_the_answer() -> None:
    """§8/§30.1: text always works. TTS is an enhancement of a turn that has
    already been validated and stored, so a synthesis outage must degrade to a
    text bubble rather than losing the reply she already gave."""
    from sitara_api.voice.providers.base import VoiceProviderUnavailable

    env = build_env()
    env.llm.script("generate", GROUNDED)
    tts = RecordingTts(fail=VoiceProviderUnavailable("sonic down"))

    result = await speak(env, build_voice(env, transcript=QUESTION, tts=tts))

    assert result.turn.text.startswith("Right now Saturn is moving")
    assert result.tts_audio_asset_id is None
    assert not result.turn.review_queued  # an outage is not a safety event (§8)


async def test_a_failed_transcription_keeps_the_recording_and_asks(
    asset_store,
) -> None:
    """§28.3's failure row, verbatim: "transcribe-fail → 'send as text?'
    original audio preserved". The note is not silently dropped and neither is
    the audio — the user can still hear what they said, and §9 is never run on
    an empty string."""
    from sitara_schemas import PlaybackPolicy, TranscriptStatus

    from sitara_api.voice.providers.base import VoiceProviderUnavailable

    env = build_env()
    service = VoiceNoteService(
        stt=ReplayStt(fail=VoiceProviderUnavailable("ink down")),
        tts=RecordingTts(),
        pipeline=env.pipeline,
        asset_store=asset_store,
    )

    result = await speak(env, service)

    assert result.turn is None
    assert result.transcript_status is TranscriptStatus.FAILED
    assert result.source_audio_asset_id is not None
    assert result.playback_policy is PlaybackPolicy.ORIGINAL_AUDIO
    stored = await asset_store.get(result.source_audio_asset_id)
    assert stored is not None and stored_audio(stored) == SAMPLE_PCM
    # The model was never asked to answer nothing.
    assert not env.trace.spans_for(Stage.GENERATION)


async def test_the_stored_audio_is_the_bytes_that_arrived(asset_store) -> None:
    """§25.4's promise reduced to one assertion: what comes back out is what
    went in. No transcode, no normalisation, no re-encode — the received PCM,
    byte for byte, which is the cheapest way to keep "the ORIGINAL recording"
    true rather than nearly true."""
    env = build_env()
    env.llm.script("generate", GROUNDED)
    audio = bytes(range(256)) * 64

    result = await speak(
        env,
        build_voice(env, transcript=QUESTION, asset_store=asset_store),
        audio=audio,
    )

    stored = await asset_store.get(result.source_audio_asset_id)
    assert stored_audio(stored) == audio


async def test_taras_reply_is_never_stored_as_the_users_own_audio(asset_store) -> None:
    """The §25.4 substitution, refused structurally.

    "Replay plays the user's ORIGINAL recording, never a TTS reconstruction."
    The two assets exist on one message row, so the way this goes wrong is a
    user bubble whose source-audio id points at the synthesised asset. The
    store refuses `synthesised` on anything the user said, so the wrong wiring
    raises rather than shipping a bubble that plays Tara's voice back to a user
    as their own.
    """
    from sitara_schemas import PlaybackPolicy

    env = build_env()
    env.llm.script("generate", GROUNDED)
    result = await speak(
        env, build_voice(env, transcript=QUESTION, asset_store=asset_store)
    )

    assert result.source_audio_asset_id != result.tts_audio_asset_id
    assert result.playback_policy is PlaybackPolicy.ORIGINAL_AUDIO

    user_asset = await asset_store.get(result.source_audio_asset_id)
    with pytest.raises(ValueError, match="synthesised"):
        await asset_store.put(dict(user_asset, _id="forged", role="user",
                                   playback_policy=PlaybackPolicy.SYNTHESISED.value))
