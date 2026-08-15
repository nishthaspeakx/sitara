"""§23.1's classes, §23.2's catalogue, §23.5's quiet hours, §32.6's exception.

Pure — no database, no Redis, no clock of its own. These are the rules a reader
of §23 would check the code against, one at a time.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.notifications import (
    CONTEXTUAL_TRIGGER_PRIORITY,
    DAILY_CAP,
    ContextualTrigger,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
)

from sitara_api.notifications import catalogue
from sitara_api.notifications.catalogue import (
    CATALOGUE,
    Candidate,
    DeclineReason,
    TriggerObservation,
    auto_paused,
    muhurat_is_near,
    reengagement_is_due,
    select,
)
from sitara_api.notifications.classes import CLASS_FOR_TRIGGER, policy, queue_order
from sitara_api.notifications.preferences import Preferences, default_matrix
from sitara_api.notifications.quiet_hours import (
    QuietHours,
    appointment_local_time,
    may_send,
    next_allowed_local_time,
    overlap_fingerprint,
)

# ---------------------------------------------------------------------------
# §23.1 — the class table
# ---------------------------------------------------------------------------


def test_only_class_t_bypasses_quiet_hours_and_the_cap() -> None:
    """§23.1 gives Class T both exemptions and gives them to nothing else."""
    for message_class in MessageClass:
        rules = policy(message_class)
        expected = message_class is MessageClass.TRANSACTIONAL
        assert rules.bypasses_quiet_hours is expected
        assert rules.bypasses_daily_cap is expected
        assert rules.suppressible is not expected


def test_class_t_may_never_carry_marketing() -> None:
    """§23.1: "no marketing content ever".

    The cell that matters most, because Class T is the one that bypasses quiet
    hours and the cap — so it is what a win-back would be routed through, and
    §22.13's dunning being legitimately Class T makes that a live temptation.
    """
    assert policy(MessageClass.TRANSACTIONAL).may_carry_marketing is False
    assert policy(MessageClass.MARKETING).may_carry_marketing is True


def test_the_unsubscribe_header_is_on_m_and_never_on_t() -> None:
    """§23.3: "List-Unsubscribe … on Class M, never on Class T"."""
    assert policy(MessageClass.MARKETING).unsubscribe_header is True
    assert policy(MessageClass.TRANSACTIONAL).unsubscribe_header is False


def test_queue_priority_is_t_then_d_then_c_then_m() -> None:
    """§23.7's ordering, with no ties — a tie would make the worker's order
    depend on dict iteration."""
    assert queue_order() == (
        MessageClass.TRANSACTIONAL,
        MessageClass.DAILY_LOOP,
        MessageClass.CONTEXTUAL,
        MessageClass.MARKETING,
    )


def test_only_marketing_carries_a_weekly_cap() -> None:
    """§23.1 hard-caps M at 2/week and caps nothing else per class."""
    capped = [c for c in MessageClass if policy(c).weekly_cap is not None]
    assert capped == [MessageClass.MARKETING]
    assert policy(MessageClass.MARKETING).weekly_cap == 2


# ---------------------------------------------------------------------------
# §23.2 — the catalogue
# ---------------------------------------------------------------------------


def test_the_catalogue_is_closed_at_six_in_the_spec_order() -> None:
    """§23.2: "Nothing else qualifies." """
    assert len(CATALOGUE) == 6
    assert tuple(CATALOGUE) == CONTEXTUAL_TRIGGER_PRIORITY
    assert [spec.priority for spec in CATALOGUE.values()] == [1, 2, 3, 4, 5, 6]


def test_a_user_reminder_is_class_t_and_does_not_spend_the_slot() -> None:
    """§23.2(1): "always wins, and does NOT consume the contextual slot".

    The exemption is DERIVED from the class rather than listed beside it, so
    this asserts both halves — if a future edit made the reminder Class C, the
    slot behaviour would change with it rather than silently disagreeing.
    """
    spec = CATALOGUE[ContextualTrigger.USER_REMINDER]
    assert spec.message_class is MessageClass.TRANSACTIONAL
    assert spec.consumes_slot is False
    assert policy(spec.message_class).bypasses_quiet_hours is True

    others = [s for t, s in CATALOGUE.items() if t is not ContextualTrigger.USER_REMINDER]
    assert all(s.consumes_slot for s in others)
    assert all(s.message_class is MessageClass.CONTEXTUAL for s in others)


def test_three_reminders_and_a_festival_all_go_out() -> None:
    """The consequence §23.2 intends, stated as a day.

    Three Class-T reminders plus one Class-C greeting is FOUR messages and is
    not a cap breach: §23.1 exempts Class T from the 3/day cap, and §23.2(1)
    exempts the reminder from the 1/day contextual slot. A reading that made
    the reminders compete for the slot would deliver one of them.
    """
    selection = select(
        [
            Candidate(ContextualTrigger.USER_REMINDER, id="r1"),
            Candidate(ContextualTrigger.USER_REMINDER, id="r2"),
            Candidate(ContextualTrigger.USER_REMINDER, id="r3"),
            Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="rakhi"),
        ]
    )
    assert len(selection.admitted) == 4
    assert selection.slot_spent is True


def test_the_highest_priority_contextual_wins_and_the_rest_are_declined() -> None:
    """§23.2: "highest wins" — and the losers are RECORDED, not discarded.

    §23.8 reports the trigger mix, and a mix that only counted winners could
    not show that one trigger has been crowding out five others all month.
    """
    selection = select(
        [
            Candidate(ContextualTrigger.TRANSIT_CHANGE, id="t", relevance=0.99),
            Candidate(ContextualTrigger.MUHURAT_WINDOW, id="m"),
            Candidate(ContextualTrigger.REFLECTION_FOLLOWUP, id="f"),
        ]
    )
    assert [c.trigger for c in selection.admitted] == [ContextualTrigger.MUHURAT_WINDOW]
    assert {c.trigger for c, _ in selection.declined} == {
        ContextualTrigger.TRANSIT_CHANGE,
        ContextualTrigger.REFLECTION_FOLLOWUP,
    }
    assert all(reason is DeclineReason.SLOT_TAKEN for _, reason in selection.declined)


def test_a_high_relevance_transit_cannot_outrank_the_catalogue() -> None:
    """§23.2 orders by TRIGGER, not by the ranking engine's score.

    Ordering by relevance would quietly replace §23.2's priority list with
    whatever the transit ranker happened to emit that morning — and the
    festival someone's mother-in-law asked about would lose to a routine
    aspect with a high number attached.
    """
    selection = select(
        [
            Candidate(ContextualTrigger.TRANSIT_CHANGE, id="t", relevance=1.0),
            Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="rakhi", relevance=0.0),
        ]
    )
    assert selection.admitted[0].trigger is ContextualTrigger.FESTIVAL_OR_FAMILY


def test_engagement_only_breaks_a_tie_between_the_same_trigger() -> None:
    """§23.2: "tie-broken by user's engagement history".

    Priority is a total order over the six, so a tie can only be two candidates
    of the SAME trigger. Engagement is recorded per trigger, so it cannot
    separate those either — and the id is the honest last key, which is what
    makes a re-run deterministic instead of dependent on list order.
    """
    first = select(
        [
            Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="b-festival"),
            Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="a-festival"),
        ]
    )
    second = select(
        [
            Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="a-festival"),
            Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="b-festival"),
        ]
    )
    assert first.admitted[0].id == second.admitted[0].id == "a-festival"


def test_a_spent_slot_admits_reminders_and_nothing_else() -> None:
    """`slot_already_spent` is what makes the selector safe to call twice a
    day — the §7.1 wave and an on-open path both reach it."""
    selection = select(
        [
            Candidate(ContextualTrigger.MUHURAT_WINDOW, id="m"),
            Candidate(ContextualTrigger.USER_REMINDER, id="r"),
        ],
        slot_already_spent=True,
    )
    assert [c.trigger for c in selection.admitted] == [ContextualTrigger.USER_REMINDER]


def test_a_switched_off_category_declines_before_the_slot_is_spent() -> None:
    """§23.5's festival toggle must not consume the day's contextual slot.

    Declining AFTER awarding would let a switched-off festival greeting eat the
    slot and silence the muhurat reminder behind it — the user would have
    turned off festivals and lost everything else too.
    """
    selection = select(
        [
            Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="rakhi"),
            Candidate(ContextualTrigger.MUHURAT_WINDOW, id="m"),
        ],
        categories_off=frozenset({NotificationCategory.FESTIVAL}),
    )
    assert [c.trigger for c in selection.admitted] == [ContextualTrigger.MUHURAT_WINDOW]
    assert selection.declined[0][1] is DeclineReason.CATEGORY_OFF


def test_a_muhurat_reminder_is_only_near_before_the_window_opens() -> None:
    """§23.2(2): "approaching (≤2h)". Both ends matter — a reminder that lands
    after the window opens tells somebody they missed something."""
    now = dt.datetime(2026, 8, 15, 9, 0, tzinfo=dt.UTC)
    assert muhurat_is_near(now + dt.timedelta(hours=1), now) is True
    assert muhurat_is_near(now + dt.timedelta(hours=2), now) is True
    assert muhurat_is_near(now + dt.timedelta(hours=2, minutes=1), now) is False
    # Already open. Not "very near" — not eligible at all.
    assert muhurat_is_near(now - dt.timedelta(minutes=1), now) is False


def test_reengagement_needs_both_conditions() -> None:
    """§23.2(6): "3+ quiet days → ONE gentle check-in per week maximum".

    The weekly count is what stops "3+ quiet days" firing again on day four,
    day five and day six — which is the drumbeat §29.2 forbids and which the
    obvious reading produces.
    """
    assert reengagement_is_due(quiet_days=3, sent_in_last_week=0) is True
    assert reengagement_is_due(quiet_days=2, sent_in_last_week=0) is False
    assert reengagement_is_due(quiet_days=9, sent_in_last_week=1) is False


def test_autopause_is_strictly_below_fifteen_percent() -> None:
    """§23.2: "<15%". A trigger sitting exactly at the threshold is not paused,
    which `<=` would quietly change."""
    assert auto_paused([TriggerObservation(ContextualTrigger.TRANSIT_CHANGE, 100, 14)])
    assert not auto_paused(
        [TriggerObservation(ContextualTrigger.TRANSIT_CHANGE, 100, 15)]
    )


def test_a_trigger_that_sent_nothing_has_no_rate_and_is_not_paused() -> None:
    """Undefined, not zero — a ratio needs a denominator.

    It is also what makes the pause self-healing: a paused trigger sends
    nothing, so a fortnight later its window is empty and it resumes. §23.2
    pairs the pause with "and flagged" precisely because the pause is meant to
    buy a human time rather than to become permanent.
    """
    assert TriggerObservation(ContextualTrigger.MUHURAT_WINDOW, 0, 0).open_rate is None
    assert auto_paused([TriggerObservation(ContextualTrigger.MUHURAT_WINDOW, 0, 0)]) == (
        frozenset()
    )


def test_a_muhurat_ttl_expires_when_its_window_opens() -> None:
    """§23.4 names this case: "muhurat reminder expires when the window opens"."""
    opens = dt.datetime(2026, 8, 15, 6, 0, tzinfo=dt.UTC)
    expiry = catalogue.expires_at(
        Candidate(ContextualTrigger.MUHURAT_WINDOW, id="m", window_opens_at=opens),
        local_date="2026-08-15",
        timezone="Asia/Kolkata",
    )
    assert expiry == opens


def test_other_triggers_expire_at_the_end_of_the_local_day() -> None:
    """Each of the other four is a statement about TODAY, so it stops being
    true at midnight LOCAL — not at midnight UTC."""
    expiry = catalogue.expires_at(
        Candidate(ContextualTrigger.FESTIVAL_OR_FAMILY, id="rakhi"),
        local_date="2026-08-15",
        timezone="Asia/Kolkata",
    )
    # Midnight IST on the 16th is 18:30 UTC on the 15th.
    assert expiry == dt.datetime(2026, 8, 15, 18, 30, tzinfo=dt.UTC)


# ---------------------------------------------------------------------------
# §23.5 — quiet hours, and §32.6's one exception
# ---------------------------------------------------------------------------


def test_the_default_window_wraps_midnight() -> None:
    """22:30–07:00 is the COMPLEMENT of 07:00–22:30 in string order.

    The one-line version that forgets this is `start <= t < end`, which is
    False all night and True all day — i.e. exactly inverted, and quiet.
    """
    quiet = QuietHours()
    assert quiet.wraps_midnight is True
    assert quiet.covers("23:00") is True
    assert quiet.covers("02:00") is True
    assert quiet.covers("06:59") is True
    assert quiet.covers("12:00") is False


def test_the_window_is_closed_at_the_start_and_open_at_the_end() -> None:
    """22:30 IS quiet (she set the moment quiet begins); 07:00 is NOT (a brief
    at exactly the end of quiet hours needs no exemption)."""
    quiet = QuietHours()
    assert quiet.covers("22:30") is True
    assert quiet.covers("07:00") is False


def test_an_unpadded_time_is_refused_rather_than_compared() -> None:
    """The padding is load-bearing: "7:00" sorts after "22:30" and after
    "10:00", so an unpadded end inverts the window silently."""
    with pytest.raises(ValueError, match="zero-padded"):
        QuietHours(start="22:30", end="7:00")


def test_class_t_speaks_at_three_in_the_morning() -> None:
    """§23.1's unconditional exemption — which is why an OTP arrives at 3am,
    and that is correct for a code somebody is waiting on."""
    # No §23.5 category maps to Class T, so this asserts the CLASS rule
    # through `policy` rather than through `may_send`, which is exactly the
    # separation §23.5 makes: there is no toggle for a transactional message.
    assert policy(MessageClass.TRANSACTIONAL).bypasses_quiet_hours is True


def test_the_brief_goes_out_inside_quiet_hours_at_its_appointment() -> None:
    """§32.6: "brief_time wins over quiet hours for that single send"."""
    verdict = may_send(
        category=NotificationCategory.MORNING,
        local_time="06:30",
        quiet_hours=QuietHours(),
        brief_time="06:30",
    )
    assert verdict.allowed is True
    assert verdict.exempt is True


def test_the_night_nudge_does_not_inherit_the_brief_exemption() -> None:
    """The failure a Class-D flag would have caused, pinned.

    The night nudge is ALSO Class D and §23.4 expires it at 23:30 — one hour
    inside a default 22:30 quiet window. A class-level exemption would push it
    into exactly the hours somebody set to stop that.
    """
    verdict = may_send(
        category=NotificationCategory.NIGHT,
        local_time="23:30",
        quiet_hours=QuietHours(),
        brief_time="06:30",
    )
    assert verdict.allowed is False


def test_a_morning_push_at_any_other_hour_meets_quiet_hours() -> None:
    """§32.6's exemption is for "that single send" — the appointment.

    A late fallback, a manual fire from the control surface, a regenerate that
    slipped: none of them is the appointment she made, and the exemption
    narrows to the local time matching `brief_time` so there is no argument a
    caller could pass to widen it.
    """
    verdict = may_send(
        category=NotificationCategory.MORNING,
        local_time="02:00",
        quiet_hours=QuietHours(),
        brief_time="06:30",
    )
    assert verdict.allowed is False


def test_a_brief_outside_quiet_hours_is_allowed_without_the_exemption() -> None:
    """The ordinary case: allowed, and NOT flagged as exempt.

    Worth pinning because §23.8 and the demo both read `exempt` — a version
    that set it on every morning message would make §32.6 look like it fires
    for everybody rather than for the overlap it is about.
    """
    verdict = may_send(
        category=NotificationCategory.MORNING,
        local_time="07:30",
        quiet_hours=QuietHours(),
        brief_time="07:30",
    )
    assert verdict.allowed is True
    assert verdict.exempt is False


def test_the_exemption_follows_the_appointment_across_a_dst_gap() -> None:
    """The defect the §23.9 matrix found, pinned at the rule level.

    On 2026-03-08 in New York the clocks go forward and 02:30 never happens, so
    §7.1's `local_instant` schedules a 02:30 brief for 03:00. §32.6's exemption
    originally compared against the brief_time STRING, so the comparison failed,
    the brief was held by quiet hours and it expired at noon — once a year, in
    silence, for anyone whose brief time sits inside their quiet hours.

    `appointment_local_time` resolves the setting for the DATE, which is what
    §32.6 means by "that single send": the appointment is what §7.1 scheduled.
    """
    resolved = appointment_local_time("02:30", "2026-03-08", "America/New_York")
    assert resolved == "03:00"

    verdict = may_send(
        category=NotificationCategory.MORNING,
        local_time="03:00",
        quiet_hours=QuietHours(),
        brief_time=resolved,
    )
    assert verdict.allowed is True
    assert verdict.exempt is True

    # An ordinary day resolves to the setting itself — the other 363.
    assert appointment_local_time("02:30", "2026-08-17", "America/New_York") == "02:30"


def test_the_fall_back_repeat_resolves_to_the_first_occurrence() -> None:
    """The other DST case. 01:30 happens TWICE on 2026-11-01 in New York, and
    §7.1 takes fold=0 — so the brief is early-in-the-repeat rather than an hour
    late, and the exemption still recognises it."""
    resolved = appointment_local_time("01:30", "2026-11-01", "America/New_York")
    assert resolved == "01:30"
    assert (
        may_send(
            category=NotificationCategory.MORNING,
            local_time="01:30",
            quiet_hours=QuietHours(),
            brief_time=resolved,
        ).exempt
        is True
    )


def test_a_held_message_waits_for_the_window_to_lift() -> None:
    assert next_allowed_local_time(QuietHours(), "23:10") == "07:00"
    assert next_allowed_local_time(QuietHours(), "09:00") == "09:00"


def test_the_overlap_fingerprint_names_this_overlap_and_not_the_fact_of_one() -> None:
    """§32.6's "once" has to survive her later changing either setting.

    A boolean acknowledged in March is still set in June, when she has moved
    her quiet hours and created a NEW overlap she has never seen.
    """
    assert overlap_fingerprint(QuietHours(), "12:00") is None
    first = overlap_fingerprint(QuietHours(), "06:30")
    second = overlap_fingerprint(QuietHours(start="23:00", end="08:00"), "06:30")
    assert first is not None and second is not None
    assert first != second


def test_acknowledging_an_overlap_spends_exactly_that_one() -> None:
    preferences = Preferences(user_id="u", brief_time="06:30")
    assert preferences.overlap_to_flag() is not None

    acknowledged = preferences.acknowledging_overlap()
    assert acknowledged.overlap_to_flag() is None

    # She moves her quiet hours later, creating a different overlap.
    moved = acknowledged.with_quiet_hours(QuietHours(start="21:00", end="07:00"))
    assert moved.overlap_to_flag() is not None


# ---------------------------------------------------------------------------
# §23.5 — the matrix, the pause, the travel toggle
# ---------------------------------------------------------------------------


def test_marketing_defaults_off_everywhere_and_everything_else_on() -> None:
    """§23.1: M has "separate legal consent (default OFF)"."""
    matrix = default_matrix()
    assert len(matrix) == 5 * 3
    for (category, _channel), enabled in matrix.items():
        assert enabled is (category is not NotificationCategory.MARKETING)


def test_a_missing_pair_reads_as_off() -> None:
    """Fails toward NOT sending — the direction §33.1's unreadable-preference
    rule and `MinuteLedger`'s smallest-pool rule both fail in."""
    preferences = Preferences(user_id="u", matrix={})
    assert preferences.allows(NotificationCategory.MORNING, NotificationChannel.PUSH) is (
        False
    )


