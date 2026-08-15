"""The night reflection (§10-17, §27's day-binding row).

The tests worth having are about the two rules that are easy to break by
being helpful: one row per local date bound at CREATION, and no streak
anywhere. Both fail silently — a re-derived date moves a reflection to the
wrong day only for travellers, and a streak counter is a feature somebody adds
because it seems motivating.
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
from sitara_api.reflection.models import PROMPT_ORDER, Mood, Prompt, Reflection
from sitara_api.reflection.service import ReflectionService

MONGO_URI = "mongodb://localhost:27018"
NOW = dt.datetime(2026, 8, 15, 21, 40, tzinfo=dt.UTC)
USER_ID = ObjectId("6a70000000000000000000d1")

pytestmark = pytest.mark.asyncio


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
def service(db) -> ReflectionService:  # noqa: ANN001
    return ReflectionService(db)


# --- the ceremony ----------------------------------------------------------


async def test_three_prompts_in_a_fixed_order() -> None:
    """§10-17: "3 prompts". Not two, not four, and the order is the ceremony."""
    assert len(PROMPT_ORDER) == 3
    assert PROMPT_ORDER == (Prompt.GRATITUDE, Prompt.WEIGHT, Prompt.TOMORROW)


async def test_a_reflection_saves_what_she_wrote(service: ReflectionService) -> None:
    reflection = await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="hi-Latn",
        entries={
            Prompt.GRATITUDE: "amma called",
            Prompt.WEIGHT: "the lease is still open",
            Prompt.TOMORROW: "call the broker",
        },
        mood=Mood.STEADY,
        now=NOW,
    )

    assert {e.prompt for e in reflection.entries} == set(PROMPT_ORDER)
    assert reflection.mood is Mood.STEADY
    assert reflection.locale == "hi-Latn"


async def test_a_partial_reflection_is_a_reflection(service: ReflectionService) -> None:
    """§24.6: no dead ends. One prompt answered is a night that counted."""
    reflection = await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "amma called"},
        now=NOW,
    )

    assert reflection.is_started is True
    assert len(reflection.entries) == 1


async def test_an_empty_answer_is_not_stored_as_an_entry(
    service: ReflectionService,
) -> None:
    """A blank textarea she tabbed past is not a thought she had."""
    reflection = await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "amma called", Prompt.WEIGHT: "   "},
        now=NOW,
    )

    assert [e.prompt for e in reflection.entries] == [Prompt.GRATITUDE]


async def test_mood_is_optional(service: ReflectionService) -> None:
    reflection = await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "amma called"},
        now=NOW,
    )

    assert reflection.mood is None


# --- §27's day binding -----------------------------------------------------


async def test_one_reflection_per_local_date(service: ReflectionService, db) -> None:
    """§6.4's unique (user_id, date) index, doing the work rather than a check
    that could be raced."""
    await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "first"},
        now=NOW,
    )
    await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "second"},
        now=NOW,
    )

    assert await db.night_reflections.count_documents({"user_id": USER_ID}) == 1


async def test_returning_later_continues_the_same_night(
    service: ReflectionService,
) -> None:
    """She answers one prompt, closes the sheet, comes back after brushing her
    teeth. That is a continuation, not a second reflection."""
    await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "amma called"},
        now=NOW,
    )
    resumed = await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={
            Prompt.GRATITUDE: "amma called",
            Prompt.TOMORROW: "call the broker",
        },
        now=NOW + dt.timedelta(minutes=6),
    )

    assert len(resumed.entries) == 2


async def test_the_creation_date_is_not_moved_by_a_later_write(
    service: ReflectionService, db
) -> None:
    """§27: "binds to user-local calendar day at creation".

    The traveller's case: she starts a reflection in Delhi and finishes it
    after landing, when her local date has already rolled over. A service that
    re-derived the date on write would split one night across two rows and
    leave the first half orphaned on a day she was not there for.
    """
    await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "started before the flight"},
        now=NOW,
    )

    await service.save(
        user_id=USER_ID,
        date="2026-08-15",  # the caller passes the BOUND date, not today's
        locale="en",
        entries={
            Prompt.GRATITUDE: "started before the flight",
            Prompt.TOMORROW: "finished after landing",
        },
        now=NOW + dt.timedelta(hours=9),
    )

    rows = [doc async for doc in db.night_reflections.find({"user_id": USER_ID})]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-15"
    assert rows[0]["created_at"] == NOW, "created_at is not moved by an update"


async def test_a_different_date_is_a_different_night(
    service: ReflectionService, db
) -> None:
    await service.save(
        user_id=USER_ID, date="2026-08-15", locale="en",
        entries={Prompt.GRATITUDE: "a"}, now=NOW,
    )
    await service.save(
        user_id=USER_ID, date="2026-08-16", locale="en",
        entries={Prompt.GRATITUDE: "b"}, now=NOW + dt.timedelta(days=1),
    )

    assert await db.night_reflections.count_documents({"user_id": USER_ID}) == 2


# --- §10-17's prohibition --------------------------------------------------


async def test_nothing_in_this_module_can_express_a_streak(
    service: ReflectionService,
) -> None:
    """§10-17: "no streaks, no guilt".

    Enforced by absence, and absence is what rots — somebody adds a helpful
    counter and nothing fails. So this asserts the STRUCTURE rather than
    grepping the text: a prose sentence explaining why there is no streak is
    not a streak, and a test that cannot tell the difference is one people
    learn to work around.
    """
    import dataclasses

    from sitara_api.reflection.models import Reflection as ReflectionType

    forbidden = ("streak", "missed", "completion", "consecutive", "score")

    field_names = {f.name for f in dataclasses.fields(ReflectionType)}
    assert not [f for f in field_names if any(w in f for w in forbidden)]

    surface = {name for name in dir(service) if not name.startswith("_")}
    assert not [name for name in surface if any(w in name for w in forbidden)]

    # And nothing is written that the type does not carry.
    saved = await service.save(
        user_id=USER_ID,
        date="2026-08-15",
        locale="en",
        entries={Prompt.GRATITUDE: "amma called"},
        now=NOW,
    )
    stored = await service._db.night_reflections.find_one(  # noqa: SLF001
        {"_id": saved.reflection_id}
    )
    assert not [k for k in stored if any(w in k for w in forbidden)]


async def test_recent_returns_only_nights_she_wrote(
    service: ReflectionService,
) -> None:
    """Not "the last 30 days with the blanks filled in" — a list of empty
    nights is a guilt surface with a different name."""
    await service.save(
        user_id=USER_ID, date="2026-08-15", locale="en",
        entries={Prompt.GRATITUDE: "a"}, now=NOW,
    )
    await service.save(
        user_id=USER_ID, date="2026-08-12", locale="en",
        entries={Prompt.GRATITUDE: "b"}, now=NOW,
    )

    recent = await service.recent(USER_ID)

    assert [r.date for r in recent] == ["2026-08-15", "2026-08-12"]


async def test_a_reflection_for_a_night_she_skipped_is_simply_absent(
    service: ReflectionService,
) -> None:
    assert await service.get(USER_ID, "2026-08-14") is None


# --- reading back ----------------------------------------------------------


async def test_an_unreadable_entry_renders_as_empty_not_as_ciphertext(
    service: ReflectionService, db
) -> None:
    """§6.4 CSFLE-encrypts `entries`. Read without the codec it is Binary, and
    a reflection that showed the repr of a Binary would look like corruption
    to the person who wrote it."""
    await db.night_reflections.insert_one(
        {
            "_id": ObjectId(),
            "user_id": USER_ID,
            "date": "2026-08-15",
            "entries": [b"\x00ciphertext"],
            "memory_chips": [],
            "locale": "en",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )

    reflection = await service.get(USER_ID, "2026-08-15")

    assert isinstance(reflection, Reflection)
    assert reflection.entries == ()
