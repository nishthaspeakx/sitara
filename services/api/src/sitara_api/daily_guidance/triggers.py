"""Targeted regeneration (§7.1 location change, §32.7 locale change).

    §7.1: "late-arriving data (e.g. user flew to London overnight — location
    change event) triggers a targeted regenerate"

    §32.7: "Locale change joins location change as a targeted-regenerate
    trigger (§7.1): an undelivered brief in the old locale is discarded
    (idempotency key includes locale) and regenerated; if delivery is <10 min
    away, the notification waits for the regenerate (never delivers the wrong
    language — §2.4 rule upheld)."

Both events say the same thing in different words: the inputs a stored brief
was computed from are no longer the user's inputs. The response is the same
too — regenerate, and make sure the push that goes out is the new one — so this
module has one path with two entry points rather than two paths that must be
kept in step.

Three decisions worth stating, because each has a silent-failure twin:

* **A delivered brief is never regenerated.** Once the push has gone, replacing
  the brief behind it means the user taps a notification about their morning
  and finds a different morning. §32.7 says "undelivered" and means it; a
  delivered brief's correction is tomorrow's brief, or the user opening Today
  and seeing the travel banner §28.2 already specifies.

* **A location change only moves the brief if the user asked it to.** §23.5's
  preference centre has "follow my timezone (default, uses location events) vs
  keep home time", and §30.2's Travel Mode is the surface for it. A user who
  keeps home time gets recomputed TIMINGS for where they are without their
  07:00 moving to a new zone — which is the whole point of the setting.

* **Holding a notification is not cancelling it.** §32.7's under-ten-minutes
  rule holds the send until the regenerate lands. The row stays queued and is
  superseded by the new one; nothing is dropped, because a user who changed
  their language at 06:55 is still expecting their brief at 07:00.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from enum import StrEnum

from sitara_api.daily_guidance import notify
from sitara_api.daily_guidance.idempotency import briefing_key, local_date_for
from sitara_api.daily_guidance.service import DailyGuidanceService, GenerationResult
from sitara_api.daily_guidance.store import BriefStore
from sitara_api.daily_guidance.types import BriefStatus, BriefSubject
from sitara_api.daily_guidance.windows import local_instant, parse_brief_time

logger = logging.getLogger(__name__)


class RegenerateTrigger(StrEnum):
    LOCATION_CHANGE = "location_change"
    LOCALE_CHANGE = "locale_change"


class RegenerateOutcome(StrEnum):
    REGENERATED = "regenerated"
    HELD_AND_REGENERATED = "held_and_regenerated"
    NO_BRIEF = "no_brief"
    ALREADY_CURRENT = "already_current"
    ALREADY_DELIVERED = "already_delivered"
    NOT_FOLLOWING_TIMEZONE = "not_following_timezone"


@dataclass(frozen=True)
class RegenerateResult:
    outcome: RegenerateOutcome
    trigger: RegenerateTrigger
    local_date: str | None = None
    result: GenerationResult | None = None

    @property
    def regenerated(self) -> bool:
        return self.outcome in (
            RegenerateOutcome.REGENERATED,
            RegenerateOutcome.HELD_AND_REGENERATED,
        )


class RegenerationTriggers:
    """Both §7.1 regenerate triggers, over one implementation."""

    def __init__(
        self,
        *,
        service: DailyGuidanceService,
        store: BriefStore,
        queue: notify.NotificationQueue | None = None,
    ) -> None:
        self._service = service
        self._store = store
        self._queue = queue

    async def on_locale_change(
        self,
        subject: BriefSubject,
        *,
        now: dt.datetime | None = None,
        inputs: dict[str, str] | None = None,
    ) -> RegenerateResult:
        """§32.7. `subject.locale` is the NEW locale."""
        moment = now or dt.datetime.now(dt.UTC)
        local_date = local_date_for(moment, subject.timezone)
        stored = await self._store.get(subject.user_id, local_date)

        if stored is None:
            # Nothing to discard. The scheduled wave has not run yet and will
            # pick the new locale up on its own — regenerating now would just
            # do the work twice.
            return RegenerateResult(
                RegenerateOutcome.NO_BRIEF, RegenerateTrigger.LOCALE_CHANGE, local_date
            )
        if stored.idempotency_key == briefing_key(
            subject.user_id, local_date, subject.locale
        ):
            return RegenerateResult(
                RegenerateOutcome.ALREADY_CURRENT,
                RegenerateTrigger.LOCALE_CHANGE,
                local_date,
            )

        return await self._regenerate(
            subject,
            local_date,
            RegenerateTrigger.LOCALE_CHANGE,
            now=moment,
            inputs=inputs,
        )

    async def on_location_change(
        self,
        subject: BriefSubject,
        *,
        previous_timezone: str,
        now: dt.datetime | None = None,
        inputs: dict[str, str] | None = None,
    ) -> RegenerateResult:
        """§7.1's "user flew to London overnight". `subject` carries the NEW
        location; `previous_timezone` is where the stored brief was computed
        for, and is what decides which local date that brief belongs to."""
        moment = now or dt.datetime.now(dt.UTC)

        if not subject.follow_timezone:
            # §23.5 / §30.2: the user keeps home time. Their timings are
            # recomputed for where they are — that is the astrology facade's
            # job on the next read — but their brief does not move zones.
            return RegenerateResult(
                RegenerateOutcome.NOT_FOLLOWING_TIMEZONE,
                RegenerateTrigger.LOCATION_CHANGE,
            )

        # The stored brief is filed under the local date of the OLD zone. Look
        # there first: a passenger who landed in London still has a brief filed
        # under yesterday's Kolkata date, and looking only under the new zone's
        # date would find nothing and regenerate a second row.
        for timezone in _distinct(previous_timezone, subject.timezone):
            local_date = local_date_for(moment, timezone)
            stored = await self._store.get(subject.user_id, local_date)
            if stored is not None:
                if stored.opened_at is not None:
                    return RegenerateResult(
                        RegenerateOutcome.ALREADY_DELIVERED,
                        RegenerateTrigger.LOCATION_CHANGE,
                        local_date,
                    )
                return await self._regenerate(
                    subject,
                    local_date,
                    RegenerateTrigger.LOCATION_CHANGE,
                    now=moment,
                    inputs=inputs,
                )

        return RegenerateResult(
            RegenerateOutcome.NO_BRIEF,
            RegenerateTrigger.LOCATION_CHANGE,
            local_date_for(moment, subject.timezone),
        )

    # -- the shared path ----------------------------------------------------

    async def _regenerate(
        self,
        subject: BriefSubject,
        local_date: str,
        trigger: RegenerateTrigger,
        *,
        now: dt.datetime,
        inputs: dict[str, str] | None,
    ) -> RegenerateResult:
        stored = await self._store.get(subject.user_id, local_date)
        if stored is not None and stored.opened_at is not None:
            return RegenerateResult(
                RegenerateOutcome.ALREADY_DELIVERED, trigger, local_date
            )

        due_at = _due_at(subject, local_date)
        held = notify.should_hold_for_regenerate(due_at, now)
        if held:
            # §32.7's under-ten-minutes rule. Superseding BEFORE regenerating
            # is what makes the hold real: the queued push cannot go out in the
            # old language while the new brief is still being composed.
            if self._queue is not None:
                await self._queue.supersede(
                    subject.user_id,
                    notify.collapse_key_for(subject.user_id, local_date),
                )
            logger.info(
                "holding brief notification for regenerate (§32.7)",
                extra={"user_id": subject.user_id, "local_date": local_date},
            )

        result = await self._service.generate_on_open(
            subject, local_date, due_at=due_at, inputs=inputs, now=now
        )
        if result.brief.status is BriefStatus.FAILED:
            logger.warning(
                "targeted regenerate produced no brief",
                extra={"user_id": subject.user_id, "trigger": trigger.value},
            )
        return RegenerateResult(
            RegenerateOutcome.HELD_AND_REGENERATED if held else RegenerateOutcome.REGENERATED,
            trigger,
            local_date,
            result,
        )


def _due_at(subject: BriefSubject, local_date: str) -> dt.datetime:
    from zoneinfo import ZoneInfo

    hour, minute = parse_brief_time(subject.brief_time)
    return local_instant(
        dt.date.fromisoformat(local_date), hour, minute, ZoneInfo(subject.timezone)
    )


def _distinct(*values: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return tuple(seen)
