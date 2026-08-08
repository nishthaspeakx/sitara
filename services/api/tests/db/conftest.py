"""Data-layer test harness.

Mongo comes from the dev compose stack on 27018 (never a machine-local mongod),
each test gets its own database, and the database is dropped afterwards — the
same pattern as tests/panchang/conftest.py.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from sitara_api.config import Settings
from sitara_api.db.schema import ensure_schema

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local


@pytest.fixture()
def settings() -> Settings:
    db_name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    return Settings(
        environment="test",
        mongodb_uri=MONGO_URI,
        mongo_db=db_name,
        # Key vault per test database, so a test's data keys die with it.
        csfle_key_vault_namespace=f"{db_name}.__keyvault",
        cookie_secure=False,
    )


@pytest_asyncio.fixture()
async def raw_db(settings: Settings) -> AsyncIterator:
    """An empty database — no collections, no indexes."""
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
    database = client[settings.mongo_db]
    yield database
    await client.drop_database(settings.mongo_db)
    client.close()


@pytest_asyncio.fixture()
async def db(raw_db) -> AsyncIterator:  # noqa: ANN001
    """A database built to the §6.4 registry."""
    await ensure_schema(raw_db)
    yield raw_db
