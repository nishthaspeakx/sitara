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
from sitara_api.voice import preview
from sitara_api.voice.audio import pcm_to_wav
from sitara_api.voice.expiry import delete_note
from sitara_api.voice.providers.base import VoiceProviderUnavailable
from sitara_api.voice.providers.registry import build_tts
from sitara_api.voice.storage import MongoVoiceAssetStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/voice", tags=["voice"])


class AudioRetentionPayload(BaseModel):
    """§33.1's global setting: "delete my audio after transcription"."""

    delete_after_transcription: bool


class NamePronunciationPayload(BaseModel):
    """§2.4-6's per-user name override, from S12's "that's not how it sounds".

    `override` is a RESPELLING, not a new name: §3.4 sends it to the
    synthesiser and nowhere else, and `display_name` — what the user is
    actually called, in their thread and their brief — is untouched by this
    endpoint. None clears it and returns Tara to saying the name as written.

    The field name matches `profiles.name_pronunciation.override`, which
    `db/seed.py` has declared since M4. See `voice/preview.py` for why a new
    name beside it would have been the wrong call.
    """

    override: str | None = None


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


@router.post("/preview")
async def get_voice_preview(request: Request, session: CurrentSession) -> Response:
    """S12: Tara says the user's name (§29.1, §0.11 item 11).

    **There is no request body carrying text, and there is no query parameter
    carrying text.** The sentence is a catalog key resolved server-side in the
    account's locale; the only thing that varies is the user's own name. See
    `voice/preview.py` — this is `speak_holding_phrase`'s rule on a second
    surface, and the signature is the guarantee rather than a convention.

    POST rather than GET because it costs a vendor call: a GET is what a
    prefetcher, a link scanner and a browser's back-forward cache will all
    issue on their own, and each one is money and a rate-limit slot spent on
    audio nobody asked to hear.
    """
    user_id, _session_id = session
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")

    oid = to_object_id(user_id, field_name="user_id")
    profile = await db.profiles.find_one({"user_id": oid})
    user = await db.users.find_one({"_id": oid}) or {}
    # §2.4: the ACCOUNT's locale, never a client-supplied one. A preview is the
    # first time the product speaks, and letting the caller pick the language
    # is how it speaks the wrong one.
    locale = user.get("locale") or (profile or {}).get("locale")
    if not locale:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.sys.validation")

    settings = request.app.state.voice_settings
    try:
        result = await preview.synthesise_preview(
            build_tts(settings),
            locale=locale,
            profile=profile,
            environment=getattr(request.app.state.settings, "environment", "dev"),
        )
    except VoiceProviderUnavailable as exc:
        # §30.1: her voice being unavailable is a designed state on this
        # screen, not an error page. S12 already renders it.
        logger.info("voice preview unavailable: %s", exc)
        # Retryability is a property of the CODE (`DEFAULT_RETRYABLE`), not of
        # the call site — so the envelope says retryable here without this
        # raise having an opinion about it.
        raise ApiError(ErrorCode.VOICE_PROVIDER_UNAVAILABLE) from exc

    return Response(
        content=pcm_to_wav(result.audio, result.sample_rate_hz),
        media_type="audio/wav",
        headers={
            # Her voice saying a specific person's name. §13's rule for the
            # user's own audio applies to this for the same reason.
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
        },
    )


@router.put("/settings/name-pronunciation", status_code=204)
async def set_name_pronunciation(
    payload: NamePronunciationPayload, request: Request, session: CurrentSession
) -> Response:
    """§2.4-6: "Tara asks once, in-locale, how to say it, and stores the
    phonetic override in the user's profile."

    Writes ONE field, beside the display name rather than over it. §3.4 keeps
    the two apart on purpose: a respelling that reached a transcript would put
    a stranger's spelling of someone's own name into their own thread.
    """
    user_id, _session_id = session
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")

    spoken = (payload.override or "").strip() or None
    await db.profiles.update_one(
        {"user_id": to_object_id(user_id, field_name="user_id")},
        {"$set": {"name_pronunciation.override": spoken}},
        upsert=False,
    )
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
