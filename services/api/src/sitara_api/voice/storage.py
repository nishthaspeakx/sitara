"""§33.1's encrypted original — storage, and the rule that makes replay honest.

§33.1: "the original recording is stored encrypted (separate CSFLE key class)
for 30 days by default". Two words in that sentence decide this file.

**"CSFLE key class"** puts the bytes in MongoDB, not S3. §36.3 already
provisioned a `voice_audio` data key for exactly this and nothing has used it
since M4; §6.4's `source_audio_asset_id` is the id of a row here. S3 would mean
SSE-KMS, which is a different mechanism than the one §33.1 names, and it would
put a user's voice outside the key class whose whole purpose is that revoking
it cannot silently revoke message content — and vice versa.

**"30 days by default"** makes expiry a per-note stamp, not a collection-wide
TTL. §36.2 fixed the rule that a TTL index exists only where §6.4's table
writes "TTL", and this collection is not in that table at all; more decisively,
§33.1 asks the expiry job to "hard-delete assets + write deleted_at
tombstones", and MongoDB's reaper cannot write a tombstone. See `expiry.py`.

The §25.4 guard
---------------

"Replay plays the user's ORIGINAL recording, never a TTS reconstruction." One
message row carries both `source_audio_asset_id` and `tts_audio_asset_id`, so
the way that promise breaks is a user bubble whose source-audio id points at a
synthesised asset — a wiring mistake, not a decision anyone would make. It
would look right in every test that checks "audio plays". `assert_storable`
refuses it at the boundary, so the mistake raises instead of shipping.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from bson import Binary, ObjectId
from sitara_schemas import SOURCE_AUDIO_RETENTION_DAYS, PlaybackPolicy

from sitara_api.db.documents import stamp

logger = logging.getLogger(__name__)

COLLECTION = "voice_assets"

#: §33.1: "audio is excluded from all model training and cloning". Stamped on
#: every row rather than assumed, so an export, a backup restore or a future
#: training-data selector reads the exclusion off the document instead of
#: relying on whoever writes that query remembering §33.1.
TRAINING_EXCLUDED = True


class VoiceAssetRejected(ValueError):
    """A write that would break §33.1 or §25.4. Never caught to continue."""


def assert_storable(asset: dict[str, Any]) -> None:
    """The invariants a voice asset must satisfy, checked at every door.

    Shared by the real store and the in-memory fake, because a fake that
    accepts what the real system rejects is a defect in the fake — the root
    CLAUDE.md rule, and the one M5 broke.
    """
    role = asset.get("role")
    policy = asset.get("playback_policy")

    if role == "user" and policy == PlaybackPolicy.SYNTHESISED.value:
        raise VoiceAssetRejected(
            "§25.4: a user's voice note replays their ORIGINAL recording and never "
            "a TTS reconstruction — refusing to store a `synthesised` asset against "
            "a user message"
        )
    if role == "tara" and policy == PlaybackPolicy.ORIGINAL_AUDIO.value:
        raise VoiceAssetRejected(
            "Tara has no original recording — her bubble is `synthesised` (§25.4)"
        )
    if not asset.get("audio"):
        raise VoiceAssetRejected("a voice asset with no audio is a row with no purpose")
    if asset.get("call_session_id") is not None:
        # §33.1/§13: call audio is NEVER stored. `voice_sessions` and
        # `call_sessions` already reject audio fields structurally; this is the
        # same rule pointed the other way, so a call cannot reach the store
        # that DOES hold audio by carrying its id into a note.
        raise VoiceAssetRejected(
            "§33.1: live-call audio is never stored — a voice asset cannot belong "
            "to a call session"
        )


def build_asset(
    *,
    user_id: str | ObjectId,
    conversation_id: str | ObjectId,
    message_id: str | ObjectId | None,
    role: str,
    audio: bytes,
    sample_rate_hz: int,
    duration_ms: int,
    playback_policy: PlaybackPolicy,
    retention_days: int = SOURCE_AUDIO_RETENTION_DAYS,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """One `voice_assets` document, §33.1-shaped.

    `expires_at` is stamped per row from the retention DEFAULT, so a user who
    shortens their retention changes their own future notes without a migration
    and without the expiry job needing to know why.
    """
    from sitara_api.chat_orchestration.store import to_object_id

    created = now or dt.datetime.now(dt.UTC)
    document: dict[str, Any] = {
        "user_id": to_object_id(user_id, field_name="user_id"),
        "conversation_id": to_object_id(conversation_id, field_name="conversation_id"),
        "message_id": to_object_id(message_id, field_name="message_id") if message_id else None,
        "role": role,
        # Binary, not str: this is bytes, and CSFLE encrypts the BSON value.
        "audio": Binary(audio),
        "codec": "pcm_s16le",
        "sample_rate_hz": sample_rate_hz,
        "duration_ms": duration_ms,
        "byte_length": len(audio),
        "playback_policy": playback_policy.value,
        "expires_at": created + dt.timedelta(days=retention_days),
        "deleted_at": None,
        "training_excluded": TRAINING_EXCLUDED,
    }
    assert_storable(document)
    return stamp(document, now=created)


class MongoVoiceAssetStore:
    """The real store. `audio` is CSFLE-encrypted under `voice_audio` (§36.3).

    Encryption is explicit here for the same reason it is explicit everywhere
    else in this codebase: automatic CSFLE is Atlas/Enterprise-only and the dev
    stack is Community, so an automatic path would be one production runs and
    nobody exercises locally.
    """

    def __init__(self, db: Any, crypto: Any = None) -> None:
        self._db = db
        self._crypto = crypto

    async def put(self, asset: dict[str, Any]) -> str:
        assert_storable(asset)
        document = await self._encrypt(asset)
        result = await self._db[COLLECTION].insert_one(document)
        return str(result.inserted_id)

    async def get(self, asset_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(asset_id)
        except Exception:
            return None
        document = await self._db[COLLECTION].find_one({"_id": oid, "deleted_at": None})
        if document is None:
            return None
        return await self._decrypt(document)

    async def hard_delete(self, asset_id: str, *, now: dt.datetime | None = None) -> bool:
        """§33.1: hard-delete the asset, leave a tombstone.

        The bytes go; the row stays with `deleted_at` set. That is what lets a
        bubble say "this recording has expired" rather than rendering a play
        control over nothing, and what lets §12 answer "was this deleted or did
        it never exist" without keeping the audio to prove it.
        """
        try:
            oid = ObjectId(asset_id)
        except Exception:
            return False
        result = await self._db[COLLECTION].update_one(
            {"_id": oid, "deleted_at": None},
            {
                "$set": {
                    "deleted_at": now or dt.datetime.now(dt.UTC),
                    "updated_at": now or dt.datetime.now(dt.UTC),
                },
                "$unset": {"audio": ""},
            },
        )
        return result.modified_count == 1

    async def _encrypt(self, asset: dict[str, Any]) -> dict[str, Any]:
        if self._crypto is None:
            return asset
        from sitara_api.db.registry import spec_for

        return await self._crypto.encrypt_document(spec_for(COLLECTION), asset)

    async def _decrypt(self, document: dict[str, Any]) -> dict[str, Any]:
        if self._crypto is None:
            return document
        from sitara_api.db.registry import spec_for

        return await self._crypto.decrypt_document(spec_for(COLLECTION), document)
