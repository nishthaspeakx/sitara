"""§23.5's quiet hours, and §32.6's one exception to them.

    §23.5 — "quiet hours (default 22:30–07:00 local, user-adjustable)"
    §23.1 — "Class D … subject to quiet hours"; "Class C … earned"
    §23.1 — "Class T … bypasses quiet hours"
    §32.6 — "The scheduled morning brief is an explicit user appointment:
             brief_time wins over quiet hours for that single send. The
             settings UI flags the overlap once … and never silently
             suppresses. All other Class-D/C messages respect quiet hours
             absolutely."

── Why the exception is not a class cell ───────────────────────────────────

The obvious implementation of §32.6 is a flag on Class D. It is wrong, and
wrong in a way no test that only checks the brief would catch: **the night
nudge is also Class D.** A Class-D exemption would push it at 23:30 into a
22:30 quiet window, which is §23.4's night-nudge expiry landing an hour inside
the hours somebody set precisely to stop that.

The next implementation is a flag on the MORNING category, which is closer and
still wrong: §32.6's exemption is for "that single send" — the appointment the
user made. A morning-brief push being retried at 02:00 by a fallback ladder, or
fired by hand from a control surface, is not that appointment.

So the exemption is narrow by construction. `may_send` grants it only when the
category is `morning` AND the send's own local time IS the user's `brief_time`.
Anything else about a morning brief — a late fallback, a manual fire, a
regenerate that slipped — meets quiet hours like everything else. The
exemption cannot be widened by passing a different argument, because there is
no argument that widens it.

── The overlap flag ────────────────────────────────────────────────────────

§32.6: "The settings UI flags the overlap once ('your brief arrives inside your
quiet hours — that's fine, just checking') and never silently suppresses."

"Once" needs state, and the state is not a boolean. A boolean acknowledged in
March is still set in June, when she has moved her quiet hours and made a NEW
overlap she has never seen. `overlap_fingerprint` names the specific overlap;
the preference row remembers which fingerprint was acknowledged. So a
re-arranged overlap flags again and an unchanged one stays quiet — which is
what "once" means for a setting that can change underneath it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sitara_schemas.notifications import (
    QUIET_HOURS_DEFAULT_END,
    QUIET_HOURS_DEFAULT_START,
    MessageClass,
    NotificationCategory,
)

from sitara_api.notifications.classes import CLASS_FOR_CATEGORY, policy


@dataclass(frozen=True)
class QuietHours:
    """A local window, as zero-padded "HH:MM" strings.

    Strings and not `dt.time`, for `daily_guidance.windows`' own reason:
    §7.1's `brief_time` is a zero-padded local string because the index does a
    STRING range scan over it, and a window that had to be converted at every
    comparison against it would be a second representation of the same clock.
    The padding is load-bearing here too — unpadded "7:00" sorts after "22:30"
    and after "10:00", so an unpadded end would make the window wrap the wrong
    way round.
    """

    start: str = QUIET_HOURS_DEFAULT_START
    end: str = QUIET_HOURS_DEFAULT_END

    def __post_init__(self) -> None:
        for label, value in (("start", self.start), ("end", self.end)):
            if not _is_padded_local_time(value):
                raise ValueError(
                    f"quiet hours {label} must be zero-padded local HH:MM, got "
                    f"{value!r} — an unpadded time compares wrongly against a "
                    "padded one and silently inverts the window"
                )

    @property
    def wraps_midnight(self) -> bool:
        """True for every sane quiet-hours window, including the default.

        22:30–07:00 is not a range in string order; it is the COMPLEMENT of
        07:00–22:30. Every comparison below has to know which it is looking at,
        and the one-line version that forgets is `start <= t < end`, which is
        False all night and True all day.
        """
        return self.start > self.end

    def covers(self, local_time: str) -> bool:
        """Is this local "HH:MM" inside the window?

        Half-open at the end: 07:00 is NOT quiet when the window ends at 07:00,
        so a brief set for exactly the end of quiet hours needs no exemption.
        Closed at the start: 22:30 IS quiet when the window starts at 22:30,
        because the user set the moment quiet begins rather than the moment
        after it.
        """
        if not _is_padded_local_time(local_time):
            raise ValueError(f"local time must be zero-padded HH:MM, got {local_time!r}")
        if self.wraps_midnight:
            return local_time >= self.start or local_time < self.end
        return self.start <= local_time < self.end


@dataclass(frozen=True)
class Verdict:
    """Whether quiet hours permit this send, and — when they do not — why.

    The reason is carried rather than logged because §32.6's other half is
    "never silently suppresses": a Class-D message held by quiet hours is a
    thing the user should be able to see the reason for in the preference
    centre, and a bare False has nowhere to put it.
    """

    allowed: bool
    #: Set only when `allowed` is True DESPITE the local time being quiet.
    exempt: bool = False
    reason: str | None = None


#: §32.6's exemption applies to exactly one category. Not a set of categories
#: and not a class cell — see the module header for what each of those breaks.
_APPOINTMENT_CATEGORY = NotificationCategory.MORNING


def appointment_local_time(
    brief_time: str, local_date: str, timezone: str
) -> str:
    """The local "HH:MM" the brief is ACTUALLY scheduled for on this date.

    Equal to `brief_time` on 363 days a year, and the two days it is not are
    the reason this function exists. §7.1's `windows.local_instant` resolves a
    DST gap by advancing to the first wall clock that exists — so on a
    spring-forward morning a 02:30 brief is scheduled for 03:00, because 02:30
    never happens.

    **This was a real defect and the §23.9 matrix is what found it.** §32.6's
    exemption originally compared the send's local time against the `brief_time`
    STRING. On 2026-03-08 in New York the appointment had moved to 03:00, the
    string still said 02:30, the comparison failed — and the brief was held by
    quiet hours and then expired at noon. The user simply had no morning, once
    a year, silently, and only in the zones that observe DST with a brief time
    inside their quiet hours. No unit test would have shown it: every one of
    them passes a brief_time that exists.

    The exemption follows the APPOINTMENT, which is what §32.6 means by "that
    single send" — the appointment is what §7.1 scheduled, not what the string
    literally says.
    """
    from sitara_api.daily_guidance.windows import local_instant

    hour, minute = (int(part) for part in brief_time.split(":"))
    instant = local_instant(
        dt.date.fromisoformat(local_date), hour, minute, ZoneInfo(timezone)
    )
    return local_time_of(instant, timezone)


def may_send(
    *,
    category: NotificationCategory,
    local_time: str,
    quiet_hours: QuietHours,
    brief_time: str | None = None,
) -> Verdict:
    """§23.1 + §32.6, evaluated for one send at one local time.

    `brief_time` is the user's own appointment, RESOLVED for the date in
    question — pass `appointment_local_time(...)` rather than the raw setting
    where a DST day is possible. It is not "the time this message wants to go
    out": passing the send's own time here would make every send its own
    appointment and turn §32.6 into a blanket exemption, which is why the
    parameter is named for the setting rather than for the moment.
    """
    message_class = CLASS_FOR_CATEGORY[category]

    if policy(message_class).bypasses_quiet_hours:
        # §23.1's Class-T exemption. It is unconditional and it is the reason
        # an OTP arrives at 3am — which is the correct behaviour for a code
        # somebody is waiting on.
        return Verdict(allowed=True, exempt=False, reason=None)

    if not quiet_hours.covers(local_time):
        return Verdict(allowed=True)

    if (
        category is _APPOINTMENT_CATEGORY
        and brief_time is not None
        and local_time == brief_time
    ):
        # §32.6. The single send the user made an appointment for.
        return Verdict(allowed=True, exempt=True, reason="spec.32_6_brief_appointment")

    # §23.1's "All other Class-D/C messages respect quiet hours absolutely."
    return Verdict(allowed=False, reason="notifications.held_by_quiet_hours")


def next_allowed_local_time(quiet_hours: QuietHours, local_time: str) -> str:
    """When a held message may go, as a local "HH:MM".

    The end of the window, always — a held Class-D or Class-C message waits for
    quiet hours to lift rather than being dropped. §23.4's expiries are what
    stop that wait from becoming a stale delivery: a night nudge held at 23:00
    with a 23:30 expiry is dropped by the expiry sweep long before 07:00, and
    dropping it there is right, because §23.4 wants it gone rather than late.
    """
    return quiet_hours.end if quiet_hours.covers(local_time) else local_time


def overlaps(quiet_hours: QuietHours, brief_time: str) -> bool:
    """§32.6's "your brief arrives inside your quiet hours" condition."""
    return quiet_hours.covers(brief_time)


