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
range of §10-6 birth-time accuracies, memory consent granted and withheld, and
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
from sitara_schemas.payments import BillingRegion, PlanId, SubscriptionStatus

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
    #: What Tara CALLS her, in her own script (§2.4, §6.4 `name_pronunciation`).
    #: Onboarding S10 collects this; a seeded persona skips S10, so without it
    #: every seeded account reaches S12 with no name to say and the voice
    #: preview correctly declines — a demo hitting a designed unavailable state
    #: for want of a fixture rather than for want of a feature.
    display_name: str
    locale: str
    script_pref: str
    timezone: str
    birth_date: str
    birth_time: str | None
    time_accuracy: str  # §10-6: exact | plus_minus_30 | day_part | unknown
    #: Where she was BORN — the chart's coordinate (§30.2).
    place_label: str
    place_lat: float
    place_lon: float
    #: Where she IS — onboarding S08, and the coordinate her morning panchang is
    #: COMPUTED at. Separate from the birth place because for half this cast
    #: they differ, which is the diaspora corridor the personas exist to cover.
    #:
    #: It must agree with `timezone`, and that is the whole reason it is its own
    #: field rather than reusing the birth place: seeding Delhi's coordinates
    #: against `America/New_York` produced a real brief with a Rahu Kaal running
    #: 23:37–01:16 and a "favourable window" at 02:28. Every number was computed
    #: correctly — for a longitude eight and a half hours away from the clock it
    #: was rendered against. §30.2's "the place is never implied" is exactly
    #: this failure: nothing on the screen is wrong, and the day is somebody
    #: else's.
    current_label: str
    current_lat: float
    current_lon: float
    priorities: tuple[str, ...]
    memory_consent: bool
    #: §30.3's own vocabulary, NOT free strings. These were `"premium"`/`"basic"`
    #: and `"IN"`/`"US"` when M4 wrote this file, which is a year before M11
    #: introduced `PlanId` and `BillingRegion` — and nothing failed, because the
    #: seeder writes documents directly and no test reads one back through
    #: `PaymentStore`. Every seeded persona's `GET /v1/subscription` therefore
    #: 500'd on `ValueError: 'premium' is not a valid PlanId`, which is the whole
    #: payments surface for the whole demo cast. Typing them as the enums is what
    #: makes that unrepresentable rather than merely fixed.
    plan: PlanId
    subscription_status: SubscriptionStatus
    region: BillingRegion
    family: tuple[tuple[str, str], ...] = ()  # (relation, name)


