"""Astrology test harness — real compose mongo.

The same shape `tests/family/conftest.py` uses, for the reason
`tests/memory/conftest.py` gives: `birth_details` is a §6.4 collection with a
validator, and a test that writes past it proves nothing about the reads that
run against the real one.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from sitara_api.db import ensure_indexes

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()
