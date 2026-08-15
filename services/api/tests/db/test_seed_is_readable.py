"""Everything the seeder WRITES, read back through the code that reads it.

── Why this file exists ───────────────────────────────────────────────────────

The root rule in `CLAUDE.md` says a fake that accepts what the real system
rejects is a defect in the fake. `db/seed.py` is a fake, and it had drifted from
three different readers at once — silently, for milestones, because it writes
documents DIRECTLY and nothing ever read one back:

  · `plan: "premium"`, `region: "IN"` — M4's vocabulary. M11 introduced `PlanId`
    and `BillingRegion` a year later and never revisited the seeder, so
    `PlanId("premium")` raised and **`GET /v1/subscription` 500'd for every
    seeded persona**. S30, S31 and S34 were unreachable for the whole demo cast.
  · no `live` field at all — §6.4's second partial unique index, whose ONLY
    derivation is `lifecycle.is_live`. `find_live()` matched nothing, so a gift
    redeemed onto a seeded subscriber took the "no existing subscription" branch
    and tried to INSERT a second row. The `(user_id, status=active)` index caught
    it as a 500; without that index it would have been two rows granting access
    to one account.
  · `relation: "husband"` — not a member of `Relation`, so the demo-history
    seeder died partway through and the Journal stayed empty.

Every one of those is the same bug wearing different clothes, and none of them
is visible to a test that only asserts the seeder WROTE something. So this file
asserts the seeder wrote something the product can READ.

The tests are deliberately about the readers, not about the values: pinning
`plan == "annual"` would pass again the day someone renames the enum and
updates only the seeder.
"""

from __future__ import annotations

import pytest

from sitara_api.db.seed import PERSONAS, seed

pytestmark = pytest.mark.asyncio


class TestSubscriptionsAreReadable:
    """`PaymentStore` is the only reader of `subscriptions` (§30.3)."""

    async def test_every_seeded_subscription_hydrates(self, db) -> None:  # noqa: ANN001
        """`_hydrate` parses `plan`, `region` and `status` into their enums. It
        raised `ValueError: 'premium' is not a valid PlanId` on every row."""
        from sitara_api.payments.store import PaymentStore

        await seed(db)
        store = PaymentStore(db)
        async for user in db.users.find({}):
            stored = await store.find_latest(str(user["_id"]))
            assert stored is not None, user["email"]
            assert stored.state.plan is not None
            assert stored.state.region is not None

    async def test_every_access_granting_row_is_findable_as_live(self, db) -> None:  # noqa: ANN001
        """§6.4's `live` flag, and the reason gift redemption 500'd.

        `find_live` is what tells `redeem_gift` whether to EXTEND an existing
        subscription or START a new one. A row that grants access but is not
        `live` sends it down the wrong branch — and the branch it takes writes
        a second subscription for an account that already has one.
        """
        from sitara_api.payments import lifecycle
        from sitara_api.payments.store import PaymentStore

        await seed(db)
        store = PaymentStore(db)
        async for row in db.subscriptions.find({}):
            expected = lifecycle.is_live(row["status"])
            assert row.get("live") == expected, row["status"]
            if expected:
                assert await store.find_live(str(row["user_id"])) is not None

    async def test_no_seeded_row_names_an_unimplemented_rail(self, db) -> None:  # noqa: ANN001
        """§30.3: razorpay and stripe are DECLARED and raise on every method.
        A seeded row naming one is a row that lies about what happened."""
        from sitara_api.payments.providers.base import PaymentProviderName
        from sitara_api.payments.providers.routing import is_simulated

        await seed(db)
        async for row in db.subscriptions.find({}):
            # Parsed into the enum first, which is a second assertion for free:
            # a provider string the enum does not know raises here.
            assert is_simulated(PaymentProviderName(row["provider"])), row["provider"]