#: Fictitious throughout. Names are common given names used as placeholders, not
#: references to anyone; dates and times are invented.
PERSONAS: tuple[Persona, ...] = (
    Persona(
        handle="asha",
        display_name="आशा",
        locale="hi",
        script_pref="deva",
        timezone="Asia/Kolkata",
        birth_date="1988-03-14",
        birth_time="04:55",
        time_accuracy="exact",
        place_label="Jaipur",
        place_lat=26.9124,
        place_lon=75.7873,
        current_label="Jaipur",
        current_lat=26.9124,
        current_lon=75.7873,
        priorities=("family", "spiritual_growth", "health_adjacent"),
        memory_consent=True,
        plan=PlanId.ANNUAL,
        subscription_status=SubscriptionStatus.ACTIVE,
        region=BillingRegion.INDIA,
        family=(("mother", "Sunita"), ("daughter", "Ira")),
    ),
    Persona(
        handle="meera",
        display_name="Meera",
        locale="hi-Latn",
        script_pref="latn",
        timezone="Asia/Kolkata",
        birth_date="1993-11-02",
        birth_time="21:10",
        time_accuracy="plus_minus_30",
        place_label="Mumbai",
        place_lat=19.076,
        place_lon=72.8777,
        current_label="Mumbai",
        current_lat=19.076,
        current_lon=72.8777,
        priorities=("career", "relationships"),
        memory_consent=True,
        plan=PlanId.TRIAL,
        subscription_status=SubscriptionStatus.TRIALING,
        region=BillingRegion.INDIA,
        family=(("mother", "Shalini"), ("sister", "Priya")),
    ),
    Persona(
        handle="ritu",
        display_name="Ritu",
        locale="en",
        script_pref="latn",
        timezone="America/New_York",
        birth_date="1985-07-21",
        birth_time=None,
        time_accuracy="unknown",
        place_label="Delhi",
        place_lat=28.6139,
        place_lon=77.209,
        current_label="New York",
        current_lat=40.7128,
        current_lon=-74.006,
        priorities=("wealth", "career", "family"),
        memory_consent=False,  # §32.4: consent is per-chip and may be withheld
        plan=PlanId.ANNUAL,
        subscription_status=SubscriptionStatus.ACTIVE,
        region=BillingRegion.INTERNATIONAL,
        family=(("mother", "Kamala"), ("brother", "Vikram")),
    ),
    Persona(
        handle="kavita",
        display_name="Kavita",
        locale="en",
        script_pref="latn",
        timezone="Europe/London",
        birth_date="1979-01-09",
        birth_time="14:30",
        time_accuracy="day_part",
        place_label="Chennai",
        place_lat=13.0827,
        place_lon=80.2707,
        current_label="London",
        current_lat=51.5074,
        current_lon=-0.1278,
        priorities=("health_adjacent", "spiritual_growth"),
        memory_consent=True,
        plan=PlanId.TRIAL,
        subscription_status=SubscriptionStatus.TRIALING,
        region=BillingRegion.INTERNATIONAL,
        family=(("partner", "Arun"),),
    ),
    Persona(
        handle="divya",
        display_name="Divya",
        locale="hi-Latn",
        script_pref="latn",
        timezone="Asia/Dubai",
        birth_date="1996-05-30",
        birth_time="08:05",
        time_accuracy="exact",
        place_label="Ahmedabad",
        place_lat=23.0225,
        place_lon=72.5714,
        current_label="Dubai",
        current_lat=25.2048,
        current_lon=55.2708,
        priorities=("relationships", "career"),
        memory_consent=False,
        plan=PlanId.MONTHLY,
        subscription_status=SubscriptionStatus.CANCELLED,
        region=BillingRegion.INTERNATIONAL,
    ),
    Persona(
        handle="lata",
        display_name="लता",
        locale="hi",
        script_pref="deva",
        timezone="Asia/Kolkata",
        birth_date="1972-09-17",
        birth_time="23:45",
        time_accuracy="plus_minus_30",
        place_label="Lucknow",
        place_lat=26.8467,
        place_lon=80.9462,
        current_label="Lucknow",
        current_lat=26.8467,
        current_lon=80.9462,
        priorities=("family", "spiritual_growth"),
        memory_consent=True,
        plan=PlanId.MONTHLY,
        subscription_status=SubscriptionStatus.ACTIVE,
        region=BillingRegion.INDIA,
        family=(("daughter", "मीना"), ("son", "अरुण")),
    ),
)


