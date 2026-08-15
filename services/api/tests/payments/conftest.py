"""Payments test harness (§30.3, §22.13).

Mongo comes from the dev compose stack on 27018, never a machine-local mongod
and never a fake — the same rule `tests/db`, `tests/panchang` and
`tests/memory` follow, and here it earns its keep twice over.

**§6.4's indexes are half of what is under test.** `payments.provider_event_id`
is UNIQUE, and that index is the duplicate-webhook guard. A fake dict-store
would accept the second write happily and the suite would prove that the
application-level check works while the thing that actually has to hold — a
race between two webhook deliveries landing in two processes at once — went
unexercised. The M5 lesson (root CLAUDE.md) was a fake accepting string ids
where §6.4 wanted objectId; this would be the same lesson about money.

The provider is the SIMULATOR, which is the only implementation there is
(`payments.providers.routing`). That is not a test double: it is the shipped
arm for this milestone, so these tests exercise the real code path a demo
runs, and nothing here reaches a network.
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
from sitara_api.payments.providers.simulator import SimulatedRail
from sitara_api.payments.service import PaymentService

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local

#: A fixed instant. Every clock in this module is injected, so nothing here
#: depends on when the suite runs — which matters more than usual: half of
#: §22.13 is a boundary a day either side of.
NOW = dt.datetime(2026, 8, 15, 9, 0, tzinfo=dt.UTC)

USER_ID = ObjectId("6b70000000000000000000a1")
GIVER_ID = ObjectId("6b70000000000000000000a2")
OTHER_USER_ID = ObjectId("6b70000000000000000000a3")


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    # `tz_aware=True`, exactly as `db.make_mongo` sets it in production. BSON
    # stores UTC and the DEFAULT codec hands it back NAIVE, so a subscription
    # read from Mongo and compared against §22.13's aware clock raises
    # TypeError mid-arithmetic. The memory module's decay job hit this and the
    # panchang cache carried a local workaround for it; a payments harness that
    # differed from production here would be testing different datetimes from
    # the ones the app compares.
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()


@pytest.fixture()
def rail() -> SimulatedRail:
    """The simulator, with no faults armed.

    Each test that wants a failure arms it explicitly — `rail.arm(...)` — so a
    reader can see from the test body alone which of §30.3's states is being
    exercised. A rail configured in a fixture would make half these tests read
    as though the happy path had simply misbehaved.
    """
    return SimulatedRail()


@pytest.fixture()
def service(db, rail: SimulatedRail) -> PaymentService:  # noqa: ANN001
    return PaymentService(db, rail)
