"""CSFLE round-trips, and refuses to be misconfigured (§13, §22.12, §33.1)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import pytest_asyncio
from bson import Binary, ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from sitara_api.config import Settings
from sitara_api.db.csfle import (
    ENCRYPTED_SUBTYPE,
    CsfleConfigurationError,
    FieldCrypto,
    LocalKmsProvider,
    build_crypto,
    build_provider,
)
from sitara_api.db.documents import stamp
from sitara_api.db.registry import BY_NAME

NOW = dt.datetime(2026, 8, 8, 3, 30, tzinfo=dt.UTC)


@pytest.fixture()
def master_key(tmp_path: Path) -> Path:
    return tmp_path / "csfle-master.key"


@pytest.fixture()
def csfle_settings(settings: Settings, master_key: Path) -> Settings:
    return settings.model_copy(
        update={
            "csfle_enabled": True,
            "csfle_kms_provider": "local",
            "csfle_local_master_key_path": str(master_key),
        }
    )


@pytest_asyncio.fixture()
async def crypto(csfle_settings: Settings, db):  # noqa: ANN001
    client: AsyncIOMotorClient = AsyncIOMotorClient(csfle_settings.mongodb_uri)
    codec = await build_crypto(client, csfle_settings)
    assert codec is not None
    yield codec
    await codec.close()
    client.close()


class TestBirthDetailRoundTrip:
    """The playbook's M4 acceptance line: CSFLE round-trips a birth record."""

    pytestmark = pytest.mark.asyncio

    async def test_a_birth_record_survives_a_round_trip(self, db, crypto: FieldCrypto) -> None:
        spec = BY_NAME["birth_details"]
        plain = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "family_member_id": None,
            "date": "1988-03-14",
            "time": "04:55",
            "time_accuracy": "exact",
            "place": {"label": "Jaipur", "lat": 26.9124, "lon": 75.7873},
            "tz_snapshot": {"tz": "Asia/Kolkata"},
            "rectification_notes": None,
        }
        sealed = await crypto.encrypt_document(spec, stamp(dict(plain), now=NOW))
        await db.birth_details.insert_one(sealed)

        stored = await db.birth_details.find_one({"_id": plain["_id"]})
        assert stored is not None
        opened = await crypto.decrypt_document(spec, stored)
        for path in ("date", "time", "time_accuracy", "place", "tz_snapshot"):
            assert opened[path] == plain[path]

    async def test_ciphertext_is_what_actually_lands_on_disk(
        self, db, crypto: FieldCrypto
    ) -> None:
        """§13 calls birth details the crown jewels. A round-trip test alone
        would pass even if nothing were encrypted — so assert the stored form."""
        spec = BY_NAME["birth_details"]
        sealed = await crypto.encrypt_document(
            spec,
            stamp(
                {"_id": ObjectId(), "user_id": ObjectId(), "date": "1988-03-14",
                 "time_accuracy": "exact"},
                now=NOW,
            ),
        )
        await db.birth_details.insert_one(sealed)

        stored = await db.birth_details.find_one({})
        assert isinstance(stored["date"], Binary)
        assert stored["date"].subtype == ENCRYPTED_SUBTYPE
        assert b"1988-03-14" not in bytes(stored["date"])

    async def test_a_null_field_stays_null(self, db, crypto: FieldCrypto) -> None:
        """Encrypting a null would make "no note" indistinguishable from a note."""
        spec = BY_NAME["birth_details"]
        sealed = await crypto.encrypt_document(
            spec, {"date": "1990-01-01", "rectification_notes": None}
        )
        assert sealed["rectification_notes"] is None

    async def test_encrypting_twice_does_not_double_wrap(self, crypto: FieldCrypto) -> None:
        spec = BY_NAME["birth_details"]
        once = await crypto.encrypt_document(spec, {"date": "1990-01-01"})
        twice = await crypto.encrypt_document(spec, dict(once))
        assert twice["date"] == once["date"]