def _subscription_document(
    persona: Persona, user_id: ObjectId, now: dt.datetime
) -> dict[str, Any]:
    """One §6.4 `subscriptions` row, in the shape `PaymentStore` reads back.

    Built from the payments module's own primitives rather than hand-written,
    because a hand-written one is what shipped: `plan: "premium"`,
    `region: "IN"`, `provider: "razorpay"`, and no `live`, `period_start`,
    `period_end`, `price_minor` or `currency` at all. Each of those is a
    separate failure and the first two are fatal —

      · `PlanId("premium")` raises, so `GET /v1/subscription` 500'd for EVERY
        seeded persona. S30, S31 and S34 were unreachable for the entire demo
        cast, and the payments section of the runbook walks all three.
      · `live` is §6.4's second partial unique index and `lifecycle.is_live` is
        its ONLY derivation. Absent, `find_live()` matched nothing, so a gift
        redeemed onto a seeded subscriber took the "no existing subscription"
        branch and INSERTED a second row — caught here only because the
        `(user_id, status=active)` index refused it with a 500. Without that
        index it would have been two rows granting access to one account, which
        is the exact failure `is_live`'s docstring describes.
      · `razorpay` is a DECLARED rail whose adapter raises on every method
        (§30.3). The only IMPLEMENTED arm is the simulator, and a seeded row
        naming a rail we cannot call is a row that lies about what happened.

    None of it failed a test because the seeder writes documents directly and
    nothing reads one back through `PaymentStore` — the root CLAUDE.md rule
    ("a fake that accepts what the real system rejects is a defect in the
    fake") pointed at a fixture rather than at an in-memory store.
    """
    from sitara_api.payments import lifecycle
    from sitara_api.payments.money import price_for
    from sitara_api.payments.providers.base import PaymentProviderName

    price = price_for(persona.region, persona.plan)
    # Period dates that make the row READABLE as a lived subscription: started
    # in the past, still running. §22.13's ladder is projected from these, so a
    # row with none of them renders a subscription with no renewal date.
    #
    # The offset is chosen per status rather than fixed, because `access_at`
    # COMPUTES from the clock rather than trusting the stored status: a flat
    # 30 days put a 7-day trial 23 days past its end, so the trial persona read
    # back `downgraded` and §28.2's trial variant was unreachable in the demo.
    # Day 5 of 7 also clears §28.2's "day-counter pill FROM DAY 4", so the pill
    # is visible — which is the thing that variant exists to show.
    days_in = 4 if persona.plan is PlanId.TRIAL else 30
    period_start = now - dt.timedelta(days=days_in)
    state = lifecycle.SubscriptionState(
        plan=persona.plan,
        region=persona.region,
        status=persona.subscription_status,
        period_start=period_start,
        period_end=period_start + dt.timedelta(days=price.term_days),
    )
    return {
        "_id": ObjectId(),
        "user_id": user_id,
        "plan": state.plan.value,
        "region": state.region.value,
        "status": state.status.value,
        # THE one derivation (§6.4's second partial unique index).
        "live": lifecycle.is_live(state.status),
        "period_start": state.period_start,
        "period_end": state.period_end,
        "price_minor": price.amount.minor,
        "currency": price.amount.currency.value,
        # §30.3: the simulator is the only implemented arm. Naming a declared
        # rail here would seed a row whose adapter raises on every method.
        "provider": PaymentProviderName.SIMULATOR.value,
        "provider_sub_id": f"synthetic_sub_{persona.handle}",
        "gift_links": [],
    }


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
                "persona": {"interest_level": "curious"},  # §10-8
                "priorities": list(persona.priorities),
                "honorific_prefs": {"register": "warm"},
                # `display_name` is what Tara CALLS her; `override` is §2.4-6's
                # phonetic respelling, which S12 writes and which reaches the
                # SYNTHESISER and nothing else (§3.4). Seeded empty so the demo
                # starts at "she says it as written" and the fix-pronunciation
                # loop has somewhere to go.
                "name_pronunciation": {
                    "display_name": persona.display_name,
                    "override": None,
                },
                # §30.2: "the place is never implied". This is the coordinate
                # the morning's panchang is COMPUTED at, and `load_subject`
                # reads `subject.lat`/`lon` from exactly here.
                #
                # It was absent, and the consequence was the whole astrology
                # surface: `CompositeBriefFacts._panchang_facts` returns None
                # the moment lat or lon is None, so no seeded persona ever got
                # a tithi, a nakshatra, a sunrise, a Rahu Kaal or a single
                # timing window. Today rendered the two FACT-FREE modules
                # (`priorities`, `goal_check`), `/today/timings` served its
                # designed empty state permanently, and the brief still came
                # back `polished` — because composing nothing from nothing is
                # not a failure, and §5.3 removes a claim rather than degrading
                # a brief when a fact is missing. Nothing was red.
                #
                # Onboarding S08 writes this for a real user; a seeded persona
                # skips S08.
                "brief_place": {
                    "label": persona.current_label,
                    "lat": persona.current_lat,
                    "lon": persona.current_lon,
                    "tz": persona.timezone,
                },
                # §23.5's picker default, zero-padded because §7.1's index does
                # a STRING range scan.
                "brief_time": "07:00",
                "density": "med",
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
                # The SAME shape `AstrologyFacade.set_birth_details` writes —
                # `name` and `tz` included. It used to write `label`/`lat`/`lon`
                # only, and `birth_input` requires `place["tz"]` (§5.2 forbids
                # inferring a zone from anywhere but the stored place), so it
                # logged "birth row incomplete" and returned None for every
                # seeded account. The visible effect was that no seeded user
                # could ever get a chart-grounded answer: chat declined every
                # astrology question for a missing birth date while the row sat
                # in Mongo, complete-looking, next to a `tz_snapshot` holding
                # the zone the reader never looks at.
                #
                # A seeder that writes what the real reader rejects is the same
                # defect class as a fake that accepts what the real system
                # rejects — and it hid here for the same reason, because
                # nothing read this row in a test.
                "place": {
                    "name": persona.place_label,
                    "label": persona.place_label,
                    "lat": persona.place_lat,
                    "lon": persona.place_lon,
                    "tz": persona.timezone,
                },
                "tz_snapshot": {
                    "tz": persona.timezone,
                    "resolved_at": moment.isoformat(),
                    "source": "gazetteer",
                },
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
        await put("subscriptions", _subscription_document(persona, user_id, moment))

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
