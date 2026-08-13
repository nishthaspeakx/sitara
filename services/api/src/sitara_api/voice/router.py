"""Voice-note audio and §33.1's user controls.

Three endpoints, and each is one sentence of §33.1 made operable: play back the
original, delete a single note, and switch the account to ephemeral voice input.

**Cookie-authenticated, not service-keyed.** The `/v1/chat/ws/*` pair exists so
`sitara-realtime` can act on a user's behalf; these are the browser talking
about its own audio, so §34.5's httpOnly session cookie is the door.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sitara_schemas import ErrorCode

from sitara_api.auth.router import CurrentSession
from sitara_api.chat_orchestration.store import to_object_id
from sitara_api.errors import ApiError
from sitara_api.voice.audio import pcm_to_wav
from sitara_api.voice.expiry import delete_note
from sitara_api.voice.storage import MongoVoiceAssetStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/voice", tags=["voice"])


class AudioRetentionPayload(BaseModel):
    """§33.1's global setting: "delete my audio after transcription"."""

    delete_after_transcription: bool


def _store(request: Request) -> MongoVoiceAssetStore:
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return MongoVoiceAssetStore(db, getattr(request.app.state, "field_crypto", None))


@router.get("/notes/{asset_id}/audio")
async def get_note_audio(
    asset_id: str, request: Request, session: CurrentSession
) -> Response:
    """The ORIGINAL recording (§25.4), for its owner only.

    Served as WAV: the stored bytes are §34.6's raw PCM, and a browser needs a
    container to play them. `pcm_to_wav` adds a 44-byte header and touches no
    sample, so this is the recording, not a rendering of it.

    A tombstoned or expired note is **410 Gone**, not 404. The distinction is
    §33.1's: the note existed, the user was told it would be kept thirty days,
    and it has been deleted exactly as promised. 404 would say it never was.
    """
    user_id, _session_id = session
    asset = await _store(request).get(asset_id)
    if asset is None:
        raise ApiError(ErrorCode.VOICE_NOTE_EXPIRED, "errors.voice.note_expired")

    # §13: the owner, and nobody else. Checked against the session rather than
    # trusting an unguessable id — an id is not an authorisation.
    if asset["user_id"] != to_object_id(user_id, field_name="user_id"):
        raise ApiError(ErrorCode.AUTH_FORBIDDEN, "errors.auth.forbidden")

    audio = asset.get("audio")
    if not audio:
        raise ApiError(ErrorCode.VOICE_NOTE_EXPIRED, "errors.voice.note_expired")

    return Response(
        content=pcm_to_wav(bytes(audio), int(asset["sample_rate_hz"])),
        media_type="audio/wav",
        headers={
            # §13: a user's voice is never cached by a shared proxy, and never
            # written to disk by the browser beyond the session.
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
        },
    )


@router.delete("/notes/{asset_id}", status_code=204)
async def delete_note_audio(
    asset_id: str, request: Request, session: CurrentSession
) -> Response:
    """§33.1's per-note delete — the same hard-delete-and-tombstone the expiry
    job performs, because two different promises wearing one word is worse than
    either."""
    user_id, _session_id = session
    store = _store(request)
    asset = await store.get(asset_id)
    if asset is None:
        # Already gone. Idempotent rather than an error: a user tapping delete
        # twice has got what they asked for both times.
        return Response(status_code=204)
    if asset["user_id"] != to_object_id(user_id, field_name="user_id"):
        raise ApiError(ErrorCode.AUTH_FORBIDDEN, "errors.auth.forbidden")

    await delete_note(request.app.state.db, asset_id)
    return Response(status_code=204)


@router.put("/settings/audio-retention", status_code=204)
async def set_audio_retention(
    payload: AudioRetentionPayload, request: Request, session: CurrentSession
) -> Response:
    """§33.1's ephemeral voice-input mode.

    Forward-looking only: turning it ON does not delete existing recordings,
    and saying so is the §29.2 honesty rule. The user's existing notes keep
    their own thirty-day clocks and their own per-note delete; this changes
    what happens to the NEXT one, which is what "after transcription" means.
    """
    user_id, _session_id = session
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")

    field = "onboarding.delete_audio_after_transcription"
    await db.profiles.update_one(
        {"user_id": to_object_id(user_id, field_name="user_id")},
        {"$set": {field: payload.delete_after_transcription}},
        upsert=False,
    )
    return Response(status_code=204)