def test_channels_for_returns_schema_order_not_document_order() -> None:
    """Two users with identical settings must get the same ladder — a dict
    built from a Mongo document carries whatever order it was stored in."""
    preferences = Preferences(user_id="u")
    assert preferences.channels_for(NotificationCategory.MORNING) == (
        NotificationChannel.PUSH,
        NotificationChannel.WHATSAPP,
        NotificationChannel.EMAIL,
    )


def test_the_pause_lasts_a_week_and_ends_early_on_request() -> None:
    """§23.5's one tap, and §29.2's "close always visible" applied to it."""
    now = dt.datetime(2026, 8, 15, 9, 0, tzinfo=dt.UTC)
    paused = Preferences(user_id="u").paused_for_a_week(now)
    assert paused.is_paused(now) is True
    assert paused.is_paused(now + dt.timedelta(days=6, hours=23)) is True
    assert paused.is_paused(now + dt.timedelta(days=7, seconds=1)) is False
    assert paused.resumed().is_paused(now) is False


def test_travel_mode_falls_back_to_home_when_no_zone_was_observed() -> None:
    """"follow my timezone" cannot follow a zone nobody has observed.

    Guessing UTC would put every unobserved user's brief AND quiet hours in the
    wrong city at once — and §23's every clock is local.
    """
    following = Preferences(user_id="u", home_timezone="Asia/Kolkata")
    assert following.effective_timezone("Europe/London") == "Europe/London"
    assert following.effective_timezone(None) == "Asia/Kolkata"

    keeping_home = Preferences(
        user_id="u", follow_timezone=False, home_timezone="Asia/Kolkata"
    )
    assert keeping_home.effective_timezone("Europe/London") == "Asia/Kolkata"


def test_the_daily_cap_constant_is_three() -> None:
    """§23.9 makes a cap breach release-blocking, so the number is pinned here
    as well as in the schema — a silent change to it would pass every other
    test in this file."""
    assert DAILY_CAP == 3


def test_every_trigger_names_a_class() -> None:
    """A trigger with no class is a trigger whose quiet-hours and cap behaviour
    is undefined."""
    assert set(CLASS_FOR_TRIGGER) == set(ContextualTrigger)