def overlap_fingerprint(quiet_hours: QuietHours, brief_time: str) -> str | None:
    """A name for THIS overlap, or None when there is not one.

    The preference row stores the fingerprint the user acknowledged, so
    §32.6's "once" survives her later changing either setting: a different
    window or a different brief time makes a different overlap, and she is told
    about it once too.
    """
    if not overlaps(quiet_hours, brief_time):
        return None
    return f"{quiet_hours.start}-{quiet_hours.end}@{brief_time}"


def local_time_of(instant: dt.datetime, timezone: str) -> str:
    """A UTC instant as the user's own zero-padded local "HH:MM".

    Every quiet-hours comparison in this module is against a LOCAL clock, and
    this is the only conversion. §7.1's `windows.local_instant` records what a
    naive datetime costs at a DST boundary; the mirror-image hazard here is
    cheaper and just as silent — comparing a UTC "HH:MM" against a local
    window puts a Mumbai user's quiet hours five and a half hours out.
    """
    return instant.astimezone(ZoneInfo(timezone)).strftime("%H:%M")


def _is_padded_local_time(value: str) -> bool:
    return (
        len(value) == 5
        and value[2] == ":"
        and value[:2].isdigit()
        and value[3:].isdigit()
        and int(value[:2]) < 24
        and int(value[3:]) < 60
    )


assert CLASS_FOR_CATEGORY[_APPOINTMENT_CATEGORY] is MessageClass.DAILY_LOOP, (
    "SPEC §32.6 exempts the morning brief, which is Class D. If the morning "
    "category were ever re-classed the exemption would stop being an exception "
    "and start being redundant — worth failing on rather than discovering when "
    "a night nudge inherits it."
)
