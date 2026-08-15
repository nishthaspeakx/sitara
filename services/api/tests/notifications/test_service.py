"""§23's send pipeline, against real Mongo and real Redis.

The gates are tested through `NotificationService.send` rather than in
isolation, because §23's interesting failures are ORDERING failures — a cap
counted before quiet hours, a ledger row written after delivery — and neither
is visible from inside one gate.

Both stores are real for the reason `tests/notifications/conftest.py` states:
§23.4's idempotency IS a unique index and §23.3's dedupe key IS `SET NX EX`.
Neither has anything to test in a dict.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.notifications import (
    ContextualTrigger,
    DeliveryFailure,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
    NotificationStatus,
)

from sitara_api.notifications.emergency_stop import EmergencyStop, Halt
from sitara_api.notifications.preferences import Preferences
from sitara_api.notifications.providers.base import (
    ChannelProviderName,
    ChannelUnavailable,
    PushSubscription,
)
from sitara_api.notifications.quiet_hours import QuietHours
from sitara_api.notifications.service import Blocked, SendRequest
from sitara_api.notifications.store import PreferenceStore, PushSubscriptionStore
from tests.notifications.conftest import IST, NOW, USER_ID, RecordingChannel

pytestmark = pytest.mark.asyncio


def _push(accept=True, failure=None) -> RecordingChannel:  # noqa: ANN001
    return RecordingChannel(
        NotificationChannel.PUSH,
        ChannelProviderName.WEB_PUSH_VAPID,
        accept=accept,
        failure=failure,
    )


def _email(accept=True, failure=None) -> RecordingChannel:  # noqa: ANN001
    return RecordingChannel(
        NotificationChannel.EMAIL, ChannelProviderName.SMTP, accept=accept, failure=failure
    )


def _request(**overrides) -> SendRequest:  # noqa: ANN003
    base = {
        "user_id": str(USER_ID),
        "category": NotificationCategory.MORNING,
        "locale": "en",
        "timezone": IST,
        "message_id": "m-1",
        "scheduled_at": NOW,
    }
    return SendRequest(**{**base, **overrides})


async def _subscribe(db, endpoint="https://push.invalid/a") -> None:  # noqa: ANN001
    await PushSubscriptionStore(db).upsert(
        user_id=str(USER_ID),
        subscription=PushSubscription(endpoint=endpoint, p256dh="p", auth="a"),
        user_agent="pytest",
        now=NOW,
    )


# ---------------------------------------------------------------------------
# The happy path, and the ledger
# ---------------------------------------------------------------------------


async def test_a_brief_goes_out_on_push_and_writes_one_ledger_row(db, make_service) -> None:  # noqa: ANN001
    await _subscribe(db)
    push, email = _push(), _email()
    service = make_service(
        {NotificationChannel.PUSH: push, NotificationChannel.EMAIL: email}
    )

    result = await service.send(_request(), now=NOW)

    assert result.sent is True
    assert result.channels == (NotificationChannel.PUSH,)
    # §23.3: "same message, NOT both".
    assert len(push.sent) == 1
    assert email.sent == []

    row = await db.notifications.find_one({"message_id": "m-1"})
    assert row["status"] == NotificationStatus.SENT.value
    assert row["channel"] == NotificationChannel.PUSH.value
    assert row["message_class"] == MessageClass.DAILY_LOOP.value
    assert row["category"] == NotificationCategory.MORNING.value
    assert row["sent_at"] is not None


async def test_the_ledger_row_is_written_before_delivery(db, make_service) -> None:  # noqa: ANN001
    """§23.4's ordering, asserted from inside the adapter.

    A row written AFTER a successful send does not exist if the process dies in
    between — and the retry then has no idempotency key to collide with and
    nothing stopping a second delivery. §23.9 makes that release-blocking, so
    the worst case must be a message that was sent and recorded as queued,
    never the reverse.
    """
    await _subscribe(db)
    seen: list[str | None] = []

    class Observing(RecordingChannel):
        async def send(self, delivery):  # noqa: ANN001, ANN201
            row = await db.notifications.find_one({"message_id": delivery.message_id})
            seen.append(row["status"] if row else None)
            return await super().send(delivery)

    service = make_service(
        {
            NotificationChannel.PUSH: Observing(
                NotificationChannel.PUSH, ChannelProviderName.WEB_PUSH_VAPID
            )
        }
    )
    await service.send(_request(), now=NOW)
    assert seen == [NotificationStatus.QUEUED.value]


# ---------------------------------------------------------------------------
# §23.3 — the ladder
# ---------------------------------------------------------------------------


async def test_a_failed_push_falls_back_to_email_and_not_both(db, make_service) -> None:  # noqa: ANN001
    """§23.3: "silent fallback to WhatsApp (if opted in) same message, NOT both".

    WhatsApp is DECLARED, so email is the next rung — which is the ladder
    working, not a degradation of it.
    """
    await _subscribe(db)
    push = _push(accept=False, failure=DeliveryFailure.SUBSCRIPTION_GONE)
    email = _email()
    service = make_service(
        {NotificationChannel.PUSH: push, NotificationChannel.EMAIL: email}
    )

    result = await service.send(_request(), now=NOW)

    assert result.sent is True
    assert result.channels == (NotificationChannel.EMAIL,)
    assert len(push.sent) == 1
    assert len(email.sent) == 1
    # The SAME message, not a second one.
    assert push.sent[0].message_id == email.sent[0].message_id


async def test_a_dead_push_subscription_is_retired_on_the_first_410(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.6: "a 410/404 … marks the subscription dead immediately"."""
    await _subscribe(db)
    service = make_service(
        {
            NotificationChannel.PUSH: _push(
                accept=False, failure=DeliveryFailure.SUBSCRIPTION_GONE
            ),
            NotificationChannel.EMAIL: _email(),
        }
    )
    await service.send(_request(), now=NOW)

    records = await PushSubscriptionStore(db).all_for(str(USER_ID))
    assert records[0].live is False
    assert records[0].dead_reason is DeliveryFailure.SUBSCRIPTION_GONE
    assert await PushSubscriptionStore(db).live_for(str(USER_ID)) == []


