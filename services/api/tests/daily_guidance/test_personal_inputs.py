"""The three fact-free modules' inputs (§28.2's contextual row, §34.3's 8/13/15).

These three were structurally unreachable in a real brief until this loader
existed: `ranking.MODULE_INPUTS` gates them on `available_inputs`, and nothing
built that dict. So the tests worth having are the ones about what the loader
DECLINES — an absent key is a module that does not render, which is the honest
answer, and a wrong one is a card with a slug or a ciphertext blob in it.
"""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.daily_guidance.personal_inputs import (
    FAMILY_HORIZON_DAYS,
    _days_until_anniversary,
    load_inputs,
)
from sitara_api.daily_guidance.types import BriefSubject, Density, Tier

pytestmark = pytest.mark.asyncio

USER = ObjectId("6a70000000000000000000a1")
LOCAL_DATE = "2026-08-12"


def subject(locale: str = "en") -> BriefSubject:
    return BriefSubject(
        user_id=str(USER),
        locale=locale,
        timezone="Asia/Kolkata",
        brief_time="07:00",
        density=Density.MED,
        tier=Tier.PAYING,
    )


class _Cursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def __aiter__(self):  # noqa: ANN204
        async def gen():  # noqa: ANN202
            for doc in self._docs:
                yield doc

        return gen()


class _Collection:
    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = docs or []

    async def find_one(self, query: dict, sort=None) -> dict | None:  # noqa: ANN001, ARG002
        for doc in self.docs:
            if all(_matches(doc.get(k), v) for k, v in query.items()):
                return doc
        return None

    def find(self, query: dict) -> _Cursor:
        return _Cursor(
            [d for d in self.docs if all(_matches(d.get(k), v) for k, v in query.items())]
        )


def _matches(value, expected) -> bool:  # noqa: ANN001
    if isinstance(expected, dict) and "$in" in expected:
        return value in expected["$in"]
    return value == expected


class _Db:
    def __init__(self, **collections) -> None:  # noqa: ANN003
        self.profiles = collections.get("profiles", _Collection())
        self.goals = collections.get("goals", _Collection())
        self.family_members = collections.get("family_members", _Collection())
        self.birth_details = collections.get("birth_details", _Collection())


# ---------------------------------------------------------------------------
# priorities — a slug is not a sentence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("locale", "expected"),
    [("en", "Work & career"), ("hi", "काम और करियर"), ("hi-Latn", "Kaam aur career")],
)
async def test_a_priority_arrives_in_the_users_own_language(locale, expected) -> None:  # noqa: ANN001
    """§2.4. `profiles.priorities` holds S11's ids; the catalog owns the words.

    Passing the slug through would put "You said career matters most right now"
    in front of a Hindi user — an English token inside a Devanagari sentence.
    """
    db = _Db(profiles=_Collection([{"user_id": USER, "priorities": ["career"]}]))
    inputs = await load_inputs(db, subject(locale), local_date=LOCAL_DATE)
    assert inputs["priorities"] == expected


async def test_an_unnameable_priority_is_skipped_not_guessed() -> None:
    """A slug with no label in this locale yields no card, and the next
    priority gets its turn — §2.4 has no English fallback."""
    db = _Db(profiles=_Collection([{"user_id": USER, "priorities": ["not_a_priority", "family"]}]))
    inputs = await load_inputs(db, subject("hi"), local_date=LOCAL_DATE)
    assert inputs["priorities"] == "परिवार"


async def test_no_priorities_means_no_priorities_key() -> None:
    """`ranking.emittable` reads membership, so an absent key is a module that
    does not appear — the correct answer for a user who set none."""
    db = _Db(profiles=_Collection([{"user_id": USER}]))
    inputs = await load_inputs(db, subject(), local_date=LOCAL_DATE)
    assert "priorities" not in inputs


# ---------------------------------------------------------------------------
# goals — already in the user's words
# ---------------------------------------------------------------------------


