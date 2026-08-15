"""§23.5's preference centre, as a value (S41 `/you/settings/notifications`).

    "Per-category toggles (morning / night / contextual / festival / marketing)
     × per-channel (push / WhatsApp / email) matrix with honest copy — no 'are
     you sure' guilt modals; quiet hours (default 22:30–07:00 local,
     user-adjustable); brief time picker; one-tap 'pause everything for a week'
     (Class T exempt, stated plainly); travel behaviour toggle: 'follow my
     timezone' (default, uses location events) vs 'keep home time'. Changes
     apply within 60s."

This module is PURE — no database, no Redis, no clock of its own. Persistence
is `store.py` and the cache is `cache.py`, for `payments/lifecycle.py`'s reason:
the interesting failures here are a 5×3 grid, a window that wraps midnight and
a pause that has to exempt exactly one class, and all three are cheap to
reproduce and expensive to reason about through a database.

── The matrix is a 5×3 grid and the absences are the design ────────────────

**Class T has no row.** §23.5 lists five categories and none of them is
transactional. That is not an oversight to be helpfully corrected: an OTP is
not something to offer a toggle for, and a grid that offered one would let
somebody switch off the message that lets them sign in.

**Marketing defaults OFF on every channel** (§23.1: "separate legal consent
(default OFF)"), and everything else defaults ON. The marketing row IS the
consent record's surface rather than a second switch beside it — two controls
over one legal fact is how a consent ledger and a UI end up disagreeing.

**A toggle is not availability.** "morning × whatsapp" can be ON for someone
who has never opted into WhatsApp; the §23.3 ladder asks about opt-in and about
a live subscription separately. Collapsing the two would mean a user who
declines the push permission silently loses her preference, and gets it back
switched off if she ever grants it.

── The pause ───────────────────────────────────────────────────────────────

"one-tap 'pause everything for a week' (Class T exempt, stated plainly)". The
exemption is read from `classes.policy(...).suppressible` rather than written
here as a second list, so §23.1's "never suppressed" and §23.5's "Class T
exempt" are one cell. `paused_until` is an INSTANT and not a boolean-plus-date:
a boolean that a job has not yet cleared is a pause that outlives its week, and
§29.2's no-dark-patterns rule cuts in the direction of ending early rather than
late.

── The travel toggle ───────────────────────────────────────────────────────

"follow my timezone (default, uses location events) vs keep home time".

`effective_timezone` is the only place that decision is made, and it takes the
observed zone as an argument rather than reading one. §30.2's Travel Mode and
§7.1's brief scheduler both need the same answer, and a second implementation
of "which clock is this person on" is how a traveller's brief and her quiet
hours end up in different cities.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from sitara_schemas.notifications import (
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_CHANNELS,
    PAUSE_EVERYTHING_DAYS,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
)

from sitara_api.notifications.classes import CLASS_FOR_CATEGORY, policy
from sitara_api.notifications.quiet_hours import (
    QuietHours,
    overlap_fingerprint,
)

#: §7.1's default. Zero-padded local "HH:MM" — the padding is load-bearing,
#: because the §7.1 wave index does a STRING range scan over this field.
DEFAULT_BRIEF_TIME = "07:00"


def default_matrix() -> dict[tuple[NotificationCategory, NotificationChannel], bool]:
    """Every (category, channel) pair, with §23.1's marketing default.

    Built over the full product rather than listed, so a channel or a category
    added to the schema arrives in the grid with a declared default instead of
    being absent — and an absent pair reads as "off" to `allows`, which would
    silently switch off a category nobody meant to disable.
    """
    return {
        (category, channel): category is not NotificationCategory.MARKETING
        for category in NOTIFICATION_CATEGORIES
        for channel in NOTIFICATION_CHANNELS
    }


@dataclass(frozen=True)
class Preferences:
    """One user's §23.5 settings."""

    user_id: str
    matrix: Mapping[tuple[NotificationCategory, NotificationChannel], bool] = field(
        default_factory=default_matrix
    )
    quiet_hours: QuietHours = field(default_factory=QuietHours)
    brief_time: str = DEFAULT_BRIEF_TIME
    #: §23.5's pause. An instant, not a flag — see the module header.
    paused_until: dt.datetime | None = None
    #: §23.5's travel toggle. True = "follow my timezone" (the stated default).
    follow_timezone: bool = True
    #: Where "keep home time" means. Carried even when `follow_timezone` is
    #: True, because the toggle has to be reversible without asking her again.
    home_timezone: str = "Asia/Kolkata"
    #: §32.6's "flags the overlap once" — the fingerprint she acknowledged.
    quiet_overlap_acknowledged: str | None = None

    def allows(
        self, category: NotificationCategory, channel: NotificationChannel
    ) -> bool:
        """One cell of §23.5's grid.

        A missing pair is False and not True. The default matrix is complete,
        so a missing pair means a row read from a document written by an older
        schema — and failing toward NOT sending is the same direction §33.1's
        unreadable-preference rule and `MinuteLedger`'s smallest-pool rule
        both fail in.
        """
        return bool(self.matrix.get((category, channel), False))

    def channels_for(
        self, category: NotificationCategory
    ) -> tuple[NotificationChannel, ...]:
        """The channels this category is switched on for, in schema order.

        Order is the schema's rather than the matrix's: a dict built from a
        Mongo document carries whatever order it was stored in, and the §23.3
        ladder consults channels in a declared preference order. Two users with
        identical settings must get the same ladder.
        """
        return tuple(c for c in NOTIFICATION_CHANNELS if self.allows(category, c))

    def is_paused(self, now: dt.datetime) -> bool:
        """§23.5's week, computed from the instant rather than from a flag."""
        return self.paused_until is not None and now < self.paused_until

    def suppresses(
        self, category: NotificationCategory, *, now: dt.datetime
    ) -> bool:
        """Does the pause hold this category? Class T is exempt (§23.5, §23.1).

        The exemption is read from the class table, so "never suppressed" and
        "Class T exempt" are one cell in one file. Today no category maps to
        Class T — §23.5 offers no toggle for one — so this branch is unreachable
        through the preference centre and is still written, because the pause is
        also applied to sends that arrive by trigger rather than by category.
        """
        if not self.is_paused(now):
            return False
        return policy(CLASS_FOR_CATEGORY[category]).suppressible

    def effective_timezone(self, observed_timezone: str | None) -> str:
        """§23.5's travel toggle, and the ONE place it is decided.

        `observed_timezone` is what §30.2's location events last saw. None
        means we have not seen one — a browser that never reported, a user who
        declined location — and the honest answer there is home time regardless
        of the toggle, because "follow my timezone" cannot follow a zone nobody
        has observed. Guessing UTC instead would put every unobserved user's
        brief and quiet hours in the wrong city at once.
        """
        if self.follow_timezone and observed_timezone:
            return observed_timezone
        return self.home_timezone

    def overlap_to_flag(self) -> str | None:
        """§32.6's flag: the overlap she has NOT yet acknowledged, if any."""
        current = overlap_fingerprint(self.quiet_hours, self.brief_time)
        if current is None or current == self.quiet_overlap_acknowledged:
            return None
        return current

    # -- transitions ------------------------------------------------------
    #
    # Returned rather than mutated, so a caller cannot half-apply a change and
    # so the store writes one document from one value.

    def with_matrix(
        self,
        changes: Iterable[tuple[NotificationCategory, NotificationChannel, bool]],
    ) -> Preferences:
        matrix = dict(self.matrix)
        for category, channel, enabled in changes:
            matrix[(category, channel)] = enabled
        return replace(self, matrix=matrix)

    def with_quiet_hours(self, quiet_hours: QuietHours) -> Preferences:
        """§32.6's flag re-arms itself when the window moves.

        Clearing the acknowledgement on ANY change to either setting would
        re-flag an overlap she has already seen (moving quiet hours from
        22:30 to 22:00 with a 23:00 brief changes nothing she needs telling
        about). Clearing it never would leave a NEW overlap unannounced. So
        the acknowledgement is kept and `overlap_to_flag` compares
        fingerprints — the decision is made by what the settings now mean,
        not by the fact that they were touched.
        """
        return replace(self, quiet_hours=quiet_hours)

    def with_brief_time(self, brief_time: str) -> Preferences:
        return replace(self, brief_time=brief_time)

    def acknowledging_overlap(self) -> Preferences:
        """§32.6's "flags the overlap once" — this is the once being spent."""
        return replace(
            self,
            quiet_overlap_acknowledged=overlap_fingerprint(
                self.quiet_hours, self.brief_time
            ),
        )

    def paused_for_a_week(self, now: dt.datetime) -> Preferences:
        return replace(self, paused_until=now + dt.timedelta(days=PAUSE_EVERYTHING_DAYS))

    def resumed(self) -> Preferences:
        """§29.2: the close is always available. Un-pausing is one tap and it
        takes effect at once — there is no "are you sure", and no minimum."""
        return replace(self, paused_until=None)


assert MessageClass.TRANSACTIONAL not in set(CLASS_FOR_CATEGORY.values()), (
    "SPEC §23.5 offers five toggles and none of them is transactional. A "
    "category mapping to Class T would put a switch in the preference centre "
    "for the message that lets somebody sign in."
)