async def test_three_consecutive_timeouts_retire_a_subscription(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.6's other death. Consecutive — see the next test."""
    await _subscribe(db)
    service = make_service(
        {
            NotificationChannel.PUSH: _push(
                accept=False, failure=DeliveryFailure.TRANSIENT
            ),
            NotificationChannel.EMAIL: _email(),
        }
    )
    for index in range(3):
        await service.send(_request(message_id=f"m-{index}"), now=NOW)

    records = await PushSubscriptionStore(db).all_for(str(USER_ID))
    assert records[0].live is False
    assert records[0].consecutive_failures == 3


async def test_a_success_between_failures_resets_the_counter(
    db, make_service
) -> None:  # noqa: ANN001
    """"Consecutive" is the load-bearing word.

    A cumulative count would retire a subscription that has worked every
    morning for a year and failed three times across it.
    """
    await _subscribe(db)
    push = _push(accept=False, failure=DeliveryFailure.TRANSIENT)
    # Push ALONE, deliberately. With email wired the two failed sends would
    # fall through and succeed there, and three successes would then exhaust
    # §23.1's 3/day cap before the fourth send reached the ladder at all — so
    # the test would pass or fail on the cap rather than on the counter it is
    # about.
    service = make_service({NotificationChannel.PUSH: push})
    await service.send(_request(message_id="m-a"), now=NOW)
    await service.send(_request(message_id="m-b"), now=NOW)

    push.accept, push.failure = True, None
    await service.send(_request(message_id="m-c"), now=NOW)

    push.accept, push.failure = False, DeliveryFailure.TRANSIENT
    await service.send(_request(message_id="m-d"), now=NOW)

    records = await PushSubscriptionStore(db).all_for(str(USER_ID))
    assert records[0].live is True
    assert records[0].consecutive_failures == 1


async def test_a_channel_outage_is_transient_and_falls_through(
    db, make_service
) -> None:  # noqa: ANN001
    """`ChannelUnavailable` is caught per rung — the ladder is what it is for."""
    await _subscribe(db)

    class Down(RecordingChannel):
        async def send(self, delivery):  # noqa: ANN001, ANN201
            raise ChannelUnavailable("down")

    email = _email()
    service = make_service(
        {
            NotificationChannel.PUSH: Down(
                NotificationChannel.PUSH, ChannelProviderName.WEB_PUSH_VAPID
            ),
            NotificationChannel.EMAIL: email,
        }
    )
    result = await service.send(_request(), now=NOW)
    assert result.sent is True
    assert len(email.sent) == 1


async def test_a_transactional_message_fans_out_to_every_channel(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.3: "payment/security → all opted-in channels (deliberate redundancy)".

    The opposite rule to the daily loop's, in the same file, and the reason is
    that a payment failure which reached only a dead push subscription is a
    subscription cancelled in silence.
    """
    await _subscribe(db)
    push, email = _push(), _email()
    service = make_service(
        {NotificationChannel.PUSH: push, NotificationChannel.EMAIL: email}
    )
    result = await service.send(
        _request(
            category=NotificationCategory.CONTEXTUAL,
            trigger=ContextualTrigger.USER_REMINDER,
            params={"note": "the 3pm call"},
        ),
        now=NOW,
    )
    assert result.sent is True
    assert set(result.channels) == {NotificationChannel.PUSH, NotificationChannel.EMAIL}
    assert len(push.sent) == 1 and len(email.sent) == 1


async def test_an_unreachable_user_records_a_failed_row_rather_than_nothing(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.8's reporting is how "nobody in this cohort can be reached" becomes
    visible — and a message that was never written cannot appear in it."""
    await db.users.update_one({"_id": USER_ID}, {"$set": {"email": None}})
    service = make_service({NotificationChannel.EMAIL: _email()})

    result = await service.send(_request(), now=NOW)

    assert result.sent is False
    assert result.blocked is Blocked.UNREACHABLE
    row = await db.notifications.find_one({"message_id": "m-1"})
    assert row["status"] == NotificationStatus.FAILED.value


# ---------------------------------------------------------------------------
# §23.1 — the caps
# ---------------------------------------------------------------------------


async def test_five_contextual_sends_land_one_and_the_reminder_still_arrives(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.9's own acceptance case, with §23.1's Class-C cap applied.

    §23.9 writes "attempt 5 sends → exactly 3 + T-class delivered". Class C is
    additionally capped at 1/day (§23.1), so five CONTEXTUAL attempts land ONE
    — and the Class-T reminder, exempt from both caps, still arrives. Reading
    §23.9's "3" as three contextual messages would be reading the 3/day cap as
    if the 1/day one did not exist.
    """
    await _subscribe(db)
    service = make_service({NotificationChannel.PUSH: _push()})

    outcomes = [
        await service.send(
            _request(category=NotificationCategory.CONTEXTUAL, message_id=f"c-{i}"),
            now=NOW,
        )
        for i in range(5)
    ]
    assert sum(1 for o in outcomes if o.sent) == 1
    assert [o.blocked for o in outcomes[1:]] == [Blocked.CONTEXTUAL_SLOT_SPENT] * 4

    reminder = await service.send(
        _request(
            category=NotificationCategory.CONTEXTUAL,
            trigger=ContextualTrigger.USER_REMINDER,
            message_id="t-1",
            params={"note": "the 3pm call"},
        ),
        now=NOW,
    )
    assert reminder.sent is True


async def test_the_daily_cap_counts_the_users_own_day(db, make_service) -> None:  # noqa: ANN001
    """§23.1's "3/day" is a promise about HER day.

    A UTC window gives a Mumbai user two different caps depending on the hour.
    These four sends straddle 18:30 UTC, which is midnight IST — so the first
    three are one local day and the fourth is the next.
    """
    await _subscribe(db)
    service = make_service({NotificationChannel.PUSH: _push()})

    # 09:30, 12:30, 15:30 IST — all on 15 August local.
    before_midnight = [
        dt.datetime(2026, 8, 15, 4, 0, tzinfo=dt.UTC),
        dt.datetime(2026, 8, 15, 7, 0, tzinfo=dt.UTC),
        dt.datetime(2026, 8, 15, 10, 0, tzinfo=dt.UTC),
    ]
    for index, at in enumerate(before_midnight):
        result = await service.send(
            _request(
                category=NotificationCategory.MORNING,
                message_id=f"d-{index}",
                scheduled_at=at,
            ),
            now=at,
        )
        assert result.sent is True, index

    fourth = dt.datetime(2026, 8, 15, 13, 0, tzinfo=dt.UTC)  # 18:30 IST, same day
    capped = await service.send(
        _request(message_id="d-3", scheduled_at=fourth), now=fourth
    )
    assert capped.blocked is Blocked.CAP_REACHED

    # 08:00 IST on the 16th — a new local day, and the cap has reset. NOT
    # 00:30 IST, which is a new day and also inside the default quiet window:
    # the first version of this test used it and was refused by §23.5 while
    # appearing to be about §23.1.
    next_day = dt.datetime(2026, 8, 16, 2, 30, tzinfo=dt.UTC)
    fresh = await service.send(
        _request(message_id="d-4", scheduled_at=next_day), now=next_day
    )
    assert fresh.sent is True


async def test_marketing_is_capped_at_two_a_rolling_week(db, make_service) -> None:  # noqa: ANN001
    """§23.1: "hard-capped 2/week". Rolling, not calendar — a calendar reset
    lets four land inside 48 hours across a Sunday."""
    await _subscribe(db)
    store = PreferenceStore(db, None)
    await store.save(
        Preferences(user_id=str(USER_ID)).with_matrix(
            [(NotificationCategory.MARKETING, NotificationChannel.PUSH, True)]
        ),
        now=NOW,
    )
    service = make_service({NotificationChannel.PUSH: _push()})

    outcomes = [
        await service.send(
            _request(category=NotificationCategory.MARKETING, message_id=f"m-{i}"),
            now=NOW + dt.timedelta(days=i),
        )
        for i in range(3)
    ]
    assert [o.sent for o in outcomes] == [True, True, False]
    assert outcomes[2].blocked is Blocked.MARKETING_CAP_REACHED


async def test_marketing_is_off_until_she_turns_it_on(db, make_service) -> None:  # noqa: ANN001
    """§23.1: "separate legal consent (default OFF)"."""
    await _subscribe(db)
    service = make_service({NotificationChannel.PUSH: _push()})
    result = await service.send(
        _request(category=NotificationCategory.MARKETING), now=NOW
    )
    assert result.sent is False
    assert result.blocked is Blocked.NO_CONSENT


# ---------------------------------------------------------------------------
# §23.5 / §32.6 — quiet hours through the pipeline
# ---------------------------------------------------------------------------


async def test_a_held_message_does_not_spend_a_cap_slot(db, make_service) -> None:  # noqa: ANN001
    """The ordering bug that counting first would cause.

    Quiet hours run BEFORE the caps. Reversed, three held messages would
    exhaust a cap nothing ever used, and the user would receive nothing all day
    while the ledger said she had hit her limit.
    """
    await _subscribe(db)
    service = make_service({NotificationChannel.PUSH: _push()})
    # 23:00 IST — inside the default 22:30–07:00 window.
    quiet = dt.datetime(2026, 8, 15, 17, 30, tzinfo=dt.UTC)

    for index in range(3):
        held = await service.send(
            _request(
                category=NotificationCategory.NIGHT,
                message_id=f"n-{index}",
                scheduled_at=quiet,
            ),
            now=quiet,
        )
        assert held.blocked is Blocked.QUIET_HOURS

    # Nothing was written, so nothing was counted.
    assert await db.notifications.count_documents({}) == 0
    awake = dt.datetime(2026, 8, 16, 4, 0, tzinfo=dt.UTC)
    assert (
        await service.send(_request(message_id="n-ok", scheduled_at=awake), now=awake)
    ).sent is True


async def test_the_brief_goes_out_inside_quiet_hours_at_its_appointment(
    db, make_service
) -> None:  # noqa: ANN001
    """§32.6, end to end through the real pipeline.

    Her brief time is 06:30, which is inside the default quiet window. §32.6
    makes that one send an appointment and lets it through — and the result
    says so, which is what the demo points at.
    """
    await _subscribe(db)
    await PreferenceStore(db, None).save(
        Preferences(user_id=str(USER_ID), brief_time="06:30"), now=NOW
    )
    service = make_service({NotificationChannel.PUSH: _push()})

    at = dt.datetime(2026, 8, 15, 1, 0, tzinfo=dt.UTC)  # 06:30 IST
    result = await service.send(
        _request(message_id="brief-1", scheduled_at=at), now=at
    )

    assert result.sent is True
    assert result.quiet_hours_exempt is True


async def test_the_night_nudge_is_still_held_at_the_same_hour(
    db, make_service
) -> None:  # noqa: ANN001
    """The mirror of the test above, and the one a Class-D exemption breaks.

    Same user, same quiet hours, same clock — a different category. §32.6
    exempts the appointment, not the class.
    """
    await _subscribe(db)
    await PreferenceStore(db, None).save(
        Preferences(user_id=str(USER_ID), brief_time="06:30"), now=NOW
    )
    service = make_service({NotificationChannel.PUSH: _push()})

    at = dt.datetime(2026, 8, 15, 1, 0, tzinfo=dt.UTC)  # 06:30 IST
    result = await service.send(
        _request(
            category=NotificationCategory.NIGHT, message_id="night-1", scheduled_at=at
        ),
        now=at,
    )
    assert result.sent is False
    assert result.blocked is Blocked.QUIET_HOURS


async def test_a_pause_holds_everything_but_leaves_class_t_alone(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.5: "one-tap pause everything for a week (Class T exempt, stated
    plainly)"."""
    await _subscribe(db)
    await PreferenceStore(db, None).save(
        Preferences(user_id=str(USER_ID)).paused_for_a_week(NOW), now=NOW
    )
    service = make_service({NotificationChannel.PUSH: _push()})

    held = await service.send(_request(), now=NOW)
    assert held.blocked is Blocked.PAUSED

    reminder = await service.send(
        _request(
            category=NotificationCategory.CONTEXTUAL,
            trigger=ContextualTrigger.USER_REMINDER,
            message_id="t-during-pause",
            params={"note": "the 3pm call"},
        ),
        now=NOW,
    )
    assert reminder.sent is True


# ---------------------------------------------------------------------------
# §23.4 / §23.3 — idempotency and the dedupe key
# ---------------------------------------------------------------------------


async def test_the_same_message_id_twice_delivers_once(db, make_service) -> None:  # noqa: ANN001
    """§23.4's cross-process guard, which is the Redis claim rather than the
    unique index — the index stops a second ROW, the claim stops a second
    DELIVERY when the row already exists."""
    await _subscribe(db)
    push = _push()
    service = make_service({NotificationChannel.PUSH: push})

    first = await service.send(_request(), now=NOW)
    second = await service.send(_request(), now=NOW)

    assert first.sent is True
    assert second.sent is False
    assert second.blocked is Blocked.ALREADY_SENT
    assert len(push.sent) == 1
    assert await db.notifications.count_documents({"message_id": "m-1"}) == 1


async def test_a_message_that_reached_nobody_can_be_retried(db, make_service) -> None:  # noqa: ANN001
    """The claim exists to stop a SECOND delivery, not to stop a first one from
    ever happening — so a total failure gives the claim back."""
    await _subscribe(db)
    push = _push(accept=False, failure=DeliveryFailure.TRANSIENT)
    service = make_service({NotificationChannel.PUSH: push})

    assert (await service.send(_request(), now=NOW)).sent is False
    push.accept, push.failure = True, None
    retried = await service.send(_request(), now=NOW)
    assert retried.sent is True


async def test_an_expired_message_is_dropped_and_never_late_delivered(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.4: "undelivered → dropped, not late-delivered"."""
    await _subscribe(db)
    push = _push()
    service = make_service({NotificationChannel.PUSH: push})
    result = await service.send(
        _request(expires_at=NOW - dt.timedelta(minutes=1)), now=NOW
    )
    assert result.blocked is Blocked.EXPIRED
    assert push.sent == []


# ---------------------------------------------------------------------------
# §23.7 — the emergency stop
# ---------------------------------------------------------------------------


async def test_a_class_halt_stops_that_class_and_nothing_else(
    db, redis, make_service
) -> None:  # noqa: ANN001
    await _subscribe(db)
    service = make_service({NotificationChannel.PUSH: _push()})
    await EmergencyStop(redis).halt(Halt(message_class=MessageClass.DAILY_LOOP))

    halted = await service.send(_request(), now=NOW)
    assert halted.blocked is Blocked.HALTED
    assert halted.halt_token == "class:daily_loop"

    contextual = await service.send(
        _request(category=NotificationCategory.CONTEXTUAL, message_id="c-1"), now=NOW
    )
    assert contextual.sent is True


async def test_a_locale_halt_stops_one_language(db, redis, make_service) -> None:  # noqa: ANN001
    """§23.7's third axis — a broken interpolation in one locale must not stop
    the other two."""
    await _subscribe(db)
    service = make_service({NotificationChannel.PUSH: _push()})
    await EmergencyStop(redis).halt(Halt(locale="hi"))

    assert (await service.send(_request(locale="hi"), now=NOW)).blocked is Blocked.HALTED
    assert (await service.send(_request(message_id="m-2"), now=NOW)).sent is True


async def test_a_halt_naming_two_axes_is_refused() -> None:
    """They compose by OR. A halt naming two would be an AND, and an operator
    who halted "push" and "marketing" expecting both to stop would have stopped
    only the marketing pushes."""
    with pytest.raises(ValueError, match="exactly ONE axis"):
        Halt(message_class=MessageClass.MARKETING, channel=NotificationChannel.PUSH)


async def test_resuming_lets_messages_through_again(db, redis, make_service) -> None:  # noqa: ANN001
    await _subscribe(db)
    service = make_service({NotificationChannel.PUSH: _push()})
    stop = EmergencyStop(redis)
    await stop.halt(Halt(channel=NotificationChannel.PUSH))
    await stop.resume(Halt(channel=NotificationChannel.PUSH))
    assert (await service.send(_request(), now=NOW)).sent is True


# ---------------------------------------------------------------------------
# §23.5 — the preference store
# ---------------------------------------------------------------------------


async def test_a_user_with_no_row_gets_the_declared_defaults(db) -> None:  # noqa: ANN001
    """An empty matrix would read as "everything off" through `allows`, so a
    new account would silently receive nothing — and the first symptom would be
    a morning brief that never arrived for exactly the people who just signed
    up."""
    preferences = await PreferenceStore(db, None).load(str(USER_ID))
    assert preferences.allows(NotificationCategory.MORNING, NotificationChannel.PUSH)
    assert not preferences.allows(
        NotificationCategory.MARKETING, NotificationChannel.PUSH
    )
    assert preferences.quiet_hours == QuietHours()


async def test_preferences_round_trip_through_mongo(db) -> None:  # noqa: ANN001
    store = PreferenceStore(db, None)
    saved = (
        Preferences(user_id=str(USER_ID))
        .with_quiet_hours(QuietHours(start="21:00", end="08:00"))
        .with_brief_time("06:15")
        .with_matrix([(NotificationCategory.NIGHT, NotificationChannel.EMAIL, False)])
        .acknowledging_overlap()
    )
    await store.save(saved, now=NOW)

    loaded = await store.load(str(USER_ID))
    assert loaded.quiet_hours == QuietHours(start="21:00", end="08:00")
    assert loaded.brief_time == "06:15"
    assert not loaded.allows(NotificationCategory.NIGHT, NotificationChannel.EMAIL)
    assert loaded.overlap_to_flag() is None


async def test_a_stored_row_missing_a_pair_still_reads_its_default(db) -> None:  # noqa: ANN001
    """The overlay, not the replacement.

    A category added to the schema after this row was written must arrive with
    its declared default rather than absent — and an absent pair reads as
    "off", which would silently switch off a category nobody chose to disable,
    for exactly the users who have been here longest.
    """
    await db.notification_preferences.insert_one(
        {
            "user_id": USER_ID,
            "matrix": {"morning:push": False},
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )
    loaded = await PreferenceStore(db, None).load(str(USER_ID))
    assert loaded.allows(NotificationCategory.MORNING, NotificationChannel.PUSH) is False
    assert loaded.allows(NotificationCategory.NIGHT, NotificationChannel.PUSH) is True


async def test_a_saved_preference_invalidates_the_cache_within_the_promise(
    db, redis
) -> None:  # noqa: ANN001
    """§23.5: "Changes apply within 60s".

    Write-then-invalidate, in that order. The tidier-looking order —
    invalidate, then write — leaves a window in which a concurrent read
    repopulates the cache from the OLD document and holds it for the full
    sixty seconds.
    """
    store = PreferenceStore(db, redis)
    await store.load(str(USER_ID))  # populates the cache
    await store.save(
        Preferences(user_id=str(USER_ID)).with_brief_time("05:45"), now=NOW
    )
    assert (await store.load(str(USER_ID))).brief_time == "05:45"
