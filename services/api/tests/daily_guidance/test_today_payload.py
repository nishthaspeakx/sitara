"""§28.2's payload — what `GET /v1/today` actually serves.

`build_payload` is pure over its inputs and `compose_brief` needs no store, so
everything here runs without a database, a clock or a network. That is the
whole reason both were extracted: the interesting assertions are about what a
morning LOOKS like, and a test that needs Mongo to ask "does a degraded brief
say so" is a test nobody runs while changing the copy.
"""

from __future__ import annotations

import pytest
from sitara_schemas.facts import ConfidenceState
from sitara_schemas.today import BriefStatus, Density, PlanState, Tier

from sitara_api.daily_guidance import dev_fixtures
from sitara_api.daily_guidance.dev_router import LOCALES, dev_today
from sitara_api.daily_guidance.router import build_payload
from sitara_api.daily_guidance.types import Brief, BriefSubject

pytestmark = pytest.mark.asyncio


def subject(locale: str = "en", density: Density = Density.MED) -> BriefSubject:
    return BriefSubject(
        user_id=dev_fixtures.USER_ID,
        locale=locale,
        timezone="Asia/Kolkata",
        brief_time="07:00",
        density=density,
        tier=Tier.PAYING,
    )


# ---------------------------------------------------------------------------
# The wire shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variant", list(dev_fixtures.VARIANTS))
@pytest.mark.parametrize("locale", LOCALES)
async def test_every_variant_serves_a_valid_payload(variant, locale) -> None:  # noqa: ANN001
    payload = await dev_today(variant=variant, density=Density.MED, locale=locale)
    assert payload.local_time
    assert payload.state.brief_time == "07:00"
    # §28.2's anchor. Present on every morning, including the ones with no
    # modules at all — that is what "always present" has to mean.
    assert payload.taras_line is not None
    assert payload.taras_line.text.strip()


@pytest.mark.parametrize("variant", list(dev_fixtures.VARIANTS))
async def test_no_fact_id_reaches_the_wire(variant) -> None:  # noqa: ANN001
    """§30.4: fact-IDs are internal and never render.

    The payload has no field one could travel in, so this is really a check on
    `strip_citations`: the composer puts a marker INSIDE every claim-bearing
    sentence, and every one of them must be gone by the time it is serialised.
    """
    payload = await dev_today(variant=variant, density=Density.MED, locale="en")
    raw = payload.model_dump_json()
    assert "[[" not in raw
    assert "fact:" not in raw


# ---------------------------------------------------------------------------
# §7.1's ladder, as the screen sees it
# ---------------------------------------------------------------------------


async def test_a_degraded_morning_says_which_outcome_it_is() -> None:
    """Not merely "fewer cards".

    §28.2's provider-degraded variant needs three things to render honestly:
    the status, so the screen knows to show the note; the reason, so the log
    knows why; and §5.4's tradition-general state, which is the difference
    between "we could not do YOUR reading" and "we got it slightly wrong".
    """
    payload = await dev_today(variant="provider_degraded", density=Density.MED, locale="en")

    assert payload.status is BriefStatus.VERIFIED_CORE_CARDS
    assert payload.degrade_reason is not None
    assert payload.confidence is ConfidenceState.TRADITION_BASED_GENERAL

    # `ranking.core_cards` is deliberately narrower than LOW density, so a
    # contextual card here would be a card with no fact behind it.
    assert {m.module.value for m in payload.modules} <= {
        "moon_nakshatra_note",
        "energy_of_day",
        "personal_chart_theme",
    }


async def test_a_failed_brief_serves_a_screen_not_an_error() -> None:
    """§28.2's first-session variant is what a brief-less morning renders.

    The alternative — a 5xx on the app's home surface — replaces a designed
    state with an error page, and the state was designed precisely because this
    happens on everyone's first day.
    """
    payload = await dev_today(variant="first_session", density=Density.MED, locale="en")
    assert payload.modules == ()
    assert payload.status is BriefStatus.PENDING
    assert payload.taras_line is not None
    assert payload.state.first_session is True


