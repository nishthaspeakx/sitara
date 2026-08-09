"""The stores, against the REAL §6.4 validators.

Root CLAUDE.md records why this file is not an in-memory fake: "an in-memory
store took string ids where §6.4 requires objectId, so every real write failed
validation while the whole suite stayed green". Every write here goes through
the collection validators the migration builds.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.facts import ConfidenceState

from sitara_api.daily_guidance import notify
from sitara_api.daily_guidance.idempotency import briefing_key, is_stale, local_date_for
from sitara_api.daily_guidance.notify import NotificationQueue, NotificationStatus
from sitara_api.daily_guidance.ranking import RankingContext, rank
from sitara_api.daily_guidance.store import BriefStore
from sitara_api.daily_guidance.templates import BriefComposer
from sitara_api.daily_guidance.types import (
    Brief,
    BriefStatus,
    DegradeReason,
    Density,
    Tier,
)
from tests.daily_guidance.conftest import LOCAL_DATE, USER_ID

pytestmark = pytest.mark.asyncio()

NOW = dt.datetime(2026, 8, 12, 1, 30, tzinfo=dt.UTC)
DUE_AT = dt.datetime(2026, 8, 12, 1, 30, tzinfo=dt.UTC)  # 07:00 IST


def brief_for(
    facts,  # noqa: ANN001
    *,
    locale: str = "en",
    status: BriefStatus = BriefStatus.POLISHED,
    local_date: str = LOCAL_DATE,
    degrade: DegradeReason | None = None,
) -> Brief:
    modules = BriefComposer().compose_all(
        rank(facts, RankingContext(density=Density.MED)), locale
    )
    return Brief(
        user_id=USER_ID,
        local_date=local_date,
        locale=locale,
        density=Density.MED,
        tier=Tier.PAYING,
        status=status,
        modules=tuple(modules),
        confidence=ConfidenceState.VERIFIED,
        idempotency_key=briefing_key(USER_ID, local_date, locale),
        degrade_reason=degrade,
    )


# --- daily_briefings -------------------------------------------------------


async def test_a_brief_writes_through_the_real_validators(db, full_facts) -> None:  # noqa: ANN001
    stored = await BriefStore(db).upsert(brief_for(full_facts), now=NOW)
    doc = await db.daily_briefings.find_one({"date": LOCAL_DATE})

    assert doc is not None
    assert doc["idempotency_key"] == briefing_key(USER_ID, LOCAL_DATE, "en")
    assert doc["status"] == BriefStatus.POLISHED.value
    assert doc["modules"], "the modules are embedded, per §6.4"
    assert doc["fact_ids"], "the brief cites what it stands on"
    assert stored.generated_at == NOW


async def test_one_brief_per_user_local_date(db, full_facts) -> None:  # noqa: ANN001
    """§32.13: "one brief per user-local calendar date, bound at generation"."""
    store = BriefStore(db)
    await store.upsert(brief_for(full_facts), now=NOW)
    await store.upsert(brief_for(full_facts, status=BriefStatus.RANKING_ONLY), now=NOW)

    assert await db.daily_briefings.count_documents({"date": LOCAL_DATE}) == 1
    reread = await store.get(USER_ID, LOCAL_DATE)
    assert reread is not None
    assert reread.status is BriefStatus.RANKING_ONLY  # last writer wins


async def test_a_locale_change_replaces_rather_than_duplicates(db, full_facts) -> None:  # noqa: ANN001
    """§32.7 + §32.13 together: the key carries the locale, the INDEX does not.

    A user who switched language at 06:50 must end the morning holding one
    brief, in the new language — not two, one of which they cannot read.
    """
    store = BriefStore(db)
    await store.upsert(brief_for(full_facts, locale="en"), now=NOW)
    assert await store.stale_for_locale(USER_ID, LOCAL_DATE, "hi") is True

    await store.upsert(brief_for(full_facts, locale="hi"), now=NOW)
    assert await db.daily_briefings.count_documents({"date": LOCAL_DATE}) == 1
    reread = await store.get(USER_ID, LOCAL_DATE)
    assert reread is not None and reread.locale == "hi"
    assert await store.stale_for_locale(USER_ID, LOCAL_DATE, "hi") is False


async def test_created_at_survives_a_regenerate(db, full_facts) -> None:  # noqa: ANN001
    """Replacing a brief must not reset the age of the row it replaces."""
    store = BriefStore(db)
    await store.upsert(brief_for(full_facts), now=NOW)
    first = await db.daily_briefings.find_one({"date": LOCAL_DATE})

    later = NOW + dt.timedelta(minutes=20)
    await store.upsert(brief_for(full_facts, locale="hi"), now=later)
    second = await db.daily_briefings.find_one({"date": LOCAL_DATE})

    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] > first["updated_at"]


async def test_a_reread_brief_keeps_its_citations(db, full_facts) -> None:  # noqa: ANN001
    """The second bug the M6 harness caught.

    §6.4 stores `fact_ids` on the row and the full snapshots in `guidance_logs`
    (§34.2), so a brief read back has ids and no snapshots. Dropping them on
    read left a Trust Sheet opened on a stored brief with nothing to show —
    the citation surviving generation but not persistence.
    """
    store = BriefStore(db)
    written = await store.upsert(brief_for(full_facts), now=NOW)
    assert written.fact_ids, "the generated brief cites something"

    reread = await store.get(USER_ID, LOCAL_DATE)
    assert reread is not None
    assert reread.fact_ids == written.fact_ids
    for module in reread.modules:
        original = next(m for m in written.modules if m.module is module.module)
        assert module.fact_ids == original.fact_ids


async def test_generated_pairs_pre_filter(db, full_facts) -> None:  # noqa: ANN001
    store = BriefStore(db)
    await store.upsert(brief_for(full_facts), now=NOW)
    pairs = await store.generated_pairs({LOCAL_DATE, "2026-08-13"})
    assert (USER_ID, LOCAL_DATE) in pairs


async def test_mark_opened_is_idempotent(db, full_facts) -> None:  # noqa: ANN001
    """§7.1's TTS gate reads the trailing open rate off this; counting one open
    twice would let a user past the >20% threshold they never crossed."""
    store = BriefStore(db)
    await store.upsert(brief_for(full_facts), now=NOW)
    assert await store.mark_opened(USER_ID, LOCAL_DATE, NOW) is True
    assert await store.mark_opened(USER_ID, LOCAL_DATE, NOW) is False


# --- guidance_logs (§34.2) -------------------------------------------------


async def test_the_guidance_log_embeds_full_snapshots(db, full_facts) -> None:  # noqa: ANN001
    """§34.2: "every artefact that cites a fact EMBEDS ITS FULL SNAPSHOT at
    generation time". Old Trust Sheets read snapshots, never recomputations."""
    store = BriefStore(db)
    stored = await store.upsert(brief_for(full_facts), now=NOW)
    await store.write_guidance_log(stored, now=NOW)

    log = await db.guidance_logs.find_one({"date": LOCAL_DATE})
    assert log is not None
    assert log["fact_ids"] == list(stored.fact_ids)
    assert len(log["fact_snapshots"]) == len(stored.snapshots)
    # A snapshot, not a reference: value, precision, method and provenance.
    first = log["fact_snapshots"][0]
    assert {"fact_id", "kind", "value", "precision", "method", "source"} <= set(first)


