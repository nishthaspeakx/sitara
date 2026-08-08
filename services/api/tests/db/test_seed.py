"""The seeder writes synthetic personas and refuses everything else (§22.12)."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from sitara_api.config import Settings
from sitara_api.db.seed import (
    EMAIL_DOMAIN,
    PERSONAS,
    PHONE_PREFIX,
    SEEDED_COLLECTIONS,
    SYNTHETIC_FLAG,
    UnsafeSeedError,
    assert_safe,
    seed,
    wipe,
)


class TestGuards:
    """§22.12 is enforced before a single document is written."""

    @pytest.mark.parametrize("environment", ["production", "staging", "prod"])
    def test_it_refuses_outside_dev(self, settings: Settings, environment: str) -> None:
        with pytest.raises(UnsafeSeedError, match="dev/test only"):
            assert_safe(settings.model_copy(update={"environment": environment}))

    def test_it_refuses_a_remote_host(self, settings: Settings) -> None:
        remote = settings.model_copy(
            update={"mongodb_uri": "mongodb://sitara-prod.abc.mongodb.net:27017/sitara"}
        )
        with pytest.raises(UnsafeSeedError, match="non-local"):
            assert_safe(remote)

    def test_it_allows_the_compose_stack(self, settings: Settings) -> None:
        assert_safe(settings)  # localhost:27018
        assert_safe(settings.model_copy(update={"mongodb_uri": "mongodb://mongo:27017/sitara"}))


class TestSyntheticOnly:
    pytestmark = pytest.mark.asyncio

    async def test_every_seeded_document_is_flagged(self, db) -> None:
        await seed(db)
        for collection in SEEDED_COLLECTIONS:
            total = await db[collection].count_documents({})
            flagged = await db[collection].count_documents({SYNTHETIC_FLAG: True})
            assert total == flagged, collection

    async def test_no_contact_value_could_ever_reach_a_real_person(self, db) -> None:
        """RFC 2606 reserves .invalid; +9199999 is India's test block. Neither
        can resolve, be dialled, or receive mail."""
        await seed(db)
        async for user in db.users.find({}):
            assert user["email"].endswith(f"@{EMAIL_DOMAIN}")
            assert user["phone"].startswith(PHONE_PREFIX)

    async def test_no_birth_record_carries_a_real_looking_identity(self, db) -> None:
        await seed(db)
        async for record in db.birth_details.find({}):
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["date"])
            assert record["place"]["label"] in {p.place_label for p in PERSONAS}

    async def test_firebase_uids_are_obviously_fake(self, db) -> None:
        await seed(db)
        async for identity in db.auth_identities.find({}):
            assert identity["provider_uid"].startswith("synthetic-")


class TestCoverage:
    """The personas exist to exercise real variation, not to be realistic."""

    def test_all_three_launch_locales_are_covered(self) -> None:
        assert {p.locale for p in PERSONAS} == {"en", "hi-Latn", "hi"}

    def test_both_corridors_are_covered(self) -> None:
        regions = {p.region for p in PERSONAS}
        assert "IN" in regions and len(regions) > 1

    def test_every_birth_time_accuracy_is_covered(self) -> None:
        """§10-6 drives the confidence system, so all four states need a fixture."""
        assert {p.time_accuracy for p in PERSONAS} == {
            "exact",
            "plus_minus_30",
            "day_part",
            "unknown",
        }

    def test_memory_consent_is_present_and_absent(self) -> None:
        assert {p.memory_consent for p in PERSONAS} == {True, False}

    def test_trial_and_paid_are_both_present(self) -> None:
        assert {"trialing", "active"} <= {p.subscription_status for p in PERSONAS}


class TestWrites:
    pytestmark = pytest.mark.asyncio

    async def test_seeding_passes_every_collection_validator(self, db) -> None:
        counts = await seed(db)
        assert counts["users"] == len(PERSONAS)
        assert counts["birth_details"] == len(PERSONAS)
        assert counts["family_members"] == sum(len(p.family) for p in PERSONAS)

    async def test_memory_consent_rows_match_the_personas(self, db) -> None:
        await seed(db)
        granted = await db.consents.count_documents({"type": "memory"})
        assert granted == sum(1 for p in PERSONAS if p.memory_consent)

    async def test_seeding_twice_does_not_duplicate_personas(self, db) -> None:
        await seed(db)
        await wipe(db)
        await seed(db)
        assert await db.users.count_documents({}) == len(PERSONAS)

    async def test_wipe_only_removes_synthetic_documents(self, db) -> None:
        await seed(db)
        await db.goals.insert_one(
            {
                "user_id": (await db.users.find_one({}))["_id"],
                "text": "hand-made fixture",
                "status": "open",
                "created_at": (await db.users.find_one({}))["created_at"],
                "updated_at": (await db.users.find_one({}))["updated_at"],
                "schema_v": 1,
            }
        )
        await wipe(db)
        remaining = await db.goals.find({}).to_list(length=10)
        assert [g["text"] for g in remaining] == ["hand-made fixture"]


class TestAgeTargetRedaction:
    """§13 / §37.2 — `age=` targets are rewritten, never deleted."""

    def test_an_age_target_becomes_its_outcome(self) -> None:
        from sitara_api.db.redact_age_targets import redacted_target

        assert redacted_target("age=17;min=18") == "outcome=refused;min=18"
        assert redacted_target("age=30;min=18") == "outcome=passed;min=18"

    def test_a_row_already_in_the_new_shape_is_left_alone(self) -> None:
        from sitara_api.db.redact_age_targets import redacted_target

        assert redacted_target("outcome=passed;min=18") is None
        assert redacted_target("") is None

    @pytest.mark.asyncio
    async def test_the_row_survives_redaction(self, db) -> None:  # noqa: ANN001
        """§6.4 marks audit_logs append-only. Destroying a record to fix its
        contents would be a worse violation than the one being fixed."""
        from sitara_api.db.documents import stamp
        from sitara_api.db.redact_age_targets import run

        await db.audit_logs.insert_one(
            stamp(
                {
                    "actor": "firebase:x",
                    "action": "auth.age_gate",
                    "target": "age=17;min=18",
                    "before_hash": None,
                    "after_hash": None,
                    "ip": None,
                    "ts": dt.datetime.now(dt.UTC),
                }
            )
        )

        scanned, redacted = await run(db)
        row = await db.audit_logs.find_one({"action": "auth.age_gate"})

        assert (scanned, redacted) == (1, 1)
        assert row is not None
        assert row["target"] == "outcome=refused;min=18"
        assert row["redacted_reason"] == "§13:age_derivative"
