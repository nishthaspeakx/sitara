"""Give a seeded persona a HISTORY — through the real services, only.

`db.seed` creates who a persona IS: the user, the profile, the birth details,
the family. It creates nothing that HAPPENED, so a freshly seeded account opens
the Journal on an empty timeline and the Vault on an empty list — §24.6's
designed empty states, correct and true, and useless for showing anyone what
the product does.

── Why this is not a fixture file ─────────────────────────────────────────────

Every artefact below is produced by the SAME code that produces it in
production. The briefs run §7.1's real pipeline — the fact stage, the ranking
engine, composition, the polish ladder — for past local dates. The reflections
go through `ReflectionService.save`. The memories go through
`MemoryService.accept_chip`, which is §32.4's only path into the collection and
refuses a type 7–9 memory whose wording was not re-confirmed. The saves go
through `JournalService.save`, which stores a pointer and has no field a
sentence could occupy (§44.2).

That is the difference between a demo and a mock-up: nothing here can show a
brief the ranking engine would not have produced, or a memory that skipped its
consent record, because there is no code path here that could make one. If the
pipeline degrades, the seeded history degrades with it and the Journal shows
what a degraded morning actually looks like — which is worth seeing.

── Containment ────────────────────────────────────────────────────────────────

Refuses a non-dev environment and a non-local host, by calling `db.seed`'s own
`assert_safe`. Writes only for personas `db.seed` created — a phone that is not
synthetic is not a persona and is refused, the same rule `auth/dev_verifier.py`
follows.

    uv run python -m scripts.seed_demo_history --days 6
    uv run python -m scripts.seed_demo_history --persona asha --days 10
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from typing import Any

from bson import ObjectId

from sitara_api.config import Settings
from sitara_api.daily_guidance.repository import density_from
from sitara_api.daily_guidance.types import BriefSubject, Tier, WaveMember
from sitara_api.daily_guidance.wiring import build_service as build_daily_guidance
from sitara_api.db import make_mongo
from sitara_api.db.documents import stamp
from sitara_api.db.seed import PERSONAS, UnsafeSeedError, assert_safe
from sitara_api.journal.models import ArtefactType
from sitara_api.memory.models import MemoryCandidate
from sitara_api.memory.taxonomy import MemoryType
from sitara_api.reflection.models import Prompt

#: What a person actually writes at night — short, ordinary, and hers. These are
#: the ONE thing here that is authored rather than computed, because a
#: reflection has no generator: it is the user's own words by definition.
REFLECTIONS: tuple[dict[Prompt, str], ...] = (
    {
        Prompt.GRATITUDE: "Amma called, out of nowhere, and stayed on for an hour.",
        Prompt.WEIGHT: "The lease conversation is still sitting where I left it.",
        Prompt.TOMORROW: "Say the thing about the lease before lunch.",
    },
    {
        Prompt.GRATITUDE: "Finished the report. Nobody noticed, which was fine.",
        Prompt.TOMORROW: "A walk before the day starts.",
    },
    {
        Prompt.GRATITUDE: "Rain all evening and nowhere I needed to be.",
        Prompt.WEIGHT: "Tired in a way sleep hasn't been fixing.",
    },
)

#: §32.4-typed, and each one is a thing a person would plausibly have agreed to
#: Tara remembering. Types 7–9 carry the re-confirmation §32.4 requires; the
#: service refuses them otherwise, which is the point of going through it.
MEMORIES: tuple[tuple[MemoryType, str, bool], ...] = (
    (MemoryType.DATE_ANNIVERSARY, "Sunita's birthday is 11 March", False),
    (MemoryType.PREFERENCE, "Prefers her brief at 6:30, before the house wakes", False),
    (MemoryType.SPIRITUAL_PRACTICE, "Fasts on Tuesdays", False),
    (MemoryType.PERSON, "Ira started at a new school this year", False),
    (MemoryType.GOAL_INTENTION, "Wants the lease settled before Diwali", False),
    # Type 7. §32.4 re-confirms the wording before it may be stored.
    (MemoryType.MOOD_PATTERN, "Evenings are heavier than mornings for her", True),
)


def _persona_user_ids(db: Any, handles: list[str]) -> Any:
    wanted = {p.handle for p in PERSONAS if not handles or p.handle in handles}
    return wanted


async def _subject_for(db: Any, user_id: ObjectId) -> BriefSubject | None:
    """The same shape the wave repository assembles, read from the same rows."""
    user = await db.users.find_one({"_id": user_id})
    profile = await db.profiles.find_one({"user_id": user_id})
    if user is None or profile is None:
        return None
    place = (profile.get("brief_place") or {}) if isinstance(profile, dict) else {}
    subscription = await db.subscriptions.find_one({"user_id": user_id})
    status = (subscription or {}).get("status", "none")
    tier = Tier.PAYING if status in {"active", "trialing", "grace"} else Tier.FREE
    return BriefSubject(
        user_id=str(user_id),
        locale=user.get("locale", "en"),
        timezone=profile.get("timezone") or "Asia/Kolkata",
        brief_time=profile.get("brief_time") or "07:00",
        density=density_from(profile.get("interest")),
        tier=tier,
        lat=place.get("lat"),
        lon=place.get("lon"),
    )


async def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.seed_demo_history")
    parser.add_argument("--days", type=int, default=6, help="how many past days of briefs")
    parser.add_argument(
        "--persona",
        action="append",
        default=[],
        help="handle to seed (repeatable); default is every seeded persona",
    )
    parser.add_argument(
        "--skip-polish",
        action="store_true",
        help="§7.1's cost lever — ranking-only briefs, no model calls",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    try:
        assert_safe(settings)
    except UnsafeSeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    client, db = make_mongo(settings)
    service, close = await build_daily_guidance(db, client)

    # Built here rather than imported from `app.py` so this script does not
    # need a running FastAPI app; the SERVICES are the same objects.
    from sitara_api.family.service import FamilyService
    from sitara_api.family.store import FamilyStore
    from sitara_api.journal.search import ExactTextSearch
    from sitara_api.journal.service import JournalService
    from sitara_api.journal.store import JournalStore
    from sitara_api.memory import MemorySettings, build_memory_service
    from sitara_api.reflection.service import ReflectionService

    memory = await build_memory_service(
        db=db, settings=MemorySettings(), environment=settings.environment
    )
    reflection = ReflectionService(db)
    family = FamilyService(store=FamilyStore(db), memory_service=memory)
    journal = JournalService(
        store=JournalStore(db), search=ExactTextSearch(db), memory_service=memory
    )

    wanted = _persona_user_ids(db, args.persona)
    counts = {"briefs": 0, "reflections": 0, "memories": 0, "family_charts": 0, "saves": 0}

    try:
        async for identity in db.auth_identities.find({"provider": "phone"}):
            uid = identity.get("provider_uid") or ""
            if not uid.startswith("synthetic-"):
                continue
            handle = uid[len("synthetic-") :]
            if handle not in wanted:
                continue
            user_id = identity["user_id"]
            subject = await _subject_for(db, user_id)
            if subject is None:
                continue

            today = dt.datetime.now(dt.UTC).date()

            # ── briefs: §7.1's real pipeline, one local date at a time ──────
            for back in range(1, args.days + 1):
                local_date = (today - dt.timedelta(days=back)).isoformat()
                if await db.daily_briefings.find_one(
                    {"user_id": user_id, "date": local_date}
                ):
                    continue
                member = WaveMember(
                    subject=subject,
                    local_date=local_date,
                    due_at=dt.datetime.now(dt.UTC),
                    start_at=dt.datetime.now(dt.UTC),
                    slot_minutes=0,
                )
                try:
                    await service.generate_for(member, skip_polish=args.skip_polish)
                    counts["briefs"] += 1
                except Exception as exc:  # noqa: BLE001 — a demo seed never aborts a run
                    print(f"  {handle} {local_date}: brief skipped ({exc})")

            # ── reflections: through the real service ───────────────────────
            for offset, entries in enumerate(REFLECTIONS, start=1):
                local_date = (today - dt.timedelta(days=offset)).isoformat()
                if await db.night_reflections.find_one(
                    {"user_id": user_id, "date": local_date}
                ):
                    continue
                await reflection.save(
                    user_id=user_id,
                    date=local_date,
                    locale=subject.locale,
                    entries=entries,
                )
                counts["reflections"] += 1

            # ── memories: §32.4's only path in ──────────────────────────────
            existing = await db.memories.count_documents({"user_id": user_id})
            if existing == 0:
                for mtype, content, reconfirm in MEMORIES:
                    await memory.accept_chip(
                        user_id=user_id,
                        candidate=MemoryCandidate(type=mtype, content=content),
                        wording_reconfirmed=reconfirm,
                    )
                    counts["memories"] += 1

            # ── one family member with a chart (§13's attestation included) ──
            #
            # `db.seed` writes family members with `has_birth_details: False`,
            # which is a truthful default and leaves S28 — the first product
            # surface that draws CC-007's kundli — with nothing to draw for
            # anybody. One member gets details so the chart is reachable.
            #
            # The ATTESTATION is not decoration. §13 makes holding someone
            # else's birth details conditional on the account-holder asserting
            # she may, and §32.15's deletion retains that record while
            # destroying the data. Seeding the details without it would create
            # the one state the product is not allowed to be in.
            member = await db.family_members.find_one(
                {"owner_user_id": user_id, "has_birth_details": False}
            )
            if member is not None:
                await db.birth_details.insert_one(
                    stamp(
                        {
                            "_id": ObjectId(),
                            "user_id": user_id,
                            "family_member_id": member["_id"],
                            # The shape `AstrologyFacade.set_birth_details`
                            # writes — `place.tz` included, because §5.2 forbids
                            # inferring a zone from anywhere but the stored
                            # place and the reader returns None without it.
                            "date": "1962-03-11",
                            "time": "05:40",
                            "time_accuracy": "exact",
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
                            "synthetic": True,
                        }
                    )
                )
                await family.attest_birth_details(
                    owner_user_id=user_id, member_id=member["_id"]
                )
                await db.family_members.update_one(
                    {"_id": member["_id"]},
                    {"$set": {"has_birth_details": True}},
                )
                counts["family_charts"] += 1

            # ── a saved brief: §44.2's pointer ──────────────────────────────
            newest = await db.daily_briefings.find_one(
                {"user_id": user_id}, sort=[("date", -1)]
            )
            if newest is not None:
                await journal.save(
                    user_id=user_id,
                    artefact_type=ArtefactType.BRIEF,
                    artefact_ref=newest["date"],
                )
                counts["saves"] += 1
    finally:
        await close()
        client.close()

    print("seeded demo history:")
    for name, count in counts.items():
        print(f"  {count:>3}  {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
