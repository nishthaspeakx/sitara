"""§33.1's storage against the REAL validators, and the real expiry job.

The in-memory store in `conftest.py` shares `assert_storable` with the real one,
so the §25.4 guard is tested there. What it CANNOT test is the half that has
actually broken before: whether the collection accepts the document at all.
`tests/chat/test_store_mongo.py` exists because an in-memory fake took string
ids where §6.4 requires objectId, so every real write failed validation while
the whole suite stayed green. This is the same test for the same reason.

Mongo comes from the dev compose stack on 27018, same as tests/db.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from sitara_schemas import SOURCE_AUDIO_RETENTION_DAYS, PlaybackPolicy

from sitara_api.db import ensure_indexes
from sitara_api.voice.expiry import delete_note, run_expiry
from sitara_api.voice.storage import (
    COLLECTION,
    MongoVoiceAssetStore,
    VoiceAssetRejected,
    build_asset,
)
from tests.chat.conftest import CONVERSATION_ID, NOW, USER_ID

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local
PCM = b"\x00\x01" * 16_000


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()


def user_note(**overrides) -> dict:
    base = dict(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        message_id=None,
        role="user",
        audio=PCM,
        sample_rate_hz=16_000,
        duration_ms=1_000,
        playback_policy=PlaybackPolicy.ORIGINAL_AUDIO,
        now=NOW,
    )
    return build_asset(**{**base, **overrides})


@pytest.mark.asyncio
async def test_a_voice_asset_passes_the_collection_validator(db) -> None:  # noqa: ANN001
    store = MongoVoiceAssetStore(db)

    asset_id = await store.put(user_note())

    saved = await db[COLLECTION].find_one({"_id": ObjectId(asset_id)})
    assert saved is not None
    assert isinstance(saved["user_id"], ObjectId)
    assert isinstance(saved["conversation_id"], ObjectId)
    # Written as `Binary`, read back as plain `bytes`: subtype 0 round-trips to
    # Python's own type. Worth pinning, because the pair of traps points both
    # ways — `Binary(x) == x` is False (it compares subtype, and only against
    # another Binary), while what comes OUT of Mongo compares fine. A test that
    # asserted `isinstance(..., Binary)` here would fail on correct code.
    assert isinstance(saved["audio"], bytes)
    assert saved["audio"] == PCM
    assert saved["codec"] == "pcm_s16le"
    assert saved["playback_policy"] == PlaybackPolicy.ORIGINAL_AUDIO.value
    # §33.1: excluded from all training and cloning, stamped on the row.
    assert saved["training_excluded"] is True
    assert saved["deleted_at"] is None


@pytest.mark.asyncio
async def test_the_thirty_day_clock_is_stamped_per_note(db) -> None:  # noqa: ANN001
    """§33.1's "30 days by DEFAULT" — a per-row stamp, so a user who shortens
    their retention changes their own future notes with no migration."""
    store = MongoVoiceAssetStore(db)
    await store.put(user_note())
    saved = await db[COLLECTION].find_one({})

    expected = NOW + dt.timedelta(days=SOURCE_AUDIO_RETENTION_DAYS)
    assert saved["expires_at"].replace(tzinfo=dt.UTC) == expected

    short = user_note(retention_days=7)
    assert short["expires_at"] == NOW + dt.timedelta(days=7)


@pytest.mark.asyncio
async def test_the_collection_carries_no_ttl_index(db) -> None:  # noqa: ANN001
    """§36.2 and §33.1 agree, for different reasons that reach one answer.

    A TTL reaper deletes the DOCUMENT, so it can hard-delete the audio but
    destroys the tombstone §33.1 asks for in the same sentence — and a bubble
    cannot say "this recording has expired" if the row is gone, because a
    missing row and a never-existed row are the same absence.
    """
    indexes = await db[COLLECTION].index_information()
    assert not [name for name, spec in indexes.items() if "expireAfterSeconds" in spec]
    # But the scan index IS there — without it the nightly job reads every note
    # ever recorded.
    assert any("expires_at" in str(spec.get("key", "")) for spec in indexes.values())


@pytest.mark.asyncio
async def test_expiry_hard_deletes_the_audio_and_leaves_the_row(db) -> None:  # noqa: ANN001
    """The §33.1 sentence, both halves, against the real collection."""
    store = MongoVoiceAssetStore(db)
    stale = user_note(now=NOW - dt.timedelta(days=SOURCE_AUDIO_RETENTION_DAYS + 1))
    asset_id = await store.put(stale)
    fresh_id = await store.put(user_note())

    report = await run_expiry(db, now=NOW)

    assert report.deleted == 1
    tombstone = await db[COLLECTION].find_one({"_id": ObjectId(asset_id)})
    assert tombstone is not None, "the row must outlive the audio — that IS the tombstone"
    assert "audio" not in tombstone, "the bytes must be gone, not flagged"
    assert tombstone["deleted_at"] is not None
    # A tombstoned asset is no longer readable, and `get` says so by absence
    # rather than by returning a row with no audio in it.
    assert await store.get(asset_id) is None
    # The note still inside its thirty days is untouched.
    assert await store.get(fresh_id) is not None


@pytest.mark.asyncio
async def test_expiry_is_safe_to_run_twice(db) -> None:  # noqa: ANN001
    """§6.1: "every task must be safe to run twice" — `task_acks_late` hands a
    dead worker's message back. The second sweep must find nothing, not
    re-tombstone a row and move its deleted_at forward."""
    store = MongoVoiceAssetStore(db)
    await store.put(user_note(now=NOW - dt.timedelta(days=40)))

    first = await run_expiry(db, now=NOW)
    stamped = (await db[COLLECTION].find_one({}))["deleted_at"]
    second = await run_expiry(db, now=NOW + dt.timedelta(hours=1))

    assert first.deleted == 1
    assert second.deleted == 0
    assert (await db[COLLECTION].find_one({}))["deleted_at"] == stamped


@pytest.mark.asyncio
async def test_a_dry_run_changes_nothing(db) -> None:  # noqa: ANN001
    store = MongoVoiceAssetStore(db)
    await store.put(user_note(now=NOW - dt.timedelta(days=40)))

    report = await run_expiry(db, now=NOW, dry_run=True)

    assert report.scanned == 1
    assert (await db[COLLECTION].find_one({}))["deleted_at"] is None


@pytest.mark.asyncio
async def test_per_note_delete_is_the_same_operation_as_expiry(db) -> None:  # noqa: ANN001
    """§33.1 gives the user a per-note delete. It is deliberately the same code
    path: a per-note delete that left the bytes behind while the job removed
    them would be two different promises wearing one word."""
    store = MongoVoiceAssetStore(db)
    asset_id = await store.put(user_note())

    assert await delete_note(db, asset_id, now=NOW) is True

    row = await db[COLLECTION].find_one({"_id": ObjectId(asset_id)})
    assert "audio" not in row and row["deleted_at"] is not None
    # Deleting twice is not an error and not a second delete.
    assert await delete_note(db, asset_id, now=NOW) is False


@pytest.mark.asyncio
async def test_the_collection_refuses_a_call_session_reference(db) -> None:  # noqa: ANN001
    """§33.1/§13: live-call audio is NEVER stored. `voice_sessions` and
    `call_sessions` reject audio fields; this is the same rule pointed the
    other way, so a call cannot reach the one collection that DOES hold audio
    by carrying its id in. The VALIDATOR does it, not a convention."""
    from pymongo.errors import WriteError

    document = dict(user_note(), call_session_id=ObjectId())
    with pytest.raises(WriteError):
        await db[COLLECTION].insert_one(document)


@pytest.mark.asyncio
async def test_taras_reply_and_the_users_note_are_different_kinds_of_asset(db) -> None:  # noqa: ANN001
    """§25.4's promise, at the storage boundary.

    The guard lives in `assert_storable`, which the real store and the
    in-memory fake both call — so the fake cannot accept what the collection
    rejects, which is the root CLAUDE.md rule and the one M5 broke.
    """
    store = MongoVoiceAssetStore(db)
    await store.put(user_note(role="tara", playback_policy=PlaybackPolicy.SYNTHESISED))

    with pytest.raises(VoiceAssetRejected, match="ORIGINAL"):
        await store.put(user_note(role="user", playback_policy=PlaybackPolicy.SYNTHESISED))
    with pytest.raises(VoiceAssetRejected, match="no original recording"):
        await store.put(user_note(role="tara", playback_policy=PlaybackPolicy.ORIGINAL_AUDIO))


@pytest.mark.asyncio
async def test_one_message_cannot_hold_two_originals(db) -> None:  # noqa: ANN001
    """Two assets for one message would make "the original" ambiguous, which is
    the one thing §25.4 cannot be. The partial filter keeps the uniqueness off
    the message-less rows the service writes before the message row exists."""
    from pymongo.errors import DuplicateKeyError

    store = MongoVoiceAssetStore(db)
    message_id = ObjectId()
    await store.put(user_note(message_id=message_id))

    with pytest.raises(DuplicateKeyError):
        await store.put(user_note(message_id=message_id))

    # ...but many rows may sit unattached, which is the normal case in flight.
    await store.put(user_note())
    await store.put(user_note())
