"""`GET /v1/dev/today` — §28.2's sixteen variants, from the real engine.

**Why this exists.** Sixteen variants × three densities × three locales × two
themes is not a thing anyone can eyeball by arranging for each state to occur.
Some of them cannot be arranged at all: you cannot make it be Diwali, or make
DivineAPI fail, or be four days into a trial.

**Why it is not a mock.** The tempting shortcut is a page of hand-written JSON,
and it is wrong in a specific way: the states a designer signs off on would be
states the product never serves. So this endpoint fixes only what cannot be
arranged — the FACTS and the account state (`dev_fixtures.py`) — and runs them
through the real ranking engine, the real composer, the real §7.1 degradation
ladder and the same `build_payload` the production route uses. What comes back
is what the engine emits.

**Why it is dev-only.** It is mounted by `app.py` only when
`settings.environment == "dev"`, the same rule `db.seed` follows: a convenience
that can reach production data is not a convenience. It reads no user, writes
no row and touches no database — but "it happens to be harmless" is not the
property worth relying on.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from sitara_schemas import ErrorCode
from sitara_schemas.today import Density, Tier, TodayPayload

from sitara_api.daily_guidance import dev_fixtures
from sitara_api.daily_guidance.polish import BriefPolisher
from sitara_api.daily_guidance.router import build_payload
from sitara_api.daily_guidance.service import compose_brief
from sitara_api.daily_guidance.types import Brief, BriefSubject
from sitara_api.errors import ApiError
from sitara_api.localisation import resolve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/dev", tags=["today", "dev"])

#: §2.4's launch three. A locale outside them has no catalog, and §2.4 rule 7
#: forbids the English fallback that would otherwise paper over it.
LOCALES = ("en", "hi", "hi-Latn")


@router.get("/today")
async def dev_today(
    variant: Annotated[str, Query(description="One of §28.2's sixteen")] = "normal_morning",
    density: Annotated[Density, Query()] = Density.MED,
    locale: Annotated[str, Query()] = "en",
) -> TodayPayload:
    if variant not in dev_fixtures.VARIANTS:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.sys.validation")
    if locale not in LOCALES:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.sys.validation")

    facts, local_time, _, skip_polish = dev_fixtures.VARIANTS[variant]
    subject = BriefSubject(
        user_id=dev_fixtures.USER_ID,
        locale=locale,
        timezone=dev_fixtures.IST.tz,
        brief_time="07:00",
        density=density,
        tier=Tier.PAYING,
        lat=12.97,
        lon=77.59,
    )

    # The real ladder. `skip_polish` keeps the model out of it — the switcher
    # must render the same thing every time it is opened, and a polish pass is
    # the one stage that would not.
    composed = await compose_brief(
        facts,
        subject,
        polisher=_polisher_for(variant),
        skip_polish=skip_polish,
        inputs=_inputs_for(variant, locale),
    )

    brief = Brief(
        user_id=subject.user_id,
        local_date=dev_fixtures.LOCAL_DATE,
        locale=locale,
        density=density,
        tier=subject.tier,
        status=composed.status,
        modules=composed.modules,
        confidence=facts.confidence,
        degrade_reason=composed.degrade_reason,
    )

    state = dev_fixtures.state_for(variant, locale, brief)
    return build_payload(
        subject,
        # §7.1's FAILED outcome has no brief to show, and §28.2's first-session
        # variant is the screen for it. Passing None here is what the real route
        # passes when `BriefStore.get` misses.
        None if not composed.modules else brief,
        state,
        local_date=dev_fixtures.LOCAL_DATE,
        local_time=local_time,
    )


def _polisher_for(variant: str) -> BriefPolisher | None:
    """No model, except where the variant IS the model failing.

    Every other variant runs with `skip_polish=True`, because the switcher must
    render the same thing every time it is opened and a polish pass is the one
    stage that would not.
    """
    if variant != "provider_degraded":
        return None
    return BriefPolisher(dev_fixtures.UngroundedLLM())


def _inputs_for(variant: str, locale: str) -> dict[str, str]:
    """The three fact-free modules' non-fact material (§28.2's contextual row).

    Held here rather than in `dev_fixtures` because they are the user's own
    words, not facts: a stated priority, an open goal, a family occasion. The
    ranking engine gates all three on their presence, so a switcher without them
    would never show a priorities or goal-check card at all.

    **They are resolved IN-LOCALE**, and the first version was not: a literal
    `"work"` rendered "आपने कहा था कि अभी work सबसे ज़रूरी है" — an English word
    inside a Devanagari sentence, on the screen whose whole point is that the app
    is native (§2.4). A preview tool that manufactures the defect it exists to
    surface is worse than no preview tool.

    **Production passes no inputs at all.** Nothing in `scheduling` builds this
    dict, so `priorities`, `goal_check` and `family_reminder` are currently
    unreachable in a real brief — the ranking engine gates them on
    `available_inputs` and the set is always empty. That is an M6 wiring gap,
    not a Today one, and it is recorded in `docs/change-log.md` (CL-014) rather
    than papered over here.
    """
    if variant in {"first_session", "provider_degraded"}:
        return {}
    priority = resolve("start.priorities.option.career", locale)
    return {
        "priorities": priority,
        "goals": resolve("start.priorities.option.family", locale),
        "family_member": "Aai",
        "family_events": resolve("start.priorities.option.family", locale),
    }
