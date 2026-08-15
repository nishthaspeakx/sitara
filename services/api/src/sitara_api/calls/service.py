"""One call turn, end to end (§25.3, §9, §33.1).

The order here is the whole design, exactly as `voice/service.py`'s is, and it
differs from the voice-note order in one way that matters more than everything
else in this file:

    voice note:  store the ORIGINAL AUDIO  →  transcribe  →  §9  →  synthesise
    live call:   transcribe  →  store the TRANSCRIPT  →  §9  →  synthesise

Both are the same rule — **write the thing that cannot be recreated before the
thing that can fail** — applied to different irreplaceable things. A note's
irreplaceable thing is the recording (§28.3: "transcribe-fail → 'send as text?'
original audio preserved"). A call's is the transcript, because call audio is
never stored at all (§13, §33.1, and §6.4's validators on `voice_sessions` and
`call_sessions` reject an audio field structurally).

That is not a theoretical difference. §9's `_persist` writes the user's message
and the reply together, at the END of the turn. Under that ordering, an LLM
outage between "she heard you" and "she answered" erases what somebody said out
loud, permanently, with no audio to fall back on and no composer to resend
from. `commit_utterance` is what stops it, and `TurnRequest.user_message_id` is
what keeps the pipeline from then writing the turn twice.

Synthesis reads the PRESENTED turn text and nothing else — the outbound half of
"voice is not a §9 bypass", identical to the voice-note rule and asserted from
outside by `tests/voice/test_grounding_parity.py`. If it read the model's draft,
the audio would carry the sentence grounding REJECTED while the caption showed
the one it accepted, and no validator downstream could see the difference.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from sitara_schemas import PlaybackPolicy, TranscriptStatus

from sitara_api.chat_orchestration.store import build_message
from sitara_api.chat_orchestration.types import TurnRequest, TurnResult
from sitara_api.voice import pronunciation
from sitara_api.voice.providers.base import (
    StreamingTtsProvider,
    SynthesisRequest,
    VoiceProviderUnavailable,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpokenTurn:
    """What a finalised utterance produced.

    `user_message_id` is populated even when `turn` is None — that is the
    invariant this whole module exists for. A failed turn still leaves the
    user's words in the thread, which is what makes §25.3's handoff "with full
    transcript continuity" true rather than aspirational.
    """

    user_message_id: str
    turn: TurnResult | None = None
    failure: tuple[str, str] | None = None


class CallTurnService:
    def __init__(
        self,
        *,
        pipeline: Any,
        store: Any,
        tts: StreamingTtsProvider | None,
        voice_id: str | None = None,
        environment: str = "dev",
    ) -> None:
        self._pipeline = pipeline
        self._store = store
        self._tts = tts
        self._voice_id = voice_id
        # §3.4: outside dev/test only REVIEWED pronunciation overrides are
        # served. Same rule and same single call site as the voice-note path.
        self._environment = environment

    # -- 1. the words, before anything that can fail ------------------------

    async def commit_utterance(
        self, *, conversation_id: str, text: str, locale: str, now: dt.datetime
    ) -> str:
        """Write the user's spoken turn to the thread. Nothing may precede it.

        `transcript_only`, not `text_only`. The distinction is §33.1's and it
        is load-bearing on this path: `text_only` means "a typed message; there
        is no audio and no control", which would render a call in the thread as
        though the user had used the keyboard. `transcript_only` is the member
        `voice.json` defines for audio that was never stored — "the honest
        state, not a degraded one" — and a call's audio is never stored by
        design rather than by expiry.
        """
        return await self._store.save_message(
            build_message(
                conversation_id=conversation_id,
                role="user",
                content=text,
                locale=locale,
                now=now,
                transcript_status=TranscriptStatus.READY.value,
                playback_policy=PlaybackPolicy.TRANSCRIPT_ONLY.value,
            )
        )

    # -- 2. the same §9 pipeline the keyboard runs --------------------------

    async def answer(
        self,
        request: TurnRequest,
        *,
        on_stage: Callable[[Any], None] | None = None,
    ) -> SpokenTurn:
        """Commit, then answer. Never the other way round.

        `pipeline.run` is the method `POST /v1/chat/turn` calls — not a variant
        and not a mode. §34.6's premise is that a typed message and a spoken one
        are one event, and the moment there are two orchestrations there are two
        sets of validators to keep in step.
        """
        message_id = await self.commit_utterance(
            conversation_id=request.conversation_id,
            text=request.text,
            locale=request.locale,
            now=request.now,
        )

        try:
            turn = await self._pipeline.run(
                # The pipeline must not write the user's turn again — it is
                # already on the record, one line above.
                dataclasses.replace(request, user_message_id=message_id),
                on_stage=on_stage,
            )
        except Exception:
            # §8: a provider outage is not a safety event and does not queue a
            # human. What it must not be is silent — the caller turns this into
            # §25.3's degrade ladder, and the words are already saved.
            logger.exception("call turn failed after the transcript was committed")
            return SpokenTurn(
                user_message_id=message_id,
                failure=("SYS_UNAVAILABLE", "errors.sys.unavailable"),
            )

        return SpokenTurn(user_message_id=message_id, turn=turn)

    # -- 3. her reply, from the VALIDATED text ------------------------------

    async def speak(self, turn: TurnResult, *, locale: str) -> AsyncIterator[bytes]:
        """Stream her reply as PCM.

        `turn.text` is what the presenter produced: in-locale, citation-free,
        and past grounding, language-quality and safety-post. There is no
        expression in this method that could hand the synthesiser anything else,
        which is the point — the parity test asserts it from outside, and the
        shape of the method is what makes the assertion hold.

        §3.4's respellings are applied HERE and nowhere else, on the way into
        the synthesiser, after the turn has been stored and after it has crossed
        the wire as the caption. A respelling that reached either would put
        "raahoo kaal" in the user's own transcript.
        """
        if self._tts is None:
            raise VoiceProviderUnavailable("no streaming TTS configured (§3.2)")
        spoken = pronunciation.apply(turn.text, locale, environment=self._environment)
        async for chunk in self._tts.stream(
            SynthesisRequest(text=spoken, locale=locale, voice_id=self._voice_id)
        ):
            yield chunk
