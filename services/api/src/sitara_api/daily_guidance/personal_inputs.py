"""The user's own words, for §28.2's three fact-free contextual cards.

`priorities`, `goal_check` and `family_reminder` are the three of §34.3's
seventeen that make no astrological claim, so the ranking engine gates them on
`RankingContext.available_inputs` rather than on a fact-ID (`ranking.MODULE_INPUTS`).
**Nothing built that dict.** The scheduled task called `generate_on_open`
without it, the set was therefore always empty, and all three modules were
structurally unreachable in a real brief — three of the seventeen, and the
three most personal ones, silently absent since M6.

This module is the loader. Three rules hold it:

**A slug is not a sentence.** `profiles.priorities` stores the ids S11 recorded
("career", "family"); the catalog owns the words. Passing the slug through would
put "You said career matters most right now" in front of a Hindi user — an
English token inside a Devanagari sentence, which is exactly what §2.4 forbids
and what the dev switcher manufactured before it was fixed. A priority we cannot
name in this locale yields no card.

**A goal is already in the user's words.** `goals.text` is what they typed, so it
is used verbatim and never translated. Translating a person's own sentence back
at them would be a stranger's paraphrase of their intention.

**A name we cannot read is not a reminder.** `family_members.name` is CSFLE
encrypted under the `birth` key class (§6.4). Without the codec it reads back as
ciphertext, and a family card rendered from a BSON blob is worse than no family
card — so an unreadable name declines, the same way the composer declines a
missing term.
"""

from __future__ import annotations

import datetime as dt
import logging

from bson import ObjectId

from sitara_api.daily_guidance.types import BriefSubject
from sitara_api.localisation import MissingString, resolve

logger = logging.getLogger(__name__)

#: Goal statuses that are still live. A closed goal is not a check-in.
OPEN_GOAL_STATUSES: frozenset[str] = frozenset({"open", "active", "in_progress"})

#: How far ahead a family date counts as "coming up" (§28.2's family reminder).
#: A week: near enough to act on, far enough to prepare for.
FAMILY_HORIZON_DAYS = 7


async def load_inputs(
    db,  # noqa: ANN001
    subject: BriefSubject,
    *,
    local_date: str,
) -> dict[str, str]:
    """Everything the three fact-free modules need, or as much as exists.

    Returns only the keys it could fill. `ranking.emittable` reads membership,
    so an absent key is a module that does not appear — which is the correct
    answer when a user has set no priorities, not a card with a blank in it.
    """
    oid = ObjectId(subject.user_id)
    inputs: dict[str, str] = {}

    priority = await _priority(db, oid, subject.locale)
    if priority:
        inputs["priorities"] = priority

    goal = await _goal(db, oid)
    if goal:
        inputs["goals"] = goal

    family = await _family_event(db, oid, local_date, subject.locale)
    if family:
        inputs["family_member"], inputs["family_events"] = family

    return inputs


async def _priority(db, oid: ObjectId, locale: str) -> str | None:  # noqa: ANN001
    """The first priority S11 recorded, in this locale's own words."""
    profile = await db.profiles.find_one({"user_id": oid}) or {}
    for slug in profile.get("priorities") or ():
        if not isinstance(slug, str):
            continue
        try:
            return resolve(f"start.priorities.option.{slug}", locale)
        except MissingString:
            # An unrecognised slug, or a locale that never got the label. Either
            # way §2.4 forbids the English fallback, so try the next one.
            logger.warning(
                "priority not nameable in locale",
                extra={"slug": slug, "locale": locale},
            )
    return None


async def _goal(db, oid: ObjectId) -> str | None:  # noqa: ANN001
    """One open goal, in the words the user typed."""
    goal = await db.goals.find_one(
        {"user_id": oid, "status": {"$in": list(OPEN_GOAL_STATUSES)}},
        sort=[("review_at", 1)],
    )
    text = (goal or {}).get("text")
    return text if isinstance(text, str) and text.strip() else None


async def _family_event(
    db,  # noqa: ANN001
    oid: ObjectId,
    local_date: str,
    locale: str,
) -> tuple[str, str] | None:
    """A family occasion inside the horizon, and whose it is.

    Reads the family member's birth date through the same `birth_details`
    collection the astrology facade uses. Both the name and the date are CSFLE
    fields; when the codec is absent they come back as bytes and this declines
    rather than composing a card around a blob.
    """
    try:
        today = dt.date.fromisoformat(local_date)
    except ValueError:
        return None

    # Collected, then the SOONEST wins. Returning the first match made the card
    # depend on Mongo's iteration order, so a user with two birthdays in the
    # window saw an arbitrary one of them — and a different one on a re-generate.
    candidates: list[tuple[int, str]] = []

    async for member in db.family_members.find({"owner_user_id": oid}):
        name = member.get("name")
        if not isinstance(name, str) or not name.strip():
            # Ciphertext, or a member with no name recorded.
            continue
        if not member.get("has_birth_details"):
            continue

        birth = await db.birth_details.find_one({"family_member_id": member["_id"]})
        raw = (birth or {}).get("date")
        if not isinstance(raw, str):
            continue
        try:
            born = dt.date.fromisoformat(raw)
        except ValueError:
            continue

        days = _days_until_anniversary(born, today)
        if days is None or days > FAMILY_HORIZON_DAYS:
            continue
        candidates.append((days, name))

    if not candidates:
        return None
    days, name = min(candidates, key=lambda pair: pair[0])

    try:
        occasion = (
            resolve("brief.family.birthday_today", locale)
            if days == 0
            else resolve("brief.family.birthday", locale, days=days)
        )
    except MissingString:
        logger.warning("family occasion missing in locale", extra={"locale": locale})
        return None
    return name, occasion


def _days_until_anniversary(born: dt.date, today: dt.date) -> int | None:
    """Days from `today` to the next anniversary of `born`.

    29 February is the case worth naming: a person born on a leap day has no
    anniversary in most years, and inventing one (28 Feb? 1 March?) is a choice
    the product has not made. Until it does, they get no card rather than the
    wrong day.
    """
    try:
        this_year = born.replace(year=today.year)
    except ValueError:
        return None
    if this_year < today:
        try:
            this_year = born.replace(year=today.year + 1)
        except ValueError:
            return None
    return (this_year - today).days