async def test_a_degraded_brief_still_writes_its_log(db, full_facts) -> None:  # noqa: ANN001
    """"Why did Tara say so little on the 14th?" is exactly the question the
    audit trail has to answer, and a log written only on the happy path answers
    it for every morning except the ones anyone would ask about."""
    store = BriefStore(db)
    stored = await store.upsert(
        brief_for(
            full_facts,
            status=BriefStatus.VERIFIED_CORE_CARDS,
            degrade=DegradeReason.GROUNDING_FAILED,
        ),
        now=NOW,
    )
    await store.write_guidance_log(stored, now=NOW)
    log = await db.guidance_logs.find_one({"date": LOCAL_DATE})
    assert log["why"]["degrade_reason"] == DegradeReason.GROUNDING_FAILED.value
    assert log["why"]["status"] == BriefStatus.VERIFIED_CORE_CARDS.value


# --- notifications (§23.4) -------------------------------------------------


async def test_the_brief_push_expires_at_noon_local(db, full_facts) -> None:  # noqa: ANN001
    """§23.4: "morning brief push expires at 12:00 local (undelivered →
    dropped, not late-delivered)"."""
    stored = await BriefStore(db).upsert(brief_for(full_facts), now=NOW)
    row = notify.build(stored, timezone="Asia/Kolkata", due_at=DUE_AT)

    assert row is not None
    # 12:00 IST on 2026-08-12 is 06:30 UTC.
    assert row.expires_at == dt.datetime(2026, 8, 12, 6, 30, tzinfo=dt.UTC)
    assert row.message_class is notify.MessageClass.DAILY_LOOP


