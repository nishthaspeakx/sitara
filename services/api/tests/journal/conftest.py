"""Journal test harness.

Mongo comes from the dev compose stack on 27018, for the reason
`tests/memory/conftest.py` gives: the §6.4 validators are part of what is under
test, and `journal_saves` arrived with CC-011's validator on day one. A fake
that accepted a save the real collection rejects would be a defect in the fake.
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
from sitara_api.journal.store import JournalStore

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local

NOW = dt.datetime(2026, 8, 15, 9, 30, tzinfo=dt.UTC)
USER_ID = ObjectId("6a70000000000000000000b1")
OTHER_USER_ID = ObjectId("6a70000000000000000000b2")


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()


@pytest.fixture()
def store(db) -> JournalStore:  # noqa: ANN001
    return JournalStore(db)


__all__ = ["MONGO_URI", "NOW", "OTHER_USER_ID", "USER_ID"]