async def test_a_goal_is_used_verbatim() -> None:
    """`goals.text` is what the person typed. Translating their own sentence
    back at them would be a stranger's paraphrase of their intention."""
    db = _Db(goals=_Collection([{"user_id": USER, "status": "open", "text": "finish the move"}]))
    inputs = await load_inputs(db, subject("hi"), local_date=LOCAL_DATE)
    assert inputs["goals"] == "finish the move"


async def test_a_closed_goal_is_not_a_check_in() -> None:
    db = _Db(goals=_Collection([{"user_id": USER, "status": "done", "text": "finish the move"}]))
    inputs = await load_inputs(db, subject(), local_date=LOCAL_DATE)
    assert "goals" not in inputs


# ---------------------------------------------------------------------------
# family — a name we cannot read is not a reminder
# ---------------------------------------------------------------------------


async def test_a_family_birthday_inside_the_horizon_composes() -> None:
    db = _Db(
        family_members=_Collection(
            [{"_id": ObjectId(), "owner_user_id": USER, "name": "Aai", "has_birth_details": True}]
        ),
    )
    member_id = db.family_members.docs[0]["_id"]
    db.birth_details = _Collection([{"family_member_id": member_id, "date": "1962-08-15"}])

    inputs = await load_inputs(db, subject(), local_date=LOCAL_DATE)
    assert inputs["family_member"] == "Aai"
    assert "3 days" in inputs["family_events"]


async def test_a_ciphertext_name_declines(caplog) -> None:  # noqa: ANN001
    """§6.4 encrypts `family_members.name` under the `birth` key class. Without
    the codec it reads back as bytes, and a card composed around a BSON blob is
    worse than no card at all."""
    db = _Db(
        family_members=_Collection(
            [
                {
                    "_id": ObjectId(),
                    "owner_user_id": USER,
                    "name": b"\x01ciphertext",
                    "has_birth_details": True,
                }
            ]
        ),
    )
    inputs = await load_inputs(db, subject(), local_date=LOCAL_DATE)
    assert "family_member" not in inputs


async def test_a_date_beyond_the_horizon_is_not_a_reminder() -> None:
    db = _Db(
        family_members=_Collection(
            [{"_id": ObjectId(), "owner_user_id": USER, "name": "Aai", "has_birth_details": True}]
        ),
    )
    member_id = db.family_members.docs[0]["_id"]
    db.birth_details = _Collection([{"family_member_id": member_id, "date": "1962-11-02"}])
    inputs = await load_inputs(db, subject(), local_date=LOCAL_DATE)
    assert "family_events" not in inputs


def test_a_leap_day_birthday_gets_no_card_rather_than_the_wrong_one() -> None:
    """29 February has no anniversary in most years, and choosing 28 Feb or
    1 March is a decision the product has not made. Until it does, silence."""
    assert _days_until_anniversary(dt.date(2000, 2, 29), dt.date(2026, 8, 12)) is None
    # And an ordinary date still resolves, including across the year boundary.
    assert _days_until_anniversary(dt.date(1990, 1, 3), dt.date(2026, 12, 30)) == 4


def test_the_horizon_is_a_week() -> None:
    """Near enough to act on, far enough to prepare for."""
    assert FAMILY_HORIZON_DAYS == 7


async def test_the_soonest_birthday_wins_not_the_first_row() -> None:
    """Two dates inside the horizon must resolve deterministically.

    Returning the first match made the card depend on Mongo's iteration order:
    a user with two birthdays that week saw an arbitrary one, and potentially a
    different one after a regenerate — the same brief, re-read, naming someone
    else.
    """
    aai, kaka = ObjectId(), ObjectId()
    db = _Db(
        family_members=_Collection(
            [
                {"_id": aai, "owner_user_id": USER, "name": "Aai", "has_birth_details": True},
                {"_id": kaka, "owner_user_id": USER, "name": "Kaka", "has_birth_details": True},
            ]
        ),
    )
    db.birth_details = _Collection(
        [
            {"family_member_id": aai, "date": "1962-08-17"},  # 5 days out
            {"family_member_id": kaka, "date": "1958-08-14"},  # 2 days out
        ]
    )
    inputs = await load_inputs(db, subject(), local_date=LOCAL_DATE)
    assert inputs["family_member"] == "Kaka"
    assert "2 days" in inputs["family_events"]
