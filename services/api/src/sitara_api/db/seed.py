"""`python -m sitara_api.db.seed` — synthetic dev data (§22.12).

§22.12: "Staging and development environments use synthetic seed data only
(generated personas with fictitious birth data); production PII never leaves
production."

That rule is enforced here in three ways, all of which fail closed:

1. The seeder refuses to run unless `environment` is dev or test.
2. It refuses to run against a Mongo host that is not local/compose.
3. Every value it writes is drawn from reserved, unroutable ranges — phone
   numbers from the +91 99999 test block, emails at `@example.invalid`
   (RFC 2606, permanently unresolvable), and birth places/dates that are
   fictitious by construction.

Every document carries `synthetic: true` so anything that later finds real data
in a dev database can tell the two apart immediately.

The personas exist to exercise the product's real variation, not to be
realistic people: three locales, both corridors (metro India and diaspora), the
range of §10.6 birth-time accuracies, memory consent granted and withheld, and
trial against paid.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from bson import ObjectId

from sitara_api.config import Settings
from sitara_api.db.connection import MongoDb, make_mongo
from sitara_api.db.documents import stamp
from sitara_api.db.schema import ensure_schema

SYNTHETIC_FLAG = "synthetic"

#: RFC 2606 reserves .invalid; nothing here can ever resolve or receive mail.
EMAIL_DOMAIN = "example.invalid"
#: India's reserved test-number block — never allocated to a subscriber.
PHONE_PREFIX = "+9199999"

ALLOWED_ENVIRONMENTS = frozenset({"dev", "test", "local"})
ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "mongo", "mongodb"})

SEEDED_COLLECTIONS = (
    "users",
    "auth_identities",
    "profiles",
    "birth_details",
    "family_members",
    "consents",
    "conversations",
    "goals",
    "subscriptions",
)


class UnsafeSeedError(RuntimeError):
    """The seeder was pointed somewhere it must never write."""


@dataclass(frozen=True)
class Persona:
    handle: str
    locale: str
    script_pref: str
    timezone: str
    birth_date: str
    birth_time: str | None
    time_accuracy: str  # §10.6: exact | plus_minus_30 | day_part | unknown
    place_label: str
    place_lat: float
    place_lon: float
    priorities: tuple[str, ...]
    memory_consent: bool
    plan: str
    subscription_status: str
    region: str
    family: tuple[tuple[str, str], ...] = ()  # (relation, name)


#: Fictitious throughout. Names are common given names used as placeholders, not
#: references to anyone; dates and times are invented.
PERSONAS: tuple[Persona, ...] = (
    Persona(
        handle="asha",
        locale="hi",
        script_pref="deva",
        timezone="Asia/Kolkata",
        birth_date="1988-03-14",
        birth_time="04:55",
        time_accuracy="exact",
        place_label="Jaipur",
        place_lat=26.9124,
        place_lon=75.7873,
        priorities=("family", "spiritual_growth", "health_adjacent"),
        memory_consent=True,
        plan="premium",
        subscription_status="active",
        region="IN",
        family=(("mother", "Sunita"), ("daughter", "Ira")),
    ),
    Persona(
        handle="meera",
        locale="hi-Latn",
        script_pref="latn",
        timezone="Asia/Kolkata",
        birth_date="1993-11-02",
        birth_time="21:10",
        time_accuracy="plus_minus_30",
        place_label="Mumbai",
        place_lat=19.076,
        place_lon=72.8777,
        priorities=("career", "relationships"),
        memory_consent=True,
        plan="basic",
        subscription_status="trialing",
        region="IN",
    ),
    Persona(
        handle="ritu",
        locale="en",
        script_pref="latn",
        timezone="America/New_York",
        birth_date="1985-07-21",
        birth_time=None,
        time_accuracy="unknown",
        place_label="Delhi",
        place_lat=28.6139,
        place_lon=77.209,
        priorities=("wealth", "career", "family"),
        memory_consent=False,  # §32.4: consent is per-chip and may be withheld
        plan="premium",
        subscription_status="active",
        region="US",
    ),
    Persona(
        handle="kavita",
        locale="en",
        script_pref="latn",
        timezone="Europe/London",
        birth_date="1979-01-09",
        birth_time="14:30",
        time_accuracy="day_part",
        place_label="Chennai",
        place_lat=13.0827,
        place_lon=80.2707,
        priorities=("health_adjacent", "spiritual_growth"),
        memory_consent=True,
        plan="basic",
        subscription_status="trialing",
        region="UK",
        family=(("husband", "Arun"),),
    ),
    Persona(
        handle="divya",
        locale="hi-Latn",
        script_pref="latn",
        timezone="Asia/Dubai",
        birth_date="1996-05-30",
        birth_time="08:05",
        time_accuracy="exact",
        place_label="Ahmedabad",
        place_lat=23.0225,
        place_lon=72.5714,
        priorities=("relationships", "career"),
        memory_consent=False,
        plan="basic",
        subscription_status="cancelled",
        region="AE",
    ),
    Persona(
        handle="lata",
        locale="hi",
        script_pref="deva",
        timezone="Asia/Kolkata",
        birth_date="1972-09-17",
        birth_time="23:45",
        time_accuracy="plus_minus_30",
        place_label="Lucknow",
        place_lat=26.8467,
        place_lon=80.9462,
        priorities=("family", "spiritual_growth"),
        memory_consent=True,
        plan="premium",
        subscription_status="active",
        region="IN",
    ),
)


def assert_safe(settings: Settings) -> None:
    """Fail closed before a single document is written."""
    if settings.environment not in ALLOWED_ENVIRONMENTS:
        raise UnsafeSeedError(
            f"§22.12: synthetic seeding is dev/test only and environment is "
            f"{settings.environment!r}"
        )
    host = urlsplit(settings.mongodb_uri).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise UnsafeSeedError(
            f"§22.12: refusing to seed a non-local database (host {host!r}) — production "
            "data and dev data never share a host"
        )


def _email(persona: Persona) -> str:
    return f"{persona.handle}@{EMAIL_DOMAIN}"


def _phone(index: int) -> str:
    return f"{PHONE_PREFIX}{index:05d}"


def is_synthetic_contact(value: str) -> bool:
    """Used by the tests, and by anything that wants to assert a dev database
    holds nothing real."""
    return value.endswith(f"@{EMAIL_DOMAIN}") or value.startswith(PHONE_PREFIX)


async def wipe(db: MongoDb) -> int:
    """Remove seeded documents only — never a whole collection.

    Scoped to `synthetic: true` so running --wipe against a dev database that
    also holds hand-made test data leaves that data alone.
    """
    removed = 0
    for name in SEEDED_COLLECTIONS:
        result = await db[name].delete_many({SYNTHETIC_FLAG: True})
        removed += result.deleted_count
    return removed


async def seed(db: MongoDb, now: dt.datetime | None = None) -> dict[str, int]:
    moment = now or dt.datetime.now(dt.UTC)
    counts: dict[str, int] = {name: 0 for name in SEEDED_COLLECTIONS}

    async def put(collection: str, document: dict[str, Any]) -> ObjectId:
        document[SYNTHETIC_FLAG] = True
        stamp(document, now=moment)
        result = await db[collection].replace_one(
            {"_id": document["_id"]}, document, upsert=True
        )
        counts[collection] += 1
        del result
        return document["_id"]

    for index, persona in enumerate(PERSONAS, start=1):
        user_id = ObjectId()
        await put(
            "users",
            {
                "_id": user_id,
                "firebase_uid": f"synthetic-{persona.handle}",
                "email": _email(persona),
                "phone": _phone(index),
                "locale": persona.locale,
                "script_pref": persona.script_pref,
                "timezone": persona.timezone,
                "status": "active",
            },
        )
        await put(
            "auth_identities",
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "provider": "phone",
                "provider_uid": f"synthetic-{persona.handle}",
                "verified_at": moment,
                "linked_at": moment,
            },
        )
        await put(
            "profiles",
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "persona": {"interest_level": "curious"},  # §10.8
                "priorities": list(persona.priorities),
                "honorific_prefs": {"register": "warm"},
                "name_pronunciation": {"override": None},
            },
        )
        await put(
            "birth_details",
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "family_member_id": None,
                "date": persona.birth_date,
                "time": persona.birth_time,
                "time_accuracy": persona.time_accuracy,
                "place": {
                    "label": persona.place_label,
                    "lat": persona.place_lat,
                    "lon": persona.place_lon,
                },
                "tz_snapshot": {"tz": persona.timezone, "resolved_at": moment.isoformat()},
                "rectification_notes": None,
            },
        )
        for relation, name in persona.family:
            await put(
                "family_members",
                {
                    "_id": ObjectId(),
                    "owner_user_id": user_id,
                    "relation": relation,
                    "name": name,
                    "language_tag": persona.locale,
                    "has_birth_details": False,
                    "attested_at": None,
                },
            )
        # §5/§13: essential processing is always recorded; memory consent is
        # contextual and genuinely absent for the personas who withheld it.
        await put(
            "consents",
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "type": "essential",
                "granted_at": moment,
                "revoked_at": None,
                "surface": "onboarding",
            },
        )
        if persona.memory_consent:
            await put(
                "consents",
                {
                    "_id": ObjectId(),
                    "user_id": user_id,
                    "type": "memory",
                    "granted_at": moment,
                    "revoked_at": None,
                    "surface": "chip",
                },
            )
        await put(
            "conversations",
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "mode": "chat",
                "locale": persona.locale,
                "started_at": moment,
                "summary": None,
                "token_stats": {"prompt": 0, "completion": 0},
            },
        )
        await put(
            "goals",
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "text": f"seed goal for {persona.handle}",
                "status": "open",
                "review_at": moment + dt.timedelta(days=30),
            },
        )
        await put(
            "subscriptions",
            {
                "_id": ObjectId(),
                "user_id": user_id,
                "plan": persona.plan,
                "region": persona.region,
                "provider": "razorpay" if persona.region == "IN" else "stripe",
                "status": persona.subscription_status,
                "provider_sub_id": f"synthetic_sub_{persona.handle}",
                "gift_links": [],
            },
        )

    return counts


async def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sitara_api.db.seed")
    parser.add_argument(
        "--wipe", action="store_true", help="remove existing synthetic documents first"
    )
    args = parser.parse_args(argv)

    settings = Settings()
    try:
        assert_safe(settings)
    except UnsafeSeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    client, db = make_mongo(settings)
    try:
        await ensure_schema(db)
        if args.wipe:
            print(f"wiped {await wipe(db)} synthetic documents")
        counts = await seed(db)
    finally:
        client.close()

    print(f"seeded {len(PERSONAS)} synthetic personas into {settings.mongo_db}")
    for name, count in counts.items():
        print(f"  {count:>3}  {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
