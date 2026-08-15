"""§22.13's clock and §30.3's arithmetic, with no database at all.

The whole of §22.13 is a comparison between two instants, so it is testable in
microseconds — which is what makes it affordable to check EVERY day boundary
rather than the two ends. `voice/entitlements.py` made the same bet about
minutes and the payoff is the same: the cases that actually bite (a boundary
off by one, a currency that met another currency) are the cheap ones to run.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.payments import (
    GRACE_PERIOD_DAYS,
    PLAN_IDS,
    READ_ONLY_PERIOD_DAYS,
    BillingRegion,
    Currency,
    PaymentFailureReason,
    PlanId,
    SubscriptionStatus,
)
from sitara_schemas.today import PlanState

from sitara_api.payments import lifecycle
from sitara_api.payments.lifecycle import AccessLevel, MigrationRefused, SubscriptionState
from sitara_api.payments.money import (
    ANNUAL_TERM_DAYS,
    PRICES,
    CurrencyMismatch,
    Money,
    NoSuchPrice,
    price_for,
)
from sitara_api.voice.entitlements import MINUTE_POOL, CallPlan

NOW = dt.datetime(2026, 8, 15, 9, 0, tzinfo=dt.UTC)


def _active(plan: PlanId = PlanId.MONTHLY, *, days: int = 30) -> SubscriptionState:
    return SubscriptionState(
        plan=plan,
        region=BillingRegion.INDIA,
        status=SubscriptionStatus.ACTIVE,
        period_start=NOW,
        period_end=NOW + dt.timedelta(days=days),
    )


# ---------------------------------------------------------------------------
# §22.13's ladder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("day", range(GRACE_PERIOD_DAYS))
def test_every_day_of_the_grace_is_full_access(day: int) -> None:
    """Parametrised over each day, not sampled at the ends.

    The failure worth catching is an off-by-one that revokes on day 6, and a
    two-point test cannot see one.
    """
    failed = lifecycle.fail_renewal(
        _active(), reason=PaymentFailureReason.INSUFFICIENT_FUNDS, now=NOW
    )
    at = NOW + dt.timedelta(days=day, hours=12)
    assert failed.access_at(at) is AccessLevel.FULL
    assert failed.project(at).status is SubscriptionStatus.GRACE


@pytest.mark.parametrize("day", range(GRACE_PERIOD_DAYS, GRACE_PERIOD_DAYS + READ_ONLY_PERIOD_DAYS))
def test_every_day_of_the_read_only_window_keeps_her_history(day: int) -> None:
    failed = lifecycle.fail_renewal(
        _active(), reason=PaymentFailureReason.BANK_TIMEOUT, now=NOW
    )
    at = NOW + dt.timedelta(days=day, hours=12)
    projected = failed.project(at)
    assert projected.status is SubscriptionStatus.READ_ONLY
    assert failed.access_at(at) is AccessLevel.READ_ONLY
    # §22.13: "no hard deletion". Asserted on every day of the window.
    assert projected.retains_history is True


def test_the_boundaries_are_exact_on_both_sides() -> None:
    failed = lifecycle.fail_renewal(_active(), reason=PaymentFailureReason.UNKNOWN, now=NOW)
    grace_end = NOW + dt.timedelta(days=GRACE_PERIOD_DAYS)
    downgrade = NOW + dt.timedelta(days=GRACE_PERIOD_DAYS + READ_ONLY_PERIOD_DAYS)

    assert failed.read_only_at == grace_end
    assert failed.downgrade_at == downgrade
    assert failed.access_at(grace_end - dt.timedelta(microseconds=1)) is AccessLevel.FULL
    assert failed.access_at(grace_end) is AccessLevel.READ_ONLY
    assert failed.access_at(downgrade - dt.timedelta(microseconds=1)) is AccessLevel.READ_ONLY
    assert failed.access_at(downgrade) is AccessLevel.NONE


def test_projection_is_idempotent_and_never_runs_backwards() -> None:
    """Two workers projecting one row must compute the same answer.

    That is what lets `read` write back what it finds without a transaction.
    """
    failed = lifecycle.fail_renewal(_active(), reason=PaymentFailureReason.UNKNOWN, now=NOW)
    for offset in (0, 3, 7, 20, 28, 400):
        at = NOW + dt.timedelta(days=offset)
        once = failed.project(at)
        assert once.project(at) == once
        # And projecting further never returns to a wider access level.
        later = once.project(at + dt.timedelta(days=1))
        assert _rank(later.status) >= _rank(once.status)


def _rank(status: SubscriptionStatus) -> int:
    return [
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.GRACE,
        SubscriptionStatus.READ_ONLY,
        SubscriptionStatus.DOWNGRADED,
    ].index(status)


def test_a_second_failure_does_not_restart_the_clock() -> None:
    """A rail retrying daily must not hold someone in grace forever.

    The generous-looking bug: every retry resets `renewal_failed_at`, §22.13's
    28 days never elapse, and nobody is ever downgraded. It reads as kindness
    and it means the dunning ladder does not exist.
    """
    first = lifecycle.fail_renewal(
        _active(), reason=PaymentFailureReason.INSUFFICIENT_FUNDS, now=NOW
    )
    again = lifecycle.fail_renewal(
        first, reason=PaymentFailureReason.BANK_TIMEOUT, now=NOW + dt.timedelta(days=3)
    )
    assert again.renewal_failed_at == NOW
    assert again.failure_reason is PaymentFailureReason.INSUFFICIENT_FUNDS


def test_a_renewal_preserves_the_billing_anchor() -> None:
    """The new period starts at the OLD period end, never at `now`."""
    state = _active()
    renewed = lifecycle.renew(state, term_days=30)
    assert renewed.period_start == state.period_end
    assert renewed.period_end == state.period_end + dt.timedelta(days=30)
    assert renewed.renewal_failed_at is None


def test_a_trial_that_lapses_gets_no_grace() -> None:
    """§22.13's dunning is about a renewal that FAILED. Nothing failed here —
    nobody was ever charged, so there is nothing to be in grace about."""
    trial = lifecycle.start_trial(region=BillingRegion.INDIA, now=NOW, term_days=7)
    assert trial.project(NOW + dt.timedelta(days=8)).status is SubscriptionStatus.DOWNGRADED


def test_cancelling_keeps_access_to_the_period_end_and_no_further() -> None:
    state = _active(days=30)
    cancelled = lifecycle.cancel(state)
    assert cancelled.access_at(NOW + dt.timedelta(days=29)) is AccessLevel.FULL
    assert cancelled.access_at(state.period_end) is AccessLevel.NONE
    assert cancelled.project(state.period_end).status is SubscriptionStatus.EXPIRED


def test_a_rejected_mandate_changes_exactly_one_field() -> None:
    """§30.3 — "subscription active on paid period"."""
    state = _active()
    after = lifecycle.reject_mandate(state)
    assert after.mandate_retry_required is True
    # Every other field, unchanged. Compared as a whole so a future addition
    # has to be considered rather than slipping through a field-by-field list.
    from dataclasses import replace

    assert replace(after, mandate_retry_required=False) == state


# ---------------------------------------------------------------------------
# §28.2's commercial variant
# ---------------------------------------------------------------------------


def test_read_only_renders_as_the_free_variant_and_not_as_grace() -> None:
    """The projection worth stating out loud.

    §28.2's `grace` variant keeps full features and shows an amber banner. A
    read-only account has neither — her past is there and new guidance is not
    — which is exactly §28.2's `free`. Mapping read-only to `grace` would show
    somebody a banner about features she no longer has.
    """
    failed = lifecycle.fail_renewal(_active(), reason=PaymentFailureReason.UNKNOWN, now=NOW)
    assert failed.plan_state_at(NOW + dt.timedelta(days=1)) is PlanState.GRACE
    assert failed.plan_state_at(NOW + dt.timedelta(days=10)) is PlanState.FREE
    assert failed.plan_state_at(NOW + dt.timedelta(days=40)) is PlanState.FREE


def test_every_status_maps_to_an_access_level_and_a_plan_state() -> None:
    """No status may be added without deciding both questions about it."""
    for status in SubscriptionStatus:
        assert status in lifecycle._ACCESS, f"{status} has no access level"  # noqa: SLF001
        assert status in lifecycle._PLAN_STATE, f"{status} has no §28.2 variant"  # noqa: SLF001


def test_live_covers_every_status_that_grants_access() -> None:
    """The uniqueness index's correctness, as a property rather than a list.

    `subscriptions.live` carries a partial unique index. If a status granted
    access without being live, two access-granting rows could coexist — which
    is a double subscription and a double renewal charge.
    """
    for status in SubscriptionStatus:
        if lifecycle._ACCESS[status] is not AccessLevel.NONE:  # noqa: SLF001
            assert lifecycle.is_live(status), f"{status} grants access but is not live"


# ---------------------------------------------------------------------------
# §30.3's gift extension and region migration
# ---------------------------------------------------------------------------


def test_extending_touches_only_the_period() -> None:
    from dataclasses import replace

    state = _active(PlanId.ANNUAL, days=300)
    extended = lifecycle.extend(state, days=ANNUAL_TERM_DAYS)
    assert extended.period_end == state.period_end + dt.timedelta(days=ANNUAL_TERM_DAYS)
    assert replace(extended, period_end=state.period_end) == state


def test_a_gift_revives_a_downgraded_subscription() -> None:
    """§22.13 deleted nothing, and the giver bought access."""
    failed = lifecycle.fail_renewal(_active(), reason=PaymentFailureReason.UNKNOWN, now=NOW)
    dead = failed.project(NOW + dt.timedelta(days=40))
    assert dead.status is SubscriptionStatus.DOWNGRADED

    revived = lifecycle.extend(dead, days=ANNUAL_TERM_DAYS)
    assert revived.status is SubscriptionStatus.ACTIVE
    assert revived.renewal_failed_at is None


def test_a_region_migration_is_refused_mid_cycle() -> None:
    """§30.3: "no mid-cycle conversion, ever". A refusal, not a deferral."""
    state = _active(days=30)
    with pytest.raises(MigrationRefused):
        lifecycle.migrate_region(state, region=BillingRegion.INTERNATIONAL, now=NOW)

    at_renewal = lifecycle.migrate_region(
        state, region=BillingRegion.INTERNATIONAL, now=state.period_end
    )
    assert at_renewal.region is BillingRegion.INTERNATIONAL
    # "Entitlements continue uninterrupted through migration."
    assert at_renewal.period_start == state.period_start
    assert at_renewal.period_end == state.period_end


def test_founding_pricing_never_crosses_a_region() -> None:
    """§30.3 — "promotional/founding pricing does NOT transfer automatically
    across regions (stated at switch)"."""
    from dataclasses import replace

    state = replace(_active(PlanId.ANNUAL, days=365), founding=True)
    migrated = lifecycle.migrate_region(
        state, region=BillingRegion.INTERNATIONAL, now=state.period_end
    )
    assert migrated.founding is False


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def test_two_currencies_can_never_meet() -> None:
    """§30.3 forbids the conversion that would resolve a mismatch, so there is
    no rate in this package and every combining operation raises."""
    rupees = Money(49_900, Currency.INR)
    dollars = Money(1_299, Currency.USD)
    for operation in (
        lambda: rupees + dollars,
        lambda: rupees - dollars,
        lambda: rupees < dollars,
    ):
        with pytest.raises(CurrencyMismatch):
            operation()


