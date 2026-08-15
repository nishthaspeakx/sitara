"""Whose birth row is whose (§32.15, §5.3, S28).

Both cases here were found by the first live walkthrough, and neither had a
test — because until M10 nothing had ever written birth details for a family
member, so the query that could not tell them apart had nothing to confuse.
"""

from __future__ import annotations

import datetime as dt

import pytest
import pytest_asyncio
from bson import ObjectId

from sitara_api.astrology.service import AstrologyFacade
from sitara_api.db.documents import stamp

pytestmark = pytest.mark.asyncio()

OWNER = ObjectId()
MEMBER = ObjectId()


def _row(*, user_id: ObjectId, member_id: ObjectId | None, date: str, accuracy: str) -> dict:
    return stamp(
        {
            "_id": ObjectId(),
            "user_id": user_id,
            "family_member_id": member_id,
            "date": date,
            "time": "05:40",
            "time_accuracy": accuracy,
            "place": {
                "name": "Bengaluru",
                "label": "Bengaluru",
                "lat": 12.97,
                "lon": 77.59,
                "tz": "Asia/Kolkata",
            },
            "tz_snapshot": {
                "tz": "Asia/Kolkata",
                "resolved_at": dt.datetime.now(dt.UTC).isoformat(),
                "source": "gazetteer",
            },
            "rectification_notes": None,
        }
    )


@pytest_asyncio.fixture()
async def seeded(db):  # noqa: ANN001, ANN201
    """One account holder and one family member, both with birth details.

    The order matters: the member's row is inserted FIRST, so a query that does
    not pin `family_member_id` returns it in natural order for the owner — which
    is exactly how the defect presented.
    """
    await db.birth_details.insert_one(
        _row(user_id=OWNER, member_id=MEMBER, date="1962-03-11", accuracy="exact")
    )
    await db.birth_details.insert_one(
        _row(user_id=OWNER, member_id=None, date="1990-07-02", accuracy="approximate")
    )
    return db


async def test_the_owners_own_chart_is_never_a_family_members(seeded) -> None:  # noqa: ANN001
    """The serious half.

    `find_one({"user_id": owner})` matches every row that user OWNS, their
    mother's included, and returns natural order. An account with one family
    member could be shown their mother's chart as their own — with every
    confidence chip reading `verified`, because the row is complete and is
    genuinely theirs to hold. Nothing about it looks wrong.
    """
    facade = AstrologyFacade(db=seeded, adapter=None, crypto=None)

    birth = await facade.birth_input(str(OWNER))

    assert birth is not None
    assert birth.date == dt.date(1990, 7, 2), "the OWNER's row, not the member's"


async def test_a_family_members_chart_resolves_at_all(seeded) -> None:  # noqa: ANN001
    """§32.15's members are addressed by MEMBER id (`astrology/router.py` passes
    `subject_id`), and their row carries the OWNER's `user_id`.

    Looking up `{"user_id": member_id}` matched nothing, so S28 — the first
    product surface that draws CC-007's kundli — declined for every family
    member with ASTRO_INSUFFICIENT_BIRTH_DATA while the screen said "Birth
    details on file" one line above it.
    """
    facade = AstrologyFacade(db=seeded, adapter=None, crypto=None)

    birth = await facade.birth_input(str(MEMBER))

    assert birth is not None
    assert birth.date == dt.date(1962, 3, 11)


async def test_time_accuracy_follows_the_same_subject(seeded) -> None:  # noqa: ANN001
    """The accuracy reader had the identical query, so it had the identical
    bug — and §5.4 renders it ON the artefact. A member's `exact` read as the
    owner's `approximate` would label a correct diamond a guess, and the
    reverse would label a guess a certainty.
    """
    facade = AstrologyFacade(db=seeded, adapter=None, crypto=None)

    assert await facade.time_accuracy(str(OWNER)) == "approximate"
    assert await facade.time_accuracy(str(MEMBER)) == "exact"


async def test_a_subject_with_no_row_declines(db) -> None:  # noqa: ANN001
    """§5.3: the engine declines rather than guessing, and so does this."""
    facade = AstrologyFacade(db=db, adapter=None, crypto=None)
    assert await facade.birth_input(str(ObjectId())) is None
    assert await facade.time_accuracy(str(ObjectId())) == "unknown"
