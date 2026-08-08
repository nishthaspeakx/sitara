"""The store against the REAL §6.4 validators.

Every other chat test uses `InMemoryMessageStore`, which accepts anything. That
convenience hid a live defect: `messages.conversation_id`, `guidance_logs.user_id`
and `guidance_logs.message_id` are typed `objectId` in §6.4 and the pipeline
carries §33.2's product identity as a string, so every real write failed
validation while the suite stayed green.

These tests exist so that cannot happen twice. Mongo comes from the dev compose
stack on 27018, same as tests/db and tests/panchang.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from sitara_schemas.facts import ConfidenceState, Graha

from sitara_api.chat_orchestration.store import (
    MalformedIdentifier,
    MongoMessageStore,
    MongoReviewQueue,
    ReviewEntry,
    build_guidance_log,
    build_message,
    build_safety_event,
    pseudonymise,
    to_object_id,
)
from sitara_api.chat_orchestration.types import (
    RiskClass,
    SafetyAssessment,
    SafetyLabel,
    SafetyLevel,
    Stage,
)
from sitara_api.db import ensure_indexes
from tests.chat.conftest import CONVERSATION_ID, NOW, SATURN_FACT_ID, USER_ID, transit_house_fact

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()


ASSESSMENT = SafetyAssessment(
    level=SafetyLevel.L4_CRISIS,
    risk_class=RiskClass.ACUTE_CRISIS,
    labels=(SafetyLabel(risk_class=RiskClass.ACUTE_CRISIS, score=0.95, source="rules"),),
)


@pytest.mark.asyncio
async def test_a_message_passes_the_64_validator(db) -> None:  # noqa: ANN001
    store = MongoMessageStore(db)

    message_id = await store.save_message(
        build_message(
            conversation_id=CONVERSATION_ID,
            role="assistant",
            content="Saturn is moving through your 10th house today.",
            locale="en",
            fact_snapshots=[transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID)],
            now=NOW,
        )
    )

    saved = await db.messages.find_one({"_id": ObjectId(message_id)})
    assert saved is not None
    # §6.4 types the reference; a string here is what the validator rejected.
    assert isinstance(saved["conversation_id"], ObjectId)
    # §34.2: the snapshot travels with the artefact, not a reference to it.
    assert saved["fact_snapshots"][0]["fact_id"] == SATURN_FACT_ID
    assert saved["playback_policy"] == "text_only"


@pytest.mark.asyncio
async def test_a_guidance_log_passes_the_64_validator(db) -> None:  # noqa: ANN001
    store = MongoMessageStore(db)
    message_id = await store.save_message(
        build_message(
            conversation_id=CONVERSATION_ID, role="assistant", content="x", locale="en", now=NOW
        )
    )

    await store.save_guidance_log(
        build_guidance_log(
            user_id=USER_ID,
            local_date="2026-08-08",
            message_id=message_id,
            fact_snapshots=[transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID)],
            confidence=ConfidenceState.VERIFIED,
            why={"intent": "daily_guidance"},
            now=NOW,
        )
    )

    saved = await db.guidance_logs.find_one({"date": "2026-08-08"})
    assert saved is not None
    assert isinstance(saved["user_id"], ObjectId)
    assert isinstance(saved["message_id"], ObjectId)
    assert saved["confidence"] == "verified"


@pytest.mark.asyncio
async def test_a_safety_event_passes_the_64_validator(db) -> None:  # noqa: ANN001
    await MongoReviewQueue(db).enqueue(
        ReviewEntry(
            stage=Stage.SAFETY_PRE,
            reason="L4:acute_crisis",
            trace_id="trace-1",
            user_ref=pseudonymise(USER_ID),
            conversation_id=CONVERSATION_ID,
            locale="en",
            level=SafetyLevel.L4_CRISIS,
            created_at=NOW,
            assessment=ASSESSMENT,
        )
    )

    saved = await db.safety_events.find_one({"review_status": "pending"})
    assert saved is not None
    # §6.4's user_ref is pseudonymised, never the product identity.
    assert saved["user_ref"] != USER_ID
    # §12 pattern analytics reads the scores; the field must hold scores.
    assert saved["classifier_scores"]["labels"][0]["risk_class"] == "acute_crisis"
    assert saved["classifier_scores"]["trigger"]["stage"] == "safety_pre"


@pytest.mark.asyncio
async def test_a_guidance_log_without_a_message_is_allowed(db) -> None:  # noqa: ANN001
    """§6.4 types message_id as objectId OR null — a brief-sourced row has none."""
    await MongoMessageStore(db).save_guidance_log(
        build_guidance_log(
            user_id=USER_ID,
            local_date="2026-08-09",
            message_id=None,
            fact_snapshots=[],
            confidence=ConfidenceState.TRADITION_BASED_GENERAL,
            why={},
            now=NOW,
        )
    )

    saved = await db.guidance_logs.find_one({"date": "2026-08-09"})
    assert saved is not None and saved["message_id"] is None


def test_a_non_mongo_identifier_is_refused_loudly() -> None:
    """Better a loud failure than a turn written under an invented id — that
    message would be an orphan in the transcript."""
    with pytest.raises(MalformedIdentifier, match="conversation_id"):
        build_message(conversation_id="conv-1", role="user", content="hi", locale="en")

    with pytest.raises(MalformedIdentifier):
        to_object_id("not-an-id", field_name="user_id")


def test_object_ids_pass_through_unchanged() -> None:
    oid = ObjectId()
    assert to_object_id(oid, field_name="user_id") is oid


def test_a_safety_event_records_a_degraded_classifier() -> None:
    """§9: rules-only is a fail-safe rung, and a reviewer must be able to see
    that the classifier was not consulted."""
    entry = ReviewEntry(
        stage=Stage.SAFETY_PRE,
        reason="L4",
        trace_id="t",
        user_ref="ref",
        conversation_id=CONVERSATION_ID,
        locale="en",
        level=SafetyLevel.L4_CRISIS,
        created_at=dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
        assessment=SafetyAssessment(
            level=SafetyLevel.L4_CRISIS, risk_class=RiskClass.ACUTE_CRISIS, degraded=True
        ),
    )

    assert build_safety_event(entry)["classifier_scores"]["classifier_degraded"] is True