# ---------------------------------------------------------------------------
# §28.2's density rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
async def test_density_changes_the_count_and_never_the_facts(locale) -> None:  # noqa: ANN001
    """"Density changes ranking-engine output count, never facts."

    The second half is the one worth a test: LOW and HIGH looking at the same
    morning must produce the same SENTENCES for the cards they share. A density
    that reworded a card would mean the engine had two versions of the day, and
    the user who moved the setting would find the sky had changed.
    """
    low = await dev_today(variant="normal_morning", density=Density.LOW, locale=locale)
    med = await dev_today(variant="normal_morning", density=Density.MED, locale=locale)
    high = await dev_today(variant="normal_morning", density=Density.HIGH, locale=locale)

    assert len(low.modules) < len(med.modules) <= len(high.modules)

    by_id = {m.module: m.text for m in high.modules}
    for module in low.modules:
        assert by_id[module.module] == module.text


# ---------------------------------------------------------------------------
# §32.1's inputs
# ---------------------------------------------------------------------------


async def test_a_festival_reaches_both_of_its_surfaces() -> None:
    """§28.2 puts a festival on the banner AND among the contextual cards.

    Left to its default relevance, `festival_observance` sits mid-pool and
    loses the MED-density cut, so a festival morning rendered no festival
    anywhere — the day's most visible fact, invisible. `compose_brief` nudges
    it; this is the test that the nudge survives.
    """
    payload = await dev_today(variant="festival", density=Density.MED, locale="en")
    assert payload.state.festival is not None
    assert payload.state.festival.name == "Raksha Bandhan"
    assert "festival_observance" in {m.module.value for m in payload.modules}


@pytest.mark.parametrize("locale", LOCALES)
async def test_a_festival_is_named_in_locale_or_not_at_all(locale) -> None:  # noqa: ANN001
    """§2.4: "a vendor's English festival name never reaches a user"."""
    payload = await dev_today(variant="festival", density=Density.MED, locale=locale)
    assert payload.state.festival is not None
    assert payload.state.festival.name.strip()
    if locale == "hi":
        assert any("ऀ" <= ch <= "ॿ" for ch in payload.state.festival.name)


async def test_the_worst_case_carries_every_input_the_rule_reads() -> None:
    """§32.1's named screenshot case. The PRECEDENCE is the client's; the
    server's job is to hand it a morning where all four things are true."""
    payload = await dev_today(variant="worst_case", density=Density.MED, locale="en")
    assert payload.state.plan is PlanState.GRACE
    assert payload.state.travel.active is True
    assert payload.state.festival is not None
    assert payload.state.trial_day == 6
    assert payload.state.birth_time_missing is True


# ---------------------------------------------------------------------------
# §30.4's three layers
# ---------------------------------------------------------------------------


async def test_the_trust_layers_never_contradict_each_other() -> None:
    """The defect the recorded fixtures caught.

    `sources_line` was derived from `len(module.snapshots)` — how many
    DIFFERENT facts a card stands on — while `plain` came from the confidence
    state. A card standing on one fact therefore said "checked against two
    sources" directly above "one source available today". Both are now read
    from the same thing, so they cannot disagree.
    """
    payload = await dev_today(variant="normal_morning", density=Density.HIGH, locale="en")
    for module in payload.modules:
        two_in_plain = "two sources" in module.trust.plain
        two_in_row = "2 sources" in module.trust.sources_line
        assert two_in_plain == two_in_row, module.module


async def test_a_brief_with_no_modules_still_builds_a_payload() -> None:
    """`build_payload` takes `None` for the brief, because `BriefStore.get`
    misses on every user's first morning and that is not an error path."""
    state = dev_fixtures.state_for("first_session", "en", Brief(
        user_id=dev_fixtures.USER_ID,
        local_date=dev_fixtures.LOCAL_DATE,
        locale="en",
        density=Density.MED,
        tier=Tier.PAYING,
        status=BriefStatus.PENDING,
    ))
    payload = build_payload(
        subject(),
        None,
        state,
        local_date=dev_fixtures.LOCAL_DATE,
        local_time="09:10",
    )
    assert payload.status is BriefStatus.PENDING
    assert payload.modules == ()
    assert payload.panchang == ()
    assert payload.taras_line is not None
