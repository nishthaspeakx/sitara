"""§7.1's priority queues, the pre-job's cell collapse, and the load simulation.

The simulation tests are the ones that check §7.1's own claims about itself:
that the hash smooths the IST-07:00 spike, and that §32.13's single-fire holds
across a whole day of ticks at scale.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.facts import Tradition

from sitara_api.daily_guidance.panchang_prejob import (
    PREJOB_LOCAL_MINUTE,
    cells_for,
    zones_crossing_prejob_hour,
)
from sitara_api.daily_guidance.priority import Entitlement, generates_ahead, tier_for
from sitara_api.daily_guidance.repository import offset_bands
from sitara_api.daily_guidance.simulate import SPIKE_SHARE, simulate
from sitara_api.daily_guidance.types import Tier
from sitara_api.daily_guidance.windows import TICK_MINUTES

NOW = dt.datetime(2026, 8, 12, 6, 0, tzinfo=dt.UTC)


# --- §7.1's three queues ---------------------------------------------------


def test_paying_beats_trial_beats_dormant() -> None:
    assert tier_for(Entitlement(plan="annual", status="active"), now=NOW) is Tier.PAYING
    assert tier_for(Entitlement(plan="trial", status="active"), now=NOW) is Tier.TRIAL
    assert tier_for(Entitlement(), now=NOW) is Tier.DORMANT


def test_a_paying_user_is_never_demoted_to_dormant() -> None:
    """The reading that matters: dormancy is the RESIDUAL tier, not a second
    dimension. A subscriber who took a fortnight's holiday must not come home
    to no brief, having paid for one every day of it."""
    assert tier_for(Entitlement(plan="monthly", status="active"), now=NOW) is Tier.PAYING


def test_payment_grace_keeps_the_morning() -> None:
    """§22.13's dunning window and §28.2's payment-grace variant: "full
    features intact during grace". Cutting the brief at the first failed
    mandate debit is the punitive pattern §29.2 forbids."""
    for status in ("past_due", "in_grace"):
        assert tier_for(Entitlement(plan="monthly", status=status), now=NOW) is Tier.PAYING


def test_an_expired_trial_is_dormant_whatever_the_row_says() -> None:
    """The nightly reconciliation may not have run. The wave should not spend a
    Claude call on the strength of a stale status."""
    expired = Entitlement(
        plan="trial", status="active", trial_ends_at=NOW - dt.timedelta(days=1)
    )
    assert tier_for(expired, now=NOW) is Tier.DORMANT

    live = Entitlement(
        plan="trial", status="active", trial_ends_at=NOW + dt.timedelta(days=1)
    )
    assert tier_for(live, now=NOW) is Tier.TRIAL


def test_only_dormant_users_are_generated_on_open() -> None:
    assert generates_ahead(Tier.PAYING) is True
    assert generates_ahead(Tier.TRIAL) is True
    assert generates_ahead(Tier.DORMANT) is False


# --- the 00:30 local-region pre-job ----------------------------------------


def test_cells_collapse_by_geohash_not_by_user() -> None:
    """§7.1: "thousands of users share one panchang doc". A city of ten
    thousand users costs exactly what a city of one does."""
    mumbai = (19.076, 72.877, "Asia/Kolkata", Tradition.AMANTA)
    pune = (18.520, 73.856, "Asia/Kolkata", Tradition.AMANTA)
    cells = cells_for([mumbai] * 10_000 + [pune] * 500, dt.date(2026, 8, 12))
    assert len(cells) == 2


def test_a_second_tradition_is_a_second_cell() -> None:
    """§7.2's key is date+geohash4+tradition; amanta and purnimanta name the
    month differently and cannot share a row."""
    mumbai = (19.076, 72.877, "Asia/Kolkata")
    cells = cells_for(
        [(*mumbai, Tradition.AMANTA), (*mumbai, Tradition.PURNIMANTA)],
        dt.date(2026, 8, 12),
    )
    assert len(cells) == 2


def test_a_cell_identity_carries_no_user() -> None:
    """A user id in a global key would fan one person's data across everyone
    sharing the row (§7.2, and `cache_keys.is_global_key`)."""
    cell = cells_for(
        [(19.076, 72.877, "Asia/Kolkata", Tradition.AMANTA)], dt.date(2026, 8, 12)
    )[0]
    assert cell.identity == ("2026-08-12", cell.geohash4, "amanta")


def test_the_prejob_fires_just_after_local_midnight() -> None:
    """§7.1: "a global pre-job at 00:30 LOCAL-REGION time" — warming a region's
    cells a few hours before that region's morning wave, not after it."""
    # 19:00 UTC is 00:30 IST the next day.
    at_ist_prejob = dt.datetime(2026, 8, 11, 19, 0, tzinfo=dt.UTC)
    due = dict(zones_crossing_prejob_hour(["Asia/Kolkata", "Europe/London"], at_ist_prejob))
    assert "Asia/Kolkata" in due
    assert "Europe/London" not in due
    # The date warmed is the one that has just STARTED — warming yesterday
    # would be consistent and useless.
    assert due["Asia/Kolkata"] == dt.date(2026, 8, 12)


