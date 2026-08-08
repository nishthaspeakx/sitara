"""Memory test harness.

Mongo comes from the dev compose stack on 27018 — the same pattern as tests/db
and tests/panchang, and for the same reason: the §6.4 validators are part of
what is under test. The M5 review's lesson stands (root CLAUDE.md): a fake that
accepts what the real collection rejects is a defect in the fake, so the
memory store is exercised against the real thing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from sitara_api.db import ensure_indexes
from sitara_api.memory.embeddings import DeterministicEmbedder
from sitara_api.memory.models import ConsentAction, ConsentEvent, ConsentRecord
from sitara_api.memory.retrieval import ExactVectorSearch
from sitara_api.memory.service import MemoryService
from sitara_api.memory.store import MemoryStore
from sitara_api.memory.taxonomy import RECONFIRM_WORDING, MemoryType

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local

NOW = dt.datetime(2026, 8, 8, 9, 30, tzinfo=dt.UTC)
USER_ID = ObjectId("6a70000000000000000000a1")
OTHER_USER_ID = ObjectId("6a70000000000000000000a2")


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()


@pytest.fixture()
def store(db) -> MemoryStore:  # noqa: ANN001
    return MemoryStore(db)


@pytest.fixture()
def embedder() -> DeterministicEmbedder:
    """Token-hashing, not cross-lingual, and honest about it (§32.5).

    Every test here is about plumbing — storage, gates, decay, CRUD, ranking
    arithmetic — none of which depends on semantics. The one thing that does
    is the recall gate, which refuses to run on this.
    """
    return DeterministicEmbedder()


@pytest.fixture()
def service(store: MemoryStore, embedder: DeterministicEmbedder) -> MemoryService:
    return MemoryService(store=store, search=ExactVectorSearch(store), embedder=embedder)


def consent_for(memory_type: MemoryType, *, now: dt.datetime = NOW, wording: str = ""):  # noqa: ANN201
    """A consent record that satisfies §32.4 for this type."""
    return ConsentRecord(
        granted=True,
        granted_at=now,
        wording_reconfirmed=memory_type in RECONFIRM_WORDING,
        history=(ConsentEvent(action=ConsentAction.GRANTED, at=now, wording=wording),),
    )


__all__ = [
    "MONGO_URI",
    "NOW",
    "OTHER_USER_ID",
    "USER_ID",
    "consent_for",
]
