"""Family test harness — real compose mongo, for the §6.4 validator reasons
`tests/memory/conftest.py` gives."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from sitara_api.db import ensure_indexes
from sitara_api.family.store import FamilyStore

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local

NOW = dt.datetime(2026, 8, 15, 9, 30, tzinfo=dt.UTC)
OWNER_ID = ObjectId("6a70000000000000000000c1")
OTHER_OWNER_ID = ObjectId("6a70000000000000000000c2")


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
def store(db) -> FamilyStore:  # noqa: ANN001
    return FamilyStore(db)


__all__ = ["MONGO_URI", "NOW", "OTHER_OWNER_ID", "OWNER_ID"]