def test_money_refuses_a_float() -> None:
    """The oldest bug in commercial software, refused at construction."""
    with pytest.raises(TypeError):
        Money(499.0, Currency.INR)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(True, Currency.INR)  # type: ignore[arg-type]


def test_the_package_declares_no_exchange_rate() -> None:
    """Grepped, because the absence is the guarantee.

    §30.3 forbids conversion in four separate sentences. A rate constant
    anywhere in this package would be a rate somebody eventually applies.
    """
    from pathlib import Path

    import sitara_api.payments as package

    root = Path(package.__file__).parent
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for banned in ("exchange_rate", "fx_rate", "conversion_rate", "usd_per_inr"):
            assert banned not in source, f"{path.name} declares {banned}"


def test_every_declared_price_matches_the_spec() -> None:
    """§30.3 and §10-20 name six prices. These are those six."""
    assert PRICES[(BillingRegion.INDIA, PlanId.MONTHLY)].amount == Money(49_900, Currency.INR)
    assert PRICES[(BillingRegion.INDIA, PlanId.ANNUAL)].amount == Money(399_900, Currency.INR)
    assert PRICES[(BillingRegion.INTERNATIONAL, PlanId.MONTHLY)].amount == Money(
        1_299, Currency.USD
    )
    assert PRICES[(BillingRegion.INTERNATIONAL, PlanId.ANNUAL)].amount == Money(
        9_900, Currency.USD
    )
    assert price_for(BillingRegion.INDIA, PlanId.ANNUAL, founding=True).amount == Money(
        299_900, Currency.INR
    )
    assert price_for(
        BillingRegion.INTERNATIONAL, PlanId.ANNUAL, founding=True
    ).amount == Money(7_900, Currency.USD)