def test_every_zone_is_warmed_exactly_once_a_day() -> None:
    zones = ["Asia/Kolkata", "Europe/London", "America/New_York", "Pacific/Chatham"]
    fired: dict[str, int] = {zone: 0 for zone in zones}
    start = dt.datetime(2026, 8, 12, tzinfo=dt.UTC)
    for step in range(48):  # 24h of 30-minute ticks
        moment = start + dt.timedelta(minutes=30 * step)
        for zone, _ in zones_crossing_prejob_hour(zones, moment):
            fired[zone] += 1
    assert fired == {zone: 1 for zone in zones}, fired


def test_the_prejob_minute_is_the_spec_value() -> None:
    assert PREJOB_LOCAL_MINUTE == 30


# --- the repository's band narrowing ---------------------------------------


def test_offset_bands_wrap_past_midnight_as_two_clauses() -> None:
    """A string range query cannot express "22:40–00:40" in one clause, and
    silently returning nothing for the wrap would drop every late-evening
    brief_time in that zone."""
    tick = dt.datetime(2026, 8, 12, 23, 0, tzinfo=dt.UTC)  # +30..+105 min crosses midnight
    bands = offset_bands(["Etc/UTC"], tick)
    assert len(bands) == 2
    assert bands[0][1] == "23:59"
    assert bands[1][0] == "00:00"


def test_offset_bands_cover_the_lead_window() -> None:
    """The band must contain every brief_time the tick could select — it
    narrows the query, `wave_member` decides."""
    tick = dt.datetime(2026, 8, 12, 1, 0, tzinfo=dt.UTC)  # 06:30 IST
    ((low, high),) = offset_bands(["Asia/Kolkata"], tick)
    # 06:30 IST + 30min = 07:00 through +90min+tick = 08:15.
    assert low <= "07:00" <= high


def test_one_band_per_distinct_offset_not_per_zone() -> None:
    """Kolkata and Colombo are both +05:30; two zones, one band."""
    tick = dt.datetime(2026, 8, 12, 1, 0, tzinfo=dt.UTC)
    assert len(offset_bands(["Asia/Kolkata", "Asia/Colombo"], tick)) == 1


# --- the load simulation (§7.1's own claims) -------------------------------


@pytest.fixture(scope="module")
def sim():  # noqa: ANN201
    return simulate(5000)


def test_every_eligible_user_is_generated_exactly_once(sim) -> None:  # noqa: ANN001
    """§32.13: "Date-line crossings can neither double-fire nor skip".

    `simulate` raises on a repeat, so reaching this assertion already proves
    no double-fire; the equality proves no skip.
    """
    eligible = sim.users - sim.dormant_skipped
    assert sim.generated == eligible


def test_dormant_users_are_never_generated_ahead(sim) -> None:  # noqa: ANN001
    """§7.1: "dormant users get on-open generation only — no waste"."""
    assert sim.dormant_skipped > 0
    assert sim.generated < sim.users


def test_the_hash_spreads_the_ist_spike(sim) -> None:  # noqa: ANN001
    """§7.1: "IST 07:00 is the global spike (≈60% of India users in one band)"
    and "waves spread across the 60-min lead window hashed by user_id".

    Without the hash the whole band lands on one tick. With it, no tick may
    carry more than a third of the band.
    """
    # Measured against GENERATED users, not the whole population: the spike
    # band contains dormant users too and §7.1 never schedules those.
    band = sum(sim.spike_per_tick.values())
    assert band == pytest.approx(sim.generated * SPIKE_SHARE, rel=0.02)

    busiest = max(sim.spike_per_tick.values())
    assert busiest / band < 0.34, (
        f"the hash left {busiest}/{band} of the 07:00 band on one tick"
    )
    # A 60-minute window sampled every 15 minutes gives four full ticks plus
    # the single minute that lands exactly on the fifth.
    assert len([v for v in sim.spike_per_tick.values() if v > band * 0.1]) >= 4


def test_every_lead_slot_is_used(sim) -> None:  # noqa: ANN001
    """All sixty minutes of §7.1's window carry load — a hash that used half
    of them would double the peak for no reason."""
    assert len(sim.slot_histogram) == 60
    smallest, largest = min(sim.slot_histogram.values()), max(sim.slot_histogram.values())
    assert largest < 2 * smallest, f"lopsided slots: {smallest}..{largest}"


def test_the_busiest_tick_is_a_small_fraction_of_the_day(sim) -> None:  # noqa: ANN001
    """The number the capacity plan is actually made of."""
    _, peak = sim.busiest_tick
    assert peak / sim.generated < 0.20


def test_the_simulation_runs_a_full_day_of_ticks(sim) -> None:  # noqa: ANN001
    assert sim.ticks == (24 * 60) // TICK_MINUTES
