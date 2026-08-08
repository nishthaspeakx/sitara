"""Collection validators enforce the §6.4 preamble and the §13/§33.1 audio rule."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from bson import ObjectId
from pymongo.errors import WriteError

from sitara_api.db.documents import stamp
from sitara_api.db.registry import BY_NAME
from sitara_api.db.validators import build_validator

NOW = dt.datetime(2026, 8, 8, 3, 30, tzinfo=dt.UTC)


def _user(**overrides: object) -> dict[str, Any]:
    doc: dict[str, Any] = {"firebase_uid": "u1", "locale": "hi", "status": "active"}
    doc.update(overrides)
    return stamp(doc, now=NOW)


class TestBaseFields:
    """§6.4: "every doc carries _id, created_at, updated_at, schema_v"."""

    pytestmark = pytest.mark.asyncio

    async def test_a_stamped_document_is_accepted(self, db) -> None:
        await db.users.insert_one(_user())
        assert await db.users.count_documents({}) == 1

    @pytest.mark.parametrize("missing", ["created_at", "updated_at", "schema_v"])
    async def test_a_document_missing_a_base_field_is_rejected(self, db, missing: str) -> None:
        doc = _user()
        del doc[missing]
        with pytest.raises(WriteError):
            await db.users.insert_one(doc)

    async def test_a_document_missing_a_required_field_is_rejected(self, db) -> None:
        doc = _user()
        del doc["locale"]  # §2.4 — a user without a locale has no language to be served in
        with pytest.raises(WriteError):
            await db.users.insert_one(doc)

    async def test_wrong_bson_type_is_rejected(self, db) -> None:
        with pytest.raises(WriteError):
            await db.users.insert_one(_user(locale=7))


class TestAudioFields:
    """§33.1's explicit field model, and §13's rule about what may not exist."""

    pytestmark = pytest.mark.asyncio

    async def test_messages_accepts_all_six_audio_fields(self, db) -> None:
        await db.messages.insert_one(
            stamp(
                {
                    "conversation_id": ObjectId(),
                    "role": "user",
                    "type": "voice_note",
                    "content": "namaste",
                    "locale": "hi",
                    "fact_ids": [],
                    "safety_labels": [],
                    "source_audio_asset_id": "asset-1",
                    "tts_audio_asset_id": None,
                    "transcript_status": "final",
                    "source_audio_expires_at": NOW + dt.timedelta(days=30),
                    "source_audio_deleted_at": None,
                    "playback_policy": "original",
                },
                now=NOW,
            )
        )
        assert await db.messages.count_documents({}) == 1

    async def test_messages_without_a_playback_policy_is_rejected(self, db) -> None:
        """The policy field is what makes the bubble honest about what it can
        replay — a message without one cannot be rendered truthfully."""
        with pytest.raises(WriteError):
            await db.messages.insert_one(
                stamp(
                    {
                        "conversation_id": ObjectId(),
                        "role": "user",
                        "type": "text",
                        "locale": "hi",
                        "transcript_status": "none",
                    },
                    now=NOW,
                )
            )

    @pytest.mark.parametrize("collection", ["voice_sessions", "call_sessions"])
    @pytest.mark.parametrize(
        "audio_field", ["audio_asset_id", "audio_ref", "audio_url", "recording_ref"]
    )
    async def test_call_audio_cannot_be_stored(self, db, collection: str, audio_field: str) -> None:
        """§13/§33.1: live-call audio is never stored. Not a convention — the
        collection physically rejects the write."""
        base = {
            "user_id": ObjectId(),
            "minutes": 3.5,
            "state": "ended",
            "started_at": NOW,
            audio_field: "s3://bucket/leak.wav",
        }
        with pytest.raises(WriteError):
            await db[collection].insert_one(stamp(base, now=NOW))

    @pytest.mark.parametrize("collection", ["voice_sessions", "call_sessions"])
    async def test_the_same_document_without_audio_is_fine(self, db, collection: str) -> None:
        await db[collection].insert_one(
            stamp(
                {"user_id": ObjectId(), "minutes": 3.5, "state": "ended", "started_at": NOW},
                now=NOW,
            )
        )
        assert await db[collection].count_documents({}) == 1


class TestEncryptedFieldTypes:
    """One validator has to hold whether CSFLE is on or off, or dev-without-a-key
    would reject its own writes."""

    def test_encrypted_fields_accept_bindata_as_well_as_plaintext(self) -> None:
        schema = build_validator(BY_NAME["birth_details"])["$jsonSchema"]
        for path in BY_NAME["birth_details"].encrypted_paths:
            assert "binData" in schema["properties"][path]["bsonType"], path

    def test_unencrypted_fields_do_not_accept_bindata(self) -> None:
        schema = build_validator(BY_NAME["users"])["$jsonSchema"]
        assert "binData" not in schema["properties"]["locale"]["bsonType"]