async def test_delivery_is_idempotent_on_user_and_message_id(db, full_facts) -> None:  # noqa: ANN001
    """§23.4, and §23.9 makes a duplicate delivery release-blocking."""
    stored = await BriefStore(db).upsert(brief_for(full_facts), now=NOW)
    queue = NotificationQueue(db)
    row = notify.build(stored, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert row is not None

    assert await queue.enqueue(row) is True
    assert await queue.enqueue(row) is False  # the retry, not a second push
    assert await db.notifications.count_documents({"message_id": row.message_id}) == 1


async def test_a_regenerated_brief_replaces_its_push(db, full_facts) -> None:  # noqa: ANN001
    """§23.4: "Collapse keys ensure a re-generated brief replaces, never
    duplicates, its push"."""
    store, queue = BriefStore(db), NotificationQueue(db)
    english = await store.upsert(brief_for(full_facts, locale="en"), now=NOW)
    first = notify.build(english, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert first is not None
    await queue.enqueue(first)

    hindi = await store.upsert(brief_for(full_facts, locale="hi"), now=NOW)
    second = notify.build(hindi, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert second is not None
    await queue.enqueue(second)

    queued = await db.notifications.find(
        {"status": NotificationStatus.QUEUED.value}
    ).to_list(None)
    assert len(queued) == 1, "exactly one push may be pending for a local date"
    assert queued[0]["locale"] == "hi"

    superseded = await db.notifications.count_documents(
        {"status": NotificationStatus.SUPERSEDED.value}
    )
    assert superseded == 1, "the old row is retired, not deleted — §23.8 counts it"


async def test_a_same_locale_regenerate_replaces_its_push(db, full_facts) -> None:  # noqa: ANN001
    """The defect the M6 review found, and the one that mattered most.

    §7.1's own worked example — "user flew to London overnight" — keeps the
    LOCALE, so it used to mint the same `message_id`, supersede the queued push
    and then fail to insert its replacement on the unique index. Net effect:
    the user's morning notification was CANCELLED by the regenerate meant to
    correct it. The locale-change test above passed throughout, because a new
    locale changes the id.

    The revision now comes from the brief's `generated_at`, which is stable
    across retries of one generation and different across generations.
    """
    store, queue = BriefStore(db), NotificationQueue(db)
    first = await store.upsert(brief_for(full_facts), now=NOW)
    row = notify.build(first, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert row is not None
    assert await queue.enqueue(row) is True

    # A retry of the SAME generation must not send twice (§23.4 idempotency).
    again = notify.build(first, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert again is not None
    assert await queue.enqueue(again) is False

    # The regenerate: same locale, recomputed for London. Note the SAME `now` —
    # the acceptance harness regenerates inside one second, and a clock-based
    # revision collided there. The revision fingerprints the delivery instead.
    second = await store.upsert(brief_for(full_facts), now=NOW)
    replacement = notify.build(second, timezone="Europe/London", due_at=DUE_AT)
    assert replacement is not None
    assert replacement.message_id != row.message_id
    assert replacement.collapse_key == row.collapse_key
    assert await queue.enqueue(replacement) is True

    queued = await db.notifications.find(
        {"status": NotificationStatus.QUEUED.value}
    ).to_list(None)
    assert len(queued) == 1, "exactly one push may be pending"
    assert queued[0]["message_id"] == replacement.message_id
    assert (
        await db.notifications.count_documents(
            {"status": NotificationStatus.SUPERSEDED.value}
        )
        == 1
    )


async def test_an_unchanged_regenerate_does_not_mint_a_second_push(db, full_facts) -> None:  # noqa: ANN001
    """A regenerate that changes nothing is not a new delivery.

    The revision fingerprints what would be DELIVERED — the brief's rendered
    modules and its schedule — so recomputing an identical brief for the same
    city produces the same id and §23.4's dedup absorbs it. A clock-based
    revision would have sent a second push for no reason.
    """
    store, queue = BriefStore(db), NotificationQueue(db)
    first = await store.upsert(brief_for(full_facts), now=NOW)
    row = notify.build(first, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert row is not None and await queue.enqueue(row) is True

    later = NOW + dt.timedelta(minutes=30)
    same = await store.upsert(brief_for(full_facts), now=later)
    unchanged = notify.build(same, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert unchanged is not None
    assert unchanged.message_id == row.message_id
    assert await queue.enqueue(unchanged) is False
    assert await db.notifications.count_documents({}) == 1


async def test_a_city_change_moves_the_expiry_and_replaces_the_push(db, full_facts) -> None:  # noqa: ANN001
    """§23.4 expires the morning push at 12:00 LOCAL, and Mumbai's noon is five
    and a half hours from London's. A regenerate that kept the old row would
    expire the brief against the wrong city."""
    store, queue = BriefStore(db), NotificationQueue(db)
    stored = await store.upsert(brief_for(full_facts), now=NOW)
    mumbai = notify.build(stored, timezone="Asia/Kolkata", due_at=DUE_AT)
    london = notify.build(stored, timezone="Europe/London", due_at=DUE_AT)
    assert mumbai is not None and london is not None

    assert london.expires_at != mumbai.expires_at
    assert london.message_id != mumbai.message_id
    assert await queue.enqueue(mumbai) is True
    assert await queue.enqueue(london) is True

    queued = await db.notifications.find(
        {"status": NotificationStatus.QUEUED.value}
    ).to_list(None)
    assert len(queued) == 1
    assert queued[0]["expires_at"] == london.expires_at


async def test_a_failed_insert_never_leaves_the_user_with_no_push(db, full_facts) -> None:  # noqa: ANN001
    """Why `enqueue` inserts BEFORE it supersedes.

    Superseding first is tidier — there is never a moment with two queued rows
    — and it is wrong in the one case that matters: if the insert then fails,
    the old row is already retired and nobody gets a brief. The worst case of
    inserting first is a moment with two rows, which the collapse key resolves.
    """
    store, queue = BriefStore(db), NotificationQueue(db)
    stored = await store.upsert(brief_for(full_facts), now=NOW)
    row = notify.build(stored, timezone="Asia/Kolkata", due_at=DUE_AT)
    assert row is not None
    await queue.enqueue(row)

    # The retry that used to wipe the queue.
    assert await queue.enqueue(row) is False
    still_queued = await db.notifications.count_documents(
        {"status": NotificationStatus.QUEUED.value}
    )
    assert still_queued == 1, "the pending push survived a duplicate enqueue"


async def test_the_collapse_key_ignores_locale(db, full_facts) -> None:  # noqa: ANN001
    """If the locale were in the collapse key the two pushes above would be
    two different messages and the user would receive both."""
    assert notify.collapse_key_for(USER_ID, LOCAL_DATE) == f"brief:{USER_ID}:{LOCAL_DATE}"


async def test_a_failed_brief_is_never_announced(db) -> None:  # noqa: ANN001
    """§29.2: pushing someone awake to tell them their brief did not work."""
    failed = Brief(
        user_id=USER_ID,
        local_date=LOCAL_DATE,
        locale="en",
        density=Density.MED,
        tier=Tier.PAYING,
        status=BriefStatus.FAILED,
    )
    assert notify.build(failed, timezone="Asia/Kolkata", due_at=DUE_AT) is None


async def test_a_degraded_brief_is_announced(db, full_facts) -> None:  # noqa: ANN001
    """It has real content, and §28.2's verified-core-cards variant says so on
    the card itself."""
    degraded = brief_for(full_facts, status=BriefStatus.VERIFIED_CORE_CARDS)
    assert notify.build(degraded, timezone="Asia/Kolkata", due_at=DUE_AT) is not None


async def test_a_brief_time_after_noon_still_gets_a_window(db, full_facts) -> None:  # noqa: ANN001
    """§23.4's noon rule is about staleness, not about censoring a user's own
    choice of brief time."""
    stored = await BriefStore(db).upsert(brief_for(full_facts), now=NOW)
    evening = dt.datetime(2026, 8, 12, 15, 30, tzinfo=dt.UTC)  # 21:00 IST
    row = notify.build(stored, timezone="Asia/Kolkata", due_at=evening)
    assert row is not None and row.expires_at > row.scheduled_at


# --- §32.13 / §32.7 key semantics ------------------------------------------


async def test_the_idempotency_key_carries_all_three_components() -> None:
    assert briefing_key("u", "2026-08-12", "hi") == "brief:u:2026-08-12:hi"
    assert is_stale(briefing_key("u", "2026-08-12", "en"), briefing_key("u", "2026-08-12", "hi"))
    same = briefing_key("u", "2026-08-12", "hi")
    assert not is_stale(same, same)


async def test_an_unkeyed_legacy_row_counts_as_stale() -> None:
    """A row written before the key existed cannot be shown to match, and
    regenerating one brief is cheaper than delivering one in the wrong language."""
    assert is_stale("", briefing_key("u", "2026-08-12", "hi"))


async def test_the_local_date_is_never_the_utc_date() -> None:
    """§32.13 is about the USER's calendar. 2026-08-11 20:00 UTC is already
    the 12th in Kolkata and still the 11th in London."""
    moment = dt.datetime(2026, 8, 11, 20, 0, tzinfo=dt.UTC)
    assert local_date_for(moment, "Asia/Kolkata") == "2026-08-12"
    assert local_date_for(moment, "Europe/London") == "2026-08-11"
    assert local_date_for(moment, "Pacific/Kiritimati") == "2026-08-12"
