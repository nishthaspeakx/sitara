"""The Beat-driven tasks (§7.1, diagram 5; diagram 8's nightly consolidation).

Every task here is a thin shell: it opens a Mongo connection, builds the module
that does the work, awaits it and closes. The work itself lives in
`daily_guidance` and `memory`, where it is testable without a broker — which is
the reason there is almost nothing in this file worth reading twice.

The one rule that is not obvious: **a task must be safe to run twice.** §6.1
rejected a workflow engine on the strength of "Celery Beat + idempotent tasks",
and `task_acks_late` means a worker that dies mid-brief hands the message back.
The wave is idempotent because §32.13's unique index is; the pre-job is because
warming a warm cache is a no-op; consolidation is because it recomputes from
the embedding space rather than accumulating.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any

from sitara_api.daily_guidance.types import Tier
from sitara_api.scheduling.celery_app import (
    QUEUE_BRIEF_PAYING,
    QUEUE_BRIEF_TRIAL,
    QUEUE_MAINTENANCE,
    app,
)

logger = logging.getLogger(__name__)


def _run(coro):  # noqa: ANN001, ANN202
    """Bridge Celery's sync worker to the async service layer.

    A fresh event loop per task rather than a shared one: Motor binds its
    connection pool to the loop that created it, and reusing a loop across
    tasks in a prefork worker is how you get "attached to a different loop"
    at three in the morning.
    """
    return asyncio.run(coro)


async def _with_db(work):  # noqa: ANN001, ANN202
    from sitara_api.config import Settings
    from sitara_api.db import make_mongo

    settings = Settings()
    client, db = make_mongo(settings)
    try:
        return await work(db, settings, client)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# §7.1 — the 15-minute generation wave
# ---------------------------------------------------------------------------


@app.task(name="sitara.daily_guidance.wave_tick", queue=QUEUE_MAINTENANCE)
def wave_tick(tick_iso: str | None = None) -> dict[str, Any]:
    """One Beat tick: select the wave and fan it out (§7.1).

    The tick itself does no generation. It selects, reports, and enqueues one
    task per member on the member's own tier queue — so a slow brief delays one
    person's morning rather than the tail of the wave behind it, and §7.1's
    priority ordering is expressed by which queue the work lands on rather than
    by hoping the loop gets there in time.
    """

    def _tier_counts(subjects) -> dict[str, int]:  # noqa: ANN001
        from sitara_api.daily_guidance.repository import subjects_by_tier

        return {tier.value: count for tier, count in subjects_by_tier(subjects).items()}

    async def work(db, _settings, _client) -> dict[str, Any]:  # noqa: ANN001
        from sitara_api.daily_guidance.repository import SubjectRepository
        from sitara_api.daily_guidance.store import BriefStore
        from sitara_api.daily_guidance.windows import select_wave

        tick = (
            dt.datetime.fromisoformat(tick_iso)
            if tick_iso
            else dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
        )
        subjects = await SubjectRepository(db).candidates(tick)
        store = BriefStore(db)

        # The pre-filter needs the local dates the candidates could be due on;
        # deriving them from the members after selection would mean querying
        # after the decision it is meant to inform.
        members, report = select_wave(subjects, tick)
        dates = {member.local_date for member in members}
        if dates:
            generated = await store.generated_pairs(dates)
            members, report = select_wave(subjects, tick, already_generated=generated)

        for member in members:
            # §7.1's priority queues, expressed as WHICH queue the work lands
            # on rather than as an ordering the loop hopes to get through in
            # time: a slow brief then delays one person's morning instead of
            # the tail of the wave behind it.
            queue = (
                QUEUE_BRIEF_PAYING
                if member.subject.tier is Tier.PAYING
                else QUEUE_BRIEF_TRIAL
            )
            # `send_task` by name rather than `generate_brief.apply_async`: the
            # producer then needs none of the consumer's imports, which is what
            # lets the tick run on a worker that carries no model client and no
            # astrology adapter.
            app.send_task(
                "sitara.daily_guidance.generate_brief",
                kwargs={
                    "user_id": member.subject.user_id,
                    "local_date": member.local_date,
                    "due_at_iso": member.due_at.isoformat(),
                },
                queue=queue,
                # §23.4's spirit applied to the work itself: a generation task
                # that has not started by the time the brief was due has missed
                # its appointment, and running it late costs a Claude call to
                # produce something the user has already seen generated on open.
                expires=member.due_at,
            )

        logger.info(
            "wave tick",
            extra={"report": report.summary(), "tiers": _tier_counts(subjects)},
        )
        return {
            "tick": tick.isoformat(),
            "selected": report.selected,
            "dormant": report.skipped_dormant,
            "already": report.skipped_already_generated,
            "tiers": _tier_counts(subjects),
        }

    return _run(_with_db(work))


@app.task(
    name="sitara.daily_guidance.generate_brief",
    queue=QUEUE_BRIEF_PAYING,
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_jitter=True,
)
def generate_brief(self, user_id: str, local_date: str, due_at_iso: str) -> dict[str, Any]:  # noqa: ANN001
    """One user's brief (§7.1's per-user pipeline).

    §7.1: "Retries: 3× exponential; a failed brief degrades to 'verified core
    cards' … rather than nothing". Both, in that order: the retries are for
    transport failures, and the degrade is what the service does when the facts
    themselves are thin. A retry that keeps failing therefore ends in a real
    brief rather than in a dead letter, which is why the exception path below
    re-raises only after the service has had its chance to degrade.
    """

    async def work(db, _settings, client) -> dict[str, Any]:  # noqa: ANN001
        from sitara_api.daily_guidance.personal_inputs import load_inputs
        from sitara_api.daily_guidance.wiring import build_service, load_subject

        subject = await load_subject(db, user_id)
        if subject is None:
            logger.warning("brief skipped: no schedulable profile", extra={"user_id": user_id})
            return {"status": "skipped"}

        # §28.2's three fact-free contextual cards. Without this the ranking
        # engine's `available_inputs` set is empty and `priorities`,
        # `goal_check` and `family_reminder` are unreachable — three of §34.3's
        # seventeen, silently absent from every brief since M6.
        inputs = await load_inputs(db, subject, local_date=local_date)

        # The codec borrows the task's own client for the key vault rather than
        # opening a second one it would then have to remember to close.
        service, close = await build_service(db, client)
        try:
            result = await service.generate_on_open(
                subject,
                local_date,
                due_at=dt.datetime.fromisoformat(due_at_iso),
                inputs=inputs,
            )
        finally:
            await close()
        return {
            "status": result.brief.status.value,
            "modules": len(result.brief.modules),
            "notified": result.notification is not None,
            "inputs": sorted(inputs),
        }

    try:
        return _run(_with_db(work))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc) from exc


# ---------------------------------------------------------------------------
# §7.1 — the 00:30 local-region panchang pre-job
# ---------------------------------------------------------------------------


@app.task(name="sitara.daily_guidance.panchang_prejob", queue=QUEUE_MAINTENANCE)
def panchang_prejob(now_iso: str | None = None) -> dict[str, Any]:
    """Warm the shared panchang cells for zones that just passed 00:30 local."""

    async def work(db, _settings, _client) -> dict[str, Any]:  # noqa: ANN001
        from sitara_api.daily_guidance.panchang_prejob import (
            PanchangPrejob,
            cells_for,
            zones_crossing_prejob_hour,
        )
        from sitara_api.daily_guidance.repository import SubjectRepository
        from sitara_api.daily_guidance.wiring import build_panchang_service, subject_places

        now = dt.datetime.fromisoformat(now_iso) if now_iso else dt.datetime.now(dt.UTC)
        zones = await SubjectRepository(db).live_timezones()
        due = zones_crossing_prejob_hour(zones, now)
        if not due:
            return {"zones": 0, "cells": 0}

        service = build_panchang_service(db)
        if service is None:
            logger.info("panchang pre-job skipped: no provider configured")
            return {"zones": len(due), "cells": 0, "skipped": "no_provider"}

        warmed = 0
        for zone_name, local_date in due:
            places = await subject_places(db, zone_name)
            cells = cells_for(places, local_date)
            report = await PanchangPrejob(service).warm(cells)
            warmed += report.warmed
        return {"zones": len(due), "warmed": warmed}

    return _run(_with_db(work))


# ---------------------------------------------------------------------------
# Diagram 8 — nightly memory consolidation
# ---------------------------------------------------------------------------


@app.task(name="sitara.memory.consolidate", queue=QUEUE_MAINTENANCE)
def consolidate_memories(dry_run: bool = False) -> dict[str, Any]:
    """Decay, dedupe and theme extraction over the embedding space (§32.4).

    Decay shipped with M5-P6b; this task runs all three thirds of diagram 8's
    last box together, because they read the same collection and running them
    as three passes would triple the nightly scan for no benefit.
    """

    async def work(db, _settings, _client) -> dict[str, Any]:  # noqa: ANN001
        from sitara_api.memory.consolidation import run_consolidation

        report = await run_consolidation(db, dry_run=dry_run)
        logger.info("memory consolidation", extra={"report": report.summary()})
        return report.as_dict()

    return _run(_with_db(work))