class TestFamilyMembersAreReadable:
    async def test_every_seeded_relation_is_a_member_of_the_enum(self, db) -> None:  # noqa: ANN001
        """`Relation` is a CLOSED set because §28.2's `family_reminder` reads it
        and it renders through i18n keys. `"husband"` is not in it, and the
        history seeder died on the row that carried it."""
        from sitara_api.family.models import FamilyMember

        await seed(db)
        async for doc in db.family_members.find({}):
            member = FamilyMember.from_doc(doc)
            assert member.relation is not None


class TestTheBriefPipelineCanRunForEveryPersona:
    """`load_subject` is the door into §7.1. A persona it cannot assemble is a
    persona with no morning at all."""

    async def test_every_persona_loads_as_a_subject(self, db) -> None:  # noqa: ANN001
        from sitara_api.daily_guidance import wiring

        await seed(db)
        async for user in db.users.find({}):
            subject = await wiring.load_subject(db, str(user["_id"]))
            assert subject is not None, user["email"]

    async def test_every_persona_has_a_place_to_compute_a_panchang_at(self, db) -> None:  # noqa: ANN001
        """The one that emptied the demo.

        `CompositeBriefFacts._panchang_facts` returns None the moment `lat` or
        `lon` is None, so a persona with no `brief_place` gets no tithi, no
        nakshatra, no sunrise, no Rahu Kaal and no timing window — and the brief
        still comes back `polished`, because §5.3 removes a claim rather than
        degrading a brief. Today rendered the two fact-free modules and nothing
        anywhere went red.
        """
        from sitara_api.daily_guidance import wiring

        await seed(db)
        async for user in db.users.find({}):
            subject = await wiring.load_subject(db, str(user["_id"]))
            assert subject is not None
            assert subject.lat is not None and subject.lon is not None, user["email"]

    async def test_the_brief_place_agrees_with_the_users_timezone(self, db) -> None:  # noqa: ANN001
        """§30.2: the place is never implied.

        A coordinate and a clock that disagree produce a brief where every
        number is computed correctly and the day belongs to somebody else —
        Delhi's Rahu Kaal rendered against a New York wall clock ran 23:37–01:16
        with a "favourable window" at 02:28. Nothing on that screen is wrong,
        and all of it is useless.

        Checked as a LONGITUDE-to-offset sanity bound rather than an exact
        lookup: the point is to catch a coordinate on the wrong continent, not
        to re-implement a timezone database.
        """
        import datetime as dt
        from zoneinfo import ZoneInfo

        await seed(db)
        async for persona in _personas_by_email(db):
            doc, user = persona
            place = doc["brief_place"]
            offset_hours = (
                dt.datetime(2026, 6, 15, 12, tzinfo=ZoneInfo(user["timezone"]))
                .utcoffset()
                .total_seconds()
                / 3600
            )
            # Solar time at this longitude, in hours from UTC.
            solar = place["lon"] / 15.0
            assert abs(solar - offset_hours) <= 3.0, (
                f"{user['email']}: brief_place {place['label']} sits at "
                f"{solar:+.1f}h solar but the account clock is {offset_hours:+.1f}h"
            )


async def _personas_by_email(db):  # noqa: ANN001, ANN202
    async for user in db.users.find({}):
        profile = await db.profiles.find_one({"user_id": user["_id"]})
        yield profile, user


class TestNamesAreSayable:
    async def test_every_persona_has_a_name_tara_can_say(self, db) -> None:  # noqa: ANN001
        """S12 synthesises the account's display name. Without one the screen
        renders its designed unavailable state — honest, and a poor demo of a
        feature that works."""
        from sitara_api.voice.preview import spoken_name

        await seed(db)
        async for profile in db.profiles.find({}):
            assert spoken_name(profile) is not None

    async def test_the_names_are_in_each_personas_own_script(self) -> None:
        """§2.4: `hi` is Devanagari and `hi-Latn` IS Hinglish — Latin script.
        A Devanagari name on a Hinglish account is the §2.4 violation the
        locale exists to prevent, arriving through the fixture."""
        devanagari = range(0x0900, 0x097F)
        for persona in PERSONAS:
            has_deva = any(ord(ch) in devanagari for ch in persona.display_name)
            assert has_deva == (persona.locale == "hi"), persona.handle
