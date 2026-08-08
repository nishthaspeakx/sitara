"""Panchang test harness.

Mongo comes from the dev compose stack on 27018 (never a machine-local mongod);
every provider HTTP call is replayed from a recorded fixture — see
tests/panchang/fixtures/README.md. CI never reaches a live vendor.
"""

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

from sitara_api.config import Settings
from sitara_api.db import ensure_indexes
from sitara_api.panchang.cache import PanchangCache, TransitCache
from sitara_api.panchang.providers.base import ResolvedPlace

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local

MUMBAI = ResolvedPlace(label="Mumbai", lat=19.076, lon=72.8777, tz="Asia/Kolkata")
DELHI = ResolvedPlace(label="Delhi", lat=28.6139, lon=77.209, tz="Asia/Kolkata")
JAIPUR = ResolvedPlace(label="Jaipur", lat=26.9124, lon=75.7873, tz="Asia/Kolkata")


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        mongodb_uri=MONGO_URI,
        mongo_db=f"sitara_test_{uuid.uuid4().hex[:8]}",
        cookie_secure=False,
    )


@pytest_asyncio.fixture()
async def db(settings: Settings) -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
    database = client[settings.mongo_db]
    await ensure_indexes(database)
    yield database
    await client.drop_database(settings.mongo_db)
    client.close()


@pytest.fixture()
def cache(db) -> PanchangCache:  # noqa: ANN001
    return PanchangCache(db)


@pytest.fixture()
def transit_cache(db) -> TransitCache:  # noqa: ANN001
    return TransitCache(db)


@pytest.fixture()
def mongo() -> Iterator[MongoClient]:
    client: MongoClient = MongoClient(MONGO_URI)
    yield client
    client.close()


def assert_envelope(body: dict, code: str, retryable: bool) -> None:
    """§34.4 — the one canonical error shape, nothing more, nothing less."""
    assert set(body.keys()) == {"code", "message_key", "trace_id", "retryable"}
    assert body["code"] == code
    assert body["retryable"] is retryable
    assert body["trace_id"]