class TestAlgorithmChoice:
    pytestmark = pytest.mark.asyncio

    async def test_contact_replicas_stay_equality_queryable(
        self, db, crypto: FieldCrypto
    ) -> None:
        """§33.2's nightly reconciliation looks users up by contact value, so
        those two fields — and only those — are deterministic."""
        spec = BY_NAME["users"]
        sealed = await crypto.encrypt_document(
            spec,
            stamp(
                {
                    "_id": ObjectId(),
                    "firebase_uid": "u1",
                    "locale": "hi",
                    "status": "active",
                    "email": "asha@example.invalid",
                },
                now=NOW,
            ),
        )
        await db.users.insert_one(sealed)

        term = await crypto.encrypt_value("contact", "asha@example.invalid", deterministic=True)
        found = await db.users.find_one({"email": term})
        assert found is not None

    async def test_a_duplicate_email_is_actually_rejected(self, db, crypto: FieldCrypto) -> None:
        """§6.4's `uniq email` has to survive encryption. Deterministic
        ciphertext is what makes the unique index bite — under randomized
        encryption the same address would encrypt differently each time and the
        index would exist while enforcing nothing."""
        spec = BY_NAME["users"]

        def account(uid: str) -> dict:
            return stamp(
                {
                    "_id": ObjectId(),
                    "firebase_uid": uid,
                    "locale": "hi",
                    "status": "active",
                    "email": "asha@example.invalid",
                },
                now=NOW,
            )

        first = await crypto.encrypt_document(spec, account("u1"))
        second = await crypto.encrypt_document(spec, account("u2"))
        assert first["email"] == second["email"]  # deterministic, by design

        await db.users.insert_one(first)
        with pytest.raises(DuplicateKeyError):
            await db.users.insert_one(second)

    async def test_the_partial_filter_still_covers_encrypted_rows(
        self, db, crypto: FieldCrypto
    ) -> None:
        """M1's filter was `$type: "string"`, which matches no ciphertext at
        all — the index would have gone hollow the day CSFLE was switched on.
        `$exists` is what keeps it covering encrypted rows."""
        live = {doc["name"]: doc async for doc in db.users.list_indexes()}
        assert live["email_1"]["partialFilterExpression"] == {"email": {"$exists": True}}

        spec = BY_NAME["users"]
        sealed = await crypto.encrypt_document(
            spec,
            stamp(
                {
                    "_id": ObjectId(),
                    "firebase_uid": "u1",
                    "locale": "hi",
                    "status": "active",
                    "email": "meera@example.invalid",
                },
                now=NOW,
            ),
        )
        await db.users.insert_one(sealed)
        covered = await db.users.count_documents({"email": {"$exists": True}})
        assert covered == 1

    async def test_a_user_without_an_email_is_still_allowed(
        self, db, crypto: FieldCrypto
    ) -> None:
        """India's default signup is phone OTP (§10.4). Several users with no
        email must not collide on the unique index."""
        spec = BY_NAME["users"]
        for uid in ("p1", "p2", "p3"):
            await db.users.insert_one(
                await crypto.encrypt_document(
                    spec,
                    stamp(
                        {"_id": ObjectId(), "firebase_uid": uid, "locale": "hi",
                         "status": "active"},
                        now=NOW,
                    ),
                )
            )
        assert await db.users.count_documents({}) == 3

    async def test_randomized_fields_are_not_equality_queryable(
        self, db, crypto: FieldCrypto
    ) -> None:
        """Deterministic ciphertext leaks equality, so everything that does not
        need lookup is randomized — and encrypting the same value twice differs."""
        spec = BY_NAME["birth_details"]
        a = await crypto.encrypt_document(spec, {"date": "1988-03-14"})
        b = await crypto.encrypt_document(spec, {"date": "1988-03-14"})
        assert a["date"] != b["date"]


class TestKeyClasses:
    pytestmark = pytest.mark.asyncio

    async def test_each_class_gets_its_own_data_key(self, crypto: FieldCrypto) -> None:
        keys = await crypto.provision()
        assert len(set(keys.values())) == len(keys)

    async def test_voice_audio_has_a_key_of_its_own(self, crypto: FieldCrypto) -> None:
        """§33.1: voice-note audio is encrypted under a separate key class, so
        revoking it cannot silently revoke message content."""
        keys = await crypto.provision()
        assert "voice_audio" in keys
        assert keys["voice_audio"] != keys["message"]

    async def test_provisioning_twice_reuses_the_same_keys(self, crypto: FieldCrypto) -> None:
        """A redeploy that minted fresh keys would orphan every existing row."""
        first = await crypto.provision()
        second = await crypto.provision()
        assert first == second


class TestConfigurationGuards:
    def test_the_local_provider_refuses_outside_dev(self, master_key: Path) -> None:
        """§22.12: a dev master key on disk must never protect real data."""
        with pytest.raises(CsfleConfigurationError, match="dev-only"):
            LocalKmsProvider(master_key, environment="production")

    def test_a_short_master_key_is_rejected(self, master_key: Path) -> None:
        master_key.write_bytes(b"too short")
        with pytest.raises(CsfleConfigurationError, match="96"):
            LocalKmsProvider(master_key, environment="test")

    def test_the_aws_provider_needs_a_cmk(self, settings: Settings) -> None:
        broken = settings.model_copy(
            update={"csfle_kms_provider": "aws", "csfle_aws_kms_key_arn": None}
        )
        with pytest.raises(CsfleConfigurationError, match="CSFLE_AWS_KMS_KEY_ARN"):
            build_provider(broken)

    def test_the_aws_provider_names_its_key_without_holding_a_secret(
        self, settings: Settings
    ) -> None:
        provider = build_provider(
            settings.model_copy(
                update={
                    "csfle_kms_provider": "aws",
                    "csfle_aws_kms_key_arn": "arn:aws:kms:ap-south-1:1:key/abc",
                    "csfle_aws_region": "ap-south-1",
                }
            )
        )
        assert provider.credentials() == {"aws": {}}  # ambient credential chain
        assert provider.master_key() == {
            "provider": "aws",
            "region": "ap-south-1",
            "key": "arn:aws:kms:ap-south-1:1:key/abc",
        }

    @pytest.mark.asyncio
    async def test_disabling_csfle_outside_dev_is_an_error(self, settings: Settings) -> None:
        """§13 requires field-level encryption on the marked columns. Off is a
        dev convenience, never a production state."""
        prod = settings.model_copy(update={"csfle_enabled": False, "environment": "production"})
        with pytest.raises(CsfleConfigurationError, match="§13"):
            await build_crypto(None, prod)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_disabling_csfle_in_dev_returns_no_codec(self, settings: Settings) -> None:
        assert await build_crypto(None, settings) is None  # type: ignore[arg-type]
