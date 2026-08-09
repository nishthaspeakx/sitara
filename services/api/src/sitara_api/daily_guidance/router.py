"""`GET /v1/today` — the door M6 never had.

M6 built §7.1's pipeline end to end and stored `daily_briefings` rows that
nothing could read: there was no HTTP surface at all, so the engine generated
briefs no screen could reach. This is that surface, and it is deliberately thin
— every decision it makes is already made somewhere better:

* which brief         `BriefStore.get`, keyed on the user's LOCAL date (§32.13)
* what to do on a miss `DailyGuidanceService.generate_on_open` — §7.1's dormant
                       path and §32.13's missed-date path are one code path
* what the cards say   `templates.py`, from facts, before any model saw them
* how it renders       `presenter.py`
* which variant        the CLIENT (§32.1's precedence rule, one implementation)

The one thing it decides for itself is the local date, and that is the thing
§32.13 is most explicit about: never a UTC date. A user in Auckland asking for
"today" at 10:00 local is asking for a date the server's clock left behind
hours ago.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from sitara_schemas import ErrorCode
from sitara_schemas.today import BriefStatus, TodayPayload, TodayState, time_band

from sitara_api.auth.router import CurrentSession
from sitara_api.daily_guidance import presenter, today_state, wiring
from sitara_api.daily_guidance.store import BriefStore
from sitara_api.daily_guidance.templates import compose_taras_line
from sitara_api.daily_guidance.types import Brief, BriefSubject
from sitara_api.errors import ApiError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["today"])


def local_now(subject: BriefSubject, *, now: dt.datetime | None = None) -> dt.datetime:
    """The user's own wall clock.

    §30.2's Travel Mode decides WHICH clock: a user who turned travel mode off
    keeps home time, and their morning does not move because they flew. The
    subject already carries that decision as `follow_timezone`; `timezone` is
    the zone their brief is scheduled in either way, so this reads one field
    rather than re-deriving a rule §7.1 already applied.
    """
    moment = now or dt.datetime.now(dt.UTC)
    return moment.astimezone(ZoneInfo(subject.timezone))


@router.get("/today")
async def get_today(
    request: Request,
    session: CurrentSession,
    date: Annotated[str | None, Query(description="Local ISO date; defaults to today")] = None,
) -> TodayPayload:
    user_id, _ = session
    db = request.app.state.db

    subject = await wiring.load_subject(db, str(user_id))
    if subject is None:
        # No timezone or no locale. §2.4 forbids guessing a language and §5.3
        # forbids guessing a place, so there is no brief to compose and no
        # honest default to compose it with.
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.sys.validation")

    here = local_now(subject)
    local_date = date or here.date().isoformat()
    local_time = here.strftime("%H:%M")

    store = BriefStore(db)
    brief = await store.get(subject.user_id, local_date)

    if brief is None:
        brief = await _generate_on_open(request, subject, local_date, here)

    if brief is not None:
        await store.mark_opened(subject.user_id, local_date, dt.datetime.now(dt.UTC))

    state = await today_state.build_state(
        db,
        subject,
        brief or _empty_brief(subject, local_date),
        local_date=local_date,
        brief_count=await _brief_count(db, subject.user_id),
        stories_enabled=getattr(request.app.state.settings, "stories_enabled", False),
    )
    return build_payload(
        subject, brief, state, local_date=local_date, local_time=local_time
    )


async def _generate_on_open(
    request: Request,
    subject: BriefSubject,
    local_date: str,
    here: dt.datetime,
) -> Brief | None:
    """§7.1: "dormant users get on-open generation only — no waste".

    A failure here is NOT an error response. §28.2 has a variant for every way
    this can go wrong — degraded, offline, first-session — and all of them are
    screens. Returning a 503 would replace a designed state with an error page
    on the app's home surface, which is the one place that must always render
    something true.
    """
    service = getattr(request.app.state, "daily_guidance", None)
    if service is None:  # pragma: no cover — lifespan always sets it
        logger.warning("no daily-guidance service on app state")
        return None
    try:
        result = await service.generate_on_open(
            subject,
            local_date,
            due_at=here.replace(
                hour=int(subject.brief_time[:2]),
                minute=int(subject.brief_time[3:]),
                second=0,
                microsecond=0,
            ),
        )
        return result.brief
    except Exception:  # noqa: BLE001
        logger.exception(
            "on-open generation failed",
            extra={"user_id": subject.user_id, "local_date": local_date},
        )
        return None


def _empty_brief(subject: BriefSubject, local_date: str) -> Brief:
    """A brief-shaped nothing, for the morning there is no brief.

    §28.2's first-session variant and §7.1's FAILED outcome both land here, and
    both are screens with content on them. Carrying an empty `Brief` rather
    than a `None` through the state builder means one code path reads the
    account state instead of two.
    """
    return Brief(
        user_id=subject.user_id,
        local_date=local_date,
        locale=subject.locale,
        density=subject.density,
        tier=subject.tier,
        status=BriefStatus.PENDING,
    )


def build_payload(
    subject: BriefSubject,
    brief: Brief | None,
    state: TodayState,
    *,
    local_date: str,
    local_time: str,
) -> TodayPayload:
    """Assemble the wire payload. Pure, and shared with the dev router.

    Pure because the interesting decisions are here — which register Tara's
    line is in, whether there are modules at all — and none of them should need
    a database to test. Shared because the dev variant switcher renders real
    engine output through this exact function: if it had its own assembler, the
    states a designer signs off on would be states the product never serves.
    """
    band = time_band(local_time)
    source = brief or _empty_brief(subject, local_date)

    # Tara's line renders on every morning, including the ones with no facts —
    # §28.2 calls it "always present", and the claimless register exists for
    # exactly that (see `compose_taras_line`).
    line = compose_taras_line(source.snapshots, source.locale, band)

    return TodayPayload(
        local_date=source.local_date,
        local_time=local_time,
        timezone=subject.timezone,
        density=source.density,
        tier=source.tier,
        status=source.status,
        degrade_reason=source.degrade_reason,
        confidence=source.confidence,
        taras_line=presenter.present_taras_line(line),
        modules=tuple(
            presenter.present_module(module, source, source.locale)
            for module in source.modules
        ),
        panchang=presenter.present_panchang(source.snapshots, source.locale),
        state=state,
    )


async def _brief_count(db, user_id: str) -> int:  # noqa: ANN001
    """How many mornings this user has had.

    Capped, because the only two answers §28.2 distinguishes are "none" (first
    session) and "exactly one" (first morning). Counting a year of briefings to
    learn which of three buckets we are in would be a scan per page view.
    """
    from bson import ObjectId

    return await db.daily_briefings.count_documents(
        {"user_id": ObjectId(user_id)}, limit=2
    )