def test_the_total_including_tax_is_always_answerable() -> None:
    """§29.2's S31 acceptance: "price total incl. tax shown before payment
    rail". `PriceCard` requires it, so every price must produce one."""
    for (region, plan), price in PRICES.items():
        assert price.total_with_tax.currency is price.amount.currency
        assert price.tax_treatment in ("inclusive", "zero_rated"), (region, plan)


def test_an_undeclared_price_declines_rather_than_guessing() -> None:
    """§2.4's rule pointed at money. No default, no nearest region, no ×12."""
    with pytest.raises(NoSuchPrice):
        price_for(BillingRegion.INDIA, PlanId.MONTHLY, founding=True)


# ---------------------------------------------------------------------------
# The seam with §7.3's minute pool
# ---------------------------------------------------------------------------


def test_every_purchasable_plan_has_a_voice_minute_pool() -> None:
    """`PlanId` and `CallPlan` are separate enums, kept in step by this test.

    `voice.entitlements._plan_from` reads `subscriptions.plan` and falls back
    to `CallPlan.NONE` — zero minutes — for anything it does not recognise.
    That fail-small default is right, and it means a plan added to the price
    book without a pool would silently sell somebody a subscription with no
    voice minutes rather than failing anywhere visible.
    """
    for plan in PLAN_IDS:
        call_plan = CallPlan(plan.value)
        assert call_plan in MINUTE_POOL, f"{plan} has no §7.3 pool"


def test_call_plan_keeps_the_two_members_that_are_not_purchasable() -> None:
    """The other direction. `premium` is §7.3's unlimited fair-use tier and
    `none` is an account with no subscription — neither is a thing to sell, and
    neither may be dropped because `_plan_from` fails toward `NONE`."""
    assert CallPlan.PREMIUM in MINUTE_POOL
    assert MINUTE_POOL[CallPlan.NONE] == 0
    assert {p.value for p in PLAN_IDS}.isdisjoint({"premium", "none"})
