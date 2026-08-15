"""One voice note, end to end (§33.1, §25.4, §28.3).

The order of operations here is the whole design, and every step is placed
where it is for a reason that has already cost someone something somewhere:

1. **Store the original first** — before STT, before §9. A note whose
   transcription fails must still be replayable (§28.3: "transcribe-fail →
   'send as text?' original audio preserved"), and storing after a successful
   transcript is how you lose exactly the recordings the user most wants back.
   Unless the account is in §33.1's ephemeral mode, in which case it is never
   written at all — see `delete_after_transcription` below.

2. **Transcribe.**

3. **Run the SAME §9 pipeline** the keyboard runs. Not a variant, not a mode:
   `pipeline.run`, the method `POST /v1/chat/turn` calls. §34.6's premise is
   that a typed message and a transcribed one are one event, and the moment
   there are two orchestrations there are two sets of validators to keep in
   step. `tests/voice/test_grounding_parity.py` asserts the two paths visit
   the same stages in the same order.

4. **Synthesise from the PRESENTED turn text** — after §9 has finished, from
   `TurnResult.text`, which is post-validation and citation-free. This is the
   outbound half of "voice is not a bypass": synthesis reading a draft would
   put the sentence grounding rejected into the user's ear while the §25.4
   transcript toggle showed the sentence it accepted. There is no expression
   in this module that could hand the synthesiser anything else.

A failure in step 4 never costs the user step 3's answer (§8, §30.1: text
always works).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

from sitara_schemas import (
    SOURCE_AUDIO_RETENTION_DAYS,
    PlaybackPolicy,
    TranscriptStatus,
)

from sitara_api.chat_orchestration.types import BirthProfile, TurnRequest, TurnResult
from sitara_api.voice import pronunciation
from sitara_api.voice.audio import duration_ms as pcm_duration_ms
from sitara_api.voice.providers.base import (
    SttProvider,
    SynthesisRequest,
    TranscriptionRequest,
    TtsProvider,
    VoiceProviderUnavailable,
    supported_locales,
)
from sitara_api.voice.storage import build_asset

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceNoteRequest:
    user_id: str
    conversation_id: str
    audio: bytes
    sample_rate_hz: int
    locale: str
    client_message_id: str
    now: dt.datetime
    profile: BirthProfile
    place_label: str | None = None
    quoted_message_id: str | None = None
    #: §33.1's global setting: "delete my audio after transcription" switches
    #: the account to ephemeral voice-input mode. Ephemeral means the asset is
    #: NEVER WRITTEN — not written and then cleaned up. A row that exists for a
    #: moment is a row in a backup, a replica and an oplog.
    delete_after_transcription: bool = False
    #: §33.1: 30 days "by default", so the caller may carry a shorter one.
    retention_days: int = SOURCE_AUDIO_RETENTION_DAYS


@dataclass(frozen=True)
class VoiceNoteResult:
    """What the socket needs to draw the exchange.

    `turn` is None when transcription failed: §28.3 keeps the audio and offers
    "send as text?", and running §9 on an empty string would answer a question
    the user never asked.
    """

    transcript: str | None
    transcript_status: TranscriptStatus
    playback_policy: PlaybackPolicy
    source_audio_asset_id: str | None
    source_audio_expires_at: dt.datetime | None
    duration_ms: int
    turn: TurnResult | None = None
    tts_audio_asset_id: str | None = None
    tts_duration_ms: int | None = None


class VoiceNoteService:
    def __init__(
        self,
        *,
        stt: SttProvider,
        tts: TtsProvider,
        pipeline: Any,
        asset_store: Any = None,
        environment: str = "dev",
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._pipeline = pipeline
        self._assets = asset_store
        # §3.4: outside dev/test only REVIEWED overrides are served. Drafts are
        # audible in dev on purpose — a dictionary nobody can hear is one
        # nobody can review.
        self._environment = environment

    async def handle(
        self,
        request: VoiceNoteRequest,
        *,
        on_stage: Any = None,
    ) -> VoiceNoteResult:
        """`on_stage` is forwarded verbatim to the pipeline (§9).

        Not wrapped, not filtered: the socket's presence mapping keys off §9's
        real stage names, and a voice path that renamed or synthesised them
        would be animating a presence state nobody designed — which is the
        thing `STAGE_PRESENCE` being a partial map exists to prevent.
        """
        if request.locale not in supported_locales():
            # §2.4: no silent fallback, ever. Declining is the honest answer;
            # transcribing into a neighbouring language is not.
            raise VoiceProviderUnavailable(
                f"voice notes are not available in {request.locale!r} (§2.4)"
            )

        duration = pcm_duration_ms(request.audio, request.sample_rate_hz)

        # -- 1. the original, before anything can fail ----------------------
        source_asset_id: str | None = None
        expires_at: dt.datetime | None = None
        if request.delete_after_transcription:
            policy = PlaybackPolicy.TRANSCRIPT_ONLY
        else:
            policy = PlaybackPolicy.ORIGINAL_AUDIO
            source_asset_id, expires_at = await self._store_original(request, duration)
            if source_asset_id is None:
                # No store wired (a unit test, a degraded deploy). The bubble
                # must not promise playback it cannot deliver.
                policy = PlaybackPolicy.TRANSCRIPT_ONLY

        # -- 2. transcribe --------------------------------------------------
        try:
            transcription = await self._stt.transcribe(
                TranscriptionRequest(
                    audio=request.audio,
                    sample_rate_hz=request.sample_rate_hz,
                    locale=request.locale,
                )
            )
        except VoiceProviderUnavailable:
            logger.warning("stt unavailable; the note is kept and offered as text (§28.3)")
            return VoiceNoteResult(
                transcript=None,
                transcript_status=TranscriptStatus.FAILED,
                playback_policy=policy,
                source_audio_asset_id=source_asset_id,
                source_audio_expires_at=expires_at,
                duration_ms=duration,
            )

        # -- 3. the same §9 pipeline the keyboard runs ----------------------
        turn = await self._pipeline.run(
            TurnRequest(
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                text=transcription.text,
                locale=request.locale,
                now=request.now,
                profile=request.profile,
                place_label=request.place_label,
                quoted_message_id=request.quoted_message_id,
            ),
            on_stage=on_stage,
        )

        # -- 4. her reply, from the VALIDATED text --------------------------
        tts_asset_id, tts_duration = await self._synthesise_reply(request, turn)

        return VoiceNoteResult(
            transcript=transcription.text,
            transcript_status=TranscriptStatus.READY,
            playback_policy=policy,
            source_audio_asset_id=source_asset_id,
            source_audio_expires_at=expires_at,
            duration_ms=transcription.duration_ms or duration,
            turn=turn,
            tts_audio_asset_id=tts_asset_id,
            tts_duration_ms=tts_duration,
        )

    # -- steps, kept small enough to read -----------------------------------

    async def _store_original(
        self, request: VoiceNoteRequest, duration: int
    ) -> tuple[str | None, dt.datetime | None]:
        if self._assets is None:
            return None, None
        asset = build_asset(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            message_id=None,
            role="user",
            audio=request.audio,
            sample_rate_hz=request.sample_rate_hz,
            duration_ms=duration,
            playback_policy=PlaybackPolicy.ORIGINAL_AUDIO,
            retention_days=request.retention_days,
            now=request.now,
        )
        return await self._assets.put(asset), asset["expires_at"]

    async def _synthesise_reply(
        self, request: VoiceNoteRequest, turn: TurnResult
    ) -> tuple[str | None, int | None]:
        """§25.4's voice-adoption engine, and the one text it may ever be given.

        `turn.text` is what the presenter produced: in-locale, citation-free,
        and already past grounding, language-quality and safety-post. Any other
        string reaching the synthesiser would be audio the validators never saw.
        """
        if self._assets is None:
            return None, None
        # §3.4's overrides are applied HERE and nowhere else — on the way into
        # the synthesiser, after `turn.text` has been stored and after it has
        # crossed the wire as the transcript. A respelling that reached either
        # would put "raahoo kaal" in the user's own thread.
        spoken = pronunciation.apply(turn.text, request.locale, environment=self._environment)
        try:
            synthesis = await self._tts.synthesise(
                SynthesisRequest(
                    text=spoken,
                    locale=request.locale,
                )
            )
        except VoiceProviderUnavailable:
            # §8: an outage degrades the bubble to text. It is not a safety
            # event and it does not queue a human — she already answered.
            logger.warning("tts unavailable; her reply stays a text bubble (§30.1)")
            return None, None

        duration = pcm_duration_ms(synthesis.audio, synthesis.sample_rate_hz)
        asset = build_asset(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            message_id=None,
            role="tara",
            audio=synthesis.audio,
            sample_rate_hz=synthesis.sample_rate_hz,
            duration_ms=duration,
            playback_policy=PlaybackPolicy.SYNTHESISED,
            retention_days=request.retention_days,
            now=request.now,
        )
        return await self._assets.put(asset), duration
