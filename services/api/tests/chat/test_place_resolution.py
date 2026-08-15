"""Which city a place-anchored answer is computed for (§30.2, §5.3 step 3).

The companion to `birth.py`'s own lesson, one field over, and found the same
way: by a live conversation rather than by a test.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from sitara_api.chat_orchestration.birth import place_label_for
from sitara_api.db import ensure_indexes
from sitara_api.db.documents import stamp

pytestmark = pytest.mark.asyncio()

MONGO_URI = "mongodb://localhost:27018"
USER = ObjectId()


class _State:
    def __init__(self, db) -> None:  # noqa: ANN001
        self.db = db


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()


async def _profile(db, place: dict | None) -> None:  # noqa: ANN001
    await db.profiles.insert_one(
        stamp({"_id": ObjectId(), "user_id": USER, "brief_place": place})
    )


async def test_the_stored_brief_place_fills_a_silent_request(db) -> None:  # noqa: ANN001
    """No client sends `place_label`, so before this every live turn ran with
    `has_current_location: False`.

    §5.3's required-data check then reported the current location missing and
    S18's very first suggestion chip — "How is my day looking?" — was answered
    with "Timings change with where you are. Which city should I use?" against
    an account whose city was in `profiles` the whole time.
    """
    await _profile(db, {"label": "Bengaluru", "lat": 12.97, "lon": 77.59, "tz": "Asia/Kolkata"})

    assert await place_label_for(_State(db), str(USER)) == "Bengaluru"


async def test_a_supplied_place_still_wins(db) -> None:  # noqa: ANN001
    """§30.2: "any muhurat query accepts an explicit place ('wedding in
    Jaipur') — computed for THAT place". A per-question override is not a
    profile change, so the fallback only fills a silence."""
    await _profile(db, {"label": "Bengaluru", "lat": 12.97, "lon": 77.59, "tz": "Asia/Kolkata"})

    assert await place_label_for(_State(db), str(USER), "Jaipur") == "Jaipur"


async def test_a_timezone_is_never_used_as_a_city(db) -> None:  # noqa: ANN001
    """§30.2: a zone is not a place. "Asia/Kolkata" is a label nobody chose,
    and putting it on a timings screen would be worse than asking."""
    await _profile(db, {"tz": "Asia/Kolkata"})

    assert await place_label_for(_State(db), str(USER)) is None


async def test_no_profile_declines_rather_than_guessing(db) -> None:  # noqa: ANN001
    """§5.3. Tara asks, which is a worse answer and never a wrong one."""
    assert await place_label_for(_State(db), str(ObjectId())) is None
