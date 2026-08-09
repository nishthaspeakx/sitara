"""Watch the §7.1 morning happen — DEV ONLY (M6 acceptance harness).

The Today screen is M8's (§24/§28.2, a parallel frontend track), so this is the
stand-in that makes M6's acceptance runnable. It bypasses no logic: the real
Beat tick selector, the real ranking engine, the real astrology facade over
sitara-astro, the real §6.4 collections, the real grounding validator, the real
§23.4 notification row. Only the browser and the Celery broker are absent — the
tick is called directly rather than fired by Beat, so the run is watchable.

    cd services/api
    set -a; . ./.env; set +a               # ANTHROPIC_API_KEY (optional)
    uv run python scripts/brief.py --locale hi

What it does, in order:

    1. seeds a synthetic persona (§22.12: @example.invalid, +9199999, a real
       birth chart) and sets brief_time TWO MINUTES from now
    2. runs the real 15-minute tick and shows the wave it selected
    3. generates the brief and renders it with its fact citations VISIBLE —
       the markers a user never sees (§30.4), shown here because the point of
       the exercise is to check them
    4. fires the notification path locally and prints the §6.4 row
    5. moves the persona to London and shows §7.1's targeted regenerate
       producing a different brief for the same local date

Every user it creates is deleted on the way out unless --keep is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sitara_api.astrology import AstroChartAdapter, AstrologyFacade  # noqa: E402
from sitara_api.config import Settings  # noqa: E402
from sitara_api.daily_guidance.notify import (  # noqa: E402
    NotificationQueue,
    NotificationStatus,
)
from sitara_api.daily_guidance.polish import BriefPolisher  # noqa: E402
from sitara_api.daily_guidance.repository import SubjectRepository  # noqa: E402
from sitara_api.daily_guidance.service import DailyGuidanceService  # noqa: E402
from sitara_api.daily_guidance.store import BriefStore  # noqa: E402
from sitara_api.daily_guidance.triggers import RegenerationTriggers  # noqa: E402
from sitara_api.daily_guidance.types import Brief, Density  # noqa: E402
from sitara_api.daily_guidance.windows import (  # noqa: E402
    TICK_MINUTES,
    lead_minutes,
    select_wave,
)
from sitara_api.daily_guidance.wiring import CompositeBriefFacts, load_subject  # noqa: E402
from sitara_api.db import ensure_indexes, make_mongo  # noqa: E402
from sitara_api.db.documents import stamp  # noqa: E402
from sitara_api.panchang.adapter import AstroPanchangAdapter  # noqa: E402
from sitara_api.panchang.cache import PanchangCache  # noqa: E402
from sitara_api.panchang.places import default_resolver  # noqa: E402
from sitara_api.panchang.registry import build_registry  # noqa: E402
from sitara_api.panchang.service import PanchangService  # noqa: E402

DIM, BOLD, GOLD, GREEN, RED, RESET = (
    "\033[2m",
    "\033[1m",
    "\033[33m",
    "\033[32m",
    "\033[31m",
    "\033[0m",
)

#: §22.12: synthetic only. The seeder refuses a non-dev environment for the
#: same reason — a dev tool must never be able to create production PII.
SYNTHETIC_PHONE = "+919999900006"
#: Per-run so two harness runs cannot collide on §6.4's unique email index.
def synthetic_email(user_id: ObjectId) -> str:
    return f"brief-harness-{user_id}@example.invalid"

#: Borrowed verbatim from `db/seed.py` — one definition of "safe to write to".
ALLOWED_ENVIRONMENTS = frozenset({"dev", "test", "local"})
ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "mongo", "mongodb"})

CITIES = {
    "Mumbai": (19.076, 72.877, "Asia/Kolkata"),
    "London": (51.507, -0.128, "Europe/London"),
    "Delhi": (28.614, 77.209, "Asia/Kolkata"),
    "New York": (40.713, -74.006, "America/New_York"),
}


def _floor_to_tick(moment: dt.datetime) -> dt.datetime:
    """The Beat tick containing this instant. Beat fires on the grid, so a
    harness that invented an off-grid tick would be testing a schedule that
    never happens."""
    minute = (moment.minute // TICK_MINUTES) * TICK_MINUTES
    return moment.replace(minute=minute, second=0, microsecond=0)


def _ago(now: dt.datetime, then: dt.datetime) -> str:
    minutes = int((now - then).total_seconds() // 60)
    if minutes >= 0:
        return f"{minutes} min ago"
    return f"in {-minutes} min"


def rule(title: str) -> None:
    print(f"\n{BOLD}{'─' * 4} {title} {'─' * max(0, 66 - len(title))}{RESET}")


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def seed_persona(
    db, *, locale: str, city: str, density: Density, brief_time: str, tier_plan: str
) -> ObjectId:  # noqa: ANN001
    """One synthetic user with a COMPLETE birth chart (§22.12).

    A complete chart is the point: `personal_chart_theme`, `work` and
    `relationship` are gated on transit-house facts (§5.3), so a persona
    without a birth time would demonstrate the degrade path rather than the
    happy one — which is a different test, and `--no-birth-time` runs it.
    """
    lat, lon, tz = CITIES[city]
    user_id = ObjectId()

    await db.users.insert_one(
        stamp(
            {
                "_id": user_id,
                "firebase_uid": f"harness-{user_id}",
                "locale": locale,
                "script_pref": "auto",
                "timezone": tz,
                "status": "active",
                "email": synthetic_email(user_id),
                "phone": SYNTHETIC_PHONE,
                "deleted_at": None,
                "synthetic": True,
            }
        )
    )
    await db.profiles.insert_one(
        stamp(
            {
                "user_id": user_id,
                "persona": {"interest_level": density.value},
                "priorities": ["work", "family"],
                "honorific_prefs": {},
                "name_pronunciation": {},
                "brief_time": brief_time,
                "brief_place": {"lat": lat, "lon": lon, "tz": tz, "name": city},
                "density": density.value,
                "quiet_hours": {"start": "22:30", "end": "07:00"},
                "notification_prefs": {"morning": {"push": True}},
                "follow_timezone": True,
                "synthetic": True,
            }
        )
    )
    await db.subscriptions.insert_one(
        stamp(
            {
                "user_id": user_id,
                "plan": tier_plan,
                "region": "IN",
                "provider": "razorpay",
                "status": "active",
                "provider_sub_id": f"harness-{user_id}",
                "gift_links": [],
                "synthetic": True,
            }
        )
    )
    return user_id


async def seed_birth(db, user_id: ObjectId, *, city: str, with_time: bool) -> None:  # noqa: ANN001
    lat, lon, tz = CITIES[city]
    await db.birth_details.insert_one(
        stamp(
            {
                "user_id": user_id,
                "family_member_id": None,
                "date": "1992-03-14",
                # §5.3: no birth time means a MOON chart, not a guessed lagna.
                "time": "07:25" if with_time else None,
                "time_accuracy": "exact" if with_time else "unknown",
                "place": {"name": city, "lat": lat, "lon": lon, "tz": tz},
                "tz_snapshot": {"tz": tz, "utc_offset_seconds": 19800},
                "rectification_notes": None,
                "synthetic": True,
            }
        )
    )


async def cleanup(db, user_id: ObjectId) -> None:  # noqa: ANN001
    for name in (
        "users",
        "profiles",
        "subscriptions",
        "birth_details",
        "charts",
        "daily_briefings",
        "guidance_logs",
        "notifications",
    ):
        # `users` keys on _id (§33.2 — the Mongo _id IS the product identity);
        # `charts` on subject_id; everything else on user_id.
        key = {"users": "_id", "charts": "subject_id"}.get(name, "user_id")
        await db[name].delete_many({key: user_id})


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_brief(brief: Brief, *, show_citations: bool) -> None:
    status_colour = GREEN if brief.status.value in ("polished", "ranking_only") else RED
    print(
        f"  {DIM}status{RESET} {status_colour}{brief.status.value}{RESET}"
        f"   {DIM}confidence{RESET} {brief.confidence.value if brief.confidence else '—'}"
        f"   {DIM}density{RESET} {brief.density.value}"
        f"   {DIM}modules{RESET} {len(brief.modules)}/17"
    )
    if brief.degrade_reason:
        print(f"  {RED}degraded:{RESET} {brief.degrade_reason.value}")
    print(f"  {DIM}idempotency key{RESET} {brief.idempotency_key}")
    print()
    for module in brief.modules:
        label = module.module.value.replace("_", " ")
        polished = "polished" if module.polished_text else "template"
        print(f"  {GOLD}▸ {label}{RESET} {DIM}({polished}){RESET}")
        print(f"    {module.rendered}")
        if show_citations:
            # §30.4: a user NEVER sees these. This harness exists to check them.
            for fact_id in module.fact_ids:
                print(f"    {DIM}└─ {fact_id}{RESET}")
        print()


def render_notification(row) -> None:  # noqa: ANN001
    if row is None:
        print(f"  {DIM}no notification — §29.2 never pushes to report a failure{RESET}")
        return
    print(f"  {DIM}message_id  {RESET}{row.message_id}")
    print(f"  {DIM}collapse    {RESET}{row.collapse_key}")
    print(f"  {DIM}class       {RESET}{row.message_class.value} (daily-loop, §23.1)")
    print(f"  {DIM}scheduled   {RESET}{row.scheduled_at.isoformat()}")
    print(
        f"  {DIM}expires     {RESET}{row.expires_at.isoformat()}"
        f"  {DIM}(12:00 local, §23.4){RESET}"
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> int:  # noqa: PLR0915
    settings = Settings()
    # §22.12, both halves — the same guard `db/seed.py` uses, for the same
    # reason. `environment` DEFAULTS to "dev", so an env check alone would let
    # `MONGODB_URI=<production> uv run python scripts/brief.py` write synthetic
    # users into production: production data and dev data never share a host.
    if settings.environment not in ALLOWED_ENVIRONMENTS:
        print(f"{RED}refusing to run in environment {settings.environment!r} (§22.12){RESET}")
        return 1
    host = urlsplit(settings.mongodb_uri).hostname or ""
    if host not in ALLOWED_HOSTS:
        print(
            f"{RED}refusing to seed a non-local database (host {host!r}) — §22.12: "
            f"production data and dev data never share a host{RESET}"
        )
        return 1

    client, db = make_mongo(settings)
    await ensure_indexes(db)

    # Everything below the router, wired exactly as the Celery worker wires it.
    registry = build_registry(settings)
    panchang = PanchangService(
        cache=PanchangCache(db, panchang_ttl_days=settings.panchang_cache_ttl_days,
                            muhurat_ttl_days=settings.muhurat_cache_ttl_days),
        divineapi=registry.divineapi,
        prokerala=registry.prokerala,
        astro=AstroPanchangAdapter(settings.astro_base_url, settings.astro_timeout_seconds),
    )
    astrology = AstrologyFacade(
        db=db,
        adapter=AstroChartAdapter(settings.astro_base_url, settings.astro_timeout_seconds),
    )

    from sitara_api.chat_orchestration.config import ChatSettings

    chat_settings = ChatSettings()
    polisher = None
    if chat_settings.anthropic_api_key:
        from sitara_api.chat_orchestration.llm import build_llm

        polisher = BriefPolisher(build_llm(chat_settings), settings=chat_settings)

    store = BriefStore(db)
    queue = NotificationQueue(db)
    service = DailyGuidanceService(
        facts=CompositeBriefFacts(panchang, default_resolver(), astrology),
        store=store,
        queue=queue,
        polisher=polisher,
    )

    user_id: ObjectId | None = None
    try:
        # -- 1. the persona ------------------------------------------------
        rule("1 · synthetic persona (§22.12)")
        now = dt.datetime.now(dt.UTC)
        tz = CITIES[args.city][2]
        due_local = now.astimezone(ZoneInfo(tz)) + dt.timedelta(minutes=args.minutes_ahead)
        brief_time = due_local.strftime("%H:%M")

        user_id = await seed_persona(
            db,
            locale=args.locale,
            city=args.city,
            density=Density(args.density),
            brief_time=brief_time,
            tier_plan=args.plan,
        )
        await seed_birth(db, user_id, city=args.city, with_time=not args.no_birth_time)
        print(f"  user      {user_id}  {DIM}(synthetic, deleted on exit){RESET}")
        print(f"  locale    {args.locale}   density {args.density}   plan {args.plan}")
        print(f"  city      {args.city} ({tz})")
        print(
            f"  born      1992-03-14 {'07:25' if not args.no_birth_time else '(no time)'}"
            f"   {DIM}→ complete natal chart{RESET}"
            if not args.no_birth_time
            else "  born      1992-03-14 (no time on file)"
        )
        print(
            f"  brief_time {BOLD}{brief_time}{RESET} local "
            f"({args.minutes_ahead} min from now — inside the §7.1 lead window)"
        )

        # -- 2. the tick ---------------------------------------------------
        rule(f"2 · the real Beat tick ({TICK_MINUTES}-minute cadence, §7.1)")
        # §7.1 generates 90–30 minutes AHEAD of the brief, so the tick that
        # owns a brief due two minutes from now already ran — about an hour
        # ago. Rather than fudge the window or make you wait, the harness asks
        # the real selector for the instant Beat would have fired: the tick
        # containing `due − lead`, floored to the 15-minute grid. Everything
        # from here on is the production path with a production timestamp.
        lead = dt.timedelta(minutes=lead_minutes(str(user_id)))
        tick_at = _floor_to_tick(due_local.astimezone(dt.UTC) - lead)
        print(
            f"  brief due at {BOLD}{brief_time}{RESET} local, this user's hashed lead is "
            f"{int(lead.total_seconds() // 60)} min"
        )
        print(
            f"  → Beat's tick for them: {BOLD}"
            f"{tick_at.astimezone(ZoneInfo(tz)):%H:%M}{RESET} local "
            f"{DIM}({_ago(now, tick_at)}){RESET}"
        )

        subjects = await SubjectRepository(db).candidates(tick_at)
        mine = [s for s in subjects if s.user_id == str(user_id)]
        print(f"  candidates loaded from Mongo: {len(subjects)}  {DIM}(band-narrowed){RESET}")
        if not mine:
            print(f"  {RED}the persona was not selected — the band query missed them{RESET}")
            return 1

        members, report = select_wave(mine, tick_at)
        if not members:
            print(f"  {RED}the band loaded them but the window did not select them{RESET}")
            return 1

        member = members[0]
        print(f"  selected  {report.summary()}")
        print(
            f"  tier      {member.subject.tier.value}   "
            f"lead {member.slot_minutes} min  {DIM}(hashed, §7.1 smoothing){RESET}"
        )
        due_local_str = f"{member.due_at.astimezone(ZoneInfo(tz)):%H:%M %Z}"
        print(f"  local date {member.local_date}   due {due_local_str}")

        # -- 3. generation -------------------------------------------------
        rule("3 · facts → ranking → composition → polish → grounding")
        facts = await service._facts.fetch(member.subject, member.local_date)  # noqa: SLF001
        kinds: dict[str, int] = {}
        for snapshot in facts.snapshots:
            kinds[snapshot.kind.value] = kinds.get(snapshot.kind.value, 0) + 1
        print(f"  facts     {len(facts.snapshots)} snapshots")
        for kind, count in sorted(kinds.items()):
            print(f"    {DIM}{count:>3} × {kind}{RESET}")
        if facts.missing:
            print(f"  {RED}missing{RESET}   {', '.join(facts.missing)}")
        print(f"  polish    {'live model' if polisher else 'skipped — no ANTHROPIC_API_KEY'}")

        result = await service.generate_for(member, now=now)
        rule(f"4 · the brief, in {args.locale}")
        render_brief(result.brief, show_citations=not args.hide_citations)

        chart_modules = {"personal_chart_theme", "work", "relationship"}
        present = {m.module.value for m in result.brief.modules} & chart_modules
        if present:
            print(f"  {GREEN}chart-backed modules composed:{RESET} {', '.join(sorted(present))}")
        else:
            print(f"  {RED}no chart-backed module composed{RESET} "
                  f"{DIM}(expected when --no-birth-time){RESET}")

        # -- 5. the notification -------------------------------------------
        rule("5 · notification (§23.4 — enqueued, not sent)")
        render_notification(result.notification)
        queued = await db.notifications.count_documents(
            {"user_id": user_id, "status": NotificationStatus.QUEUED.value}
        )
        print(f"  {DIM}queued rows for this user: {queued}{RESET}")

        # -- 6. the targeted regenerate ------------------------------------
        rule(f"6 · §7.1 location change — {args.city} → London, overnight")
        lat, lon, london_tz = CITIES["London"]
        await db.users.update_one({"_id": user_id}, {"$set": {"timezone": london_tz}})
        await db.profiles.update_one(
            {"user_id": user_id},
            {"$set": {"brief_place": {"lat": lat, "lon": lon, "tz": london_tz, "name": "London"}}},
        )
        moved = await load_subject(db, str(user_id))
        assert moved is not None

        before = result.brief
        outcome = await RegenerationTriggers(
            service=service, store=store, queue=queue
        ).on_location_change(moved, previous_timezone=tz, now=now)
        print(f"  outcome   {BOLD}{outcome.outcome.value}{RESET}   local date {outcome.local_date}")

        after = await store.get(str(user_id), before.local_date)
        if after is not None:
            print(f"  {DIM}briefs stored for this user: "
                  f"{await db.daily_briefings.count_documents({'user_id': user_id})}"
                  f"  (§32.13 — one per local date){RESET}")
            rule("7 · the regenerated brief — recomputed for London")
            render_brief(after, show_citations=not args.hide_citations)
            changed = [
                m.module.value
                for m in after.modules
                if m.rendered
                not in {b.rendered for b in before.modules if b.module is m.module}
            ]
            print(
                f"  {GREEN}modules whose text changed with the city:{RESET} "
                f"{', '.join(changed) if changed else '(none)'}"
            )
        queued_after = await db.notifications.find(
            {"user_id": user_id, "status": NotificationStatus.QUEUED.value}
        ).to_list(None)
        superseded = await db.notifications.count_documents(
            {"user_id": user_id, "status": NotificationStatus.SUPERSEDED.value}
        )
        print(
            f"  {DIM}pushes: {len(queued_after)} queued, {superseded} superseded "
            f"(§23.4 — a regenerate REPLACES its push){RESET}"
        )
        return 0
    finally:
        if user_id is not None and not args.keep:
            await cleanup(db, user_id)
            print(f"\n{DIM}synthetic user removed.{RESET}")
        elif user_id is not None:
            print(f"\n{DIM}kept: {user_id}{RESET}")
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch the §7.1 morning happen (dev only)")
    parser.add_argument("--locale", default="en", choices=["en", "hi", "hi-Latn"])
    parser.add_argument("--city", default="Mumbai", choices=sorted(CITIES))
    parser.add_argument("--density", default="high", choices=[d.value for d in Density])
    parser.add_argument("--plan", default="annual", help="subscription plan → §7.1 tier")
    parser.add_argument(
        "--minutes-ahead", type=int, default=2, help="how far ahead to set brief_time"
    )
    parser.add_argument(
        "--no-birth-time",
        action="store_true",
        help="omit the birth time to watch the §5.3 decline and §7.1 degrade instead",
    )
    parser.add_argument("--hide-citations", action="store_true")
    parser.add_argument("--keep", action="store_true", help="do not delete the synthetic user")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
