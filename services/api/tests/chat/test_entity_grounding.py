"""§5.3's entity check — is a claim about the fact it cites?

The numeric check asks whether every number in a cited sentence appears in a
cited fact. It cannot ask the prior question, and the two failures look nothing
alike: "Venus is in your 10th house" citing Saturn's 10th-house fact has no
numeric problem at all — the 10 is right there, in the fact, verbatim.

M6 shipped exactly this. `moon_nakshatra_note` took the first nakshatra-shaped
value in a payload the engine emits Sun-first, so the first live brief said
"The Moon sits in Purva Bhadrapada today" citing the SUN's nakshatra. Every
gate green, the id in the served payload, the name matching the fact it named,
and the sentence false (CL-009). S18 made it worse rather than better: that
sentence now renders with a gold underline and opens a Trust Sheet showing the
other body's data underneath it.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.facts import (
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    Nakshatra,
    NakshatraBoundaryValue,
    NakshatraValue,
)

from sitara_api.chat_orchestration.grounding import GroundingValidator
from sitara_api.chat_orchestration.types import ValidatedFacts
from tests.chat.conftest import (
    IST,
    SATURN_FACT_ID,
    VENUS_FACT_ID,
    transit_house_fact,
)

SUN_NAK = "fact:natal.sun.nakshatra/2026-08-08/6a70000000000000000000a1@v1"
PANCHANG_NAK = "fact:panchang.nakshatra.boundary/2026-08-08/global@v1"


def _snap(fact_id: str, kind: FactKind, value: object) -> FactSnapshot:
    return FactSnapshot(
        fact_id=fact_id,
        kind=kind,
        value=value,  # type: ignore[arg-type]
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(ayanamsa="lahiri", tz=IST),
        valid_from=dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
        valid_to=dt.datetime(2026, 8, 8, 23, 59, tzinfo=dt.UTC),
        engine_semver="0.1.0",
        data_revision="test",
    )


@pytest.fixture()
def two_transits() -> ValidatedFacts:
    """Saturn really is in the 10th; Venus really is in the 5th."""
    return ValidatedFacts(
        snapshots=(
            transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),
            transit_house_fact(Graha.VENUS, 5, VENUS_FACT_ID),
        )
    )


@pytest.fixture()
def validator() -> GroundingValidator:
    return GroundingValidator()


# ---------------------------------------------------------------------------
# CL-009, verbatim
# ---------------------------------------------------------------------------


def test_the_m6_sentence_is_rejected(validator: GroundingValidator) -> None:
    """"The Moon sits in Purva Bhadrapada today", citing the SUN's nakshatra.

    The exact sentence the first live brief printed. It cites a real fact that
    really is in the payload, and it is about a different body.
    """
    facts = ValidatedFacts(
        snapshots=(
            _snap(
                SUN_NAK,
                FactKind.NATAL_GRAHA_NAKSHATRA,
                NakshatraValue(
                    graha=Graha.SUN,
                    nakshatra=Nakshatra.PURVA_BHADRAPADA,
                    nakshatra_index=25,
                    pada=1,
                ),
            ),
        )
    )

    verdict = validator.check(
        f"The Moon sits in Purva Bhadrapada today [[{SUN_NAK}]].", facts, "en"
    )

    assert verdict.ok is False
    assert verdict.entity_mismatches
    assert "moon" in verdict.entity_mismatches[0]
    assert "sun" in verdict.entity_mismatches[0]
    # And it is NOT reported as a numeric problem — the two fail for opposite
    # reasons and a reviewer reading the queue needs to see which.
    assert verdict.numeric_mismatches == ()


def test_the_same_sentence_about_the_right_body_passes(
    validator: GroundingValidator,
) -> None:
    facts = ValidatedFacts(
        snapshots=(
            _snap(
                SUN_NAK,
                FactKind.NATAL_GRAHA_NAKSHATRA,
                NakshatraValue(
                    graha=Graha.SUN,
                    nakshatra=Nakshatra.PURVA_BHADRAPADA,
                    nakshatra_index=25,
                    pada=1,
                ),
            ),
        )
    )
    verdict = validator.check(
        f"The Sun sits in Purva Bhadrapada today [[{SUN_NAK}]].", facts, "en"
    )
    assert verdict.ok is True


# ---------------------------------------------------------------------------
# The house shape, where the number alone can never tell
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("locale", "sentence"),
    [
        ("en", f"Venus is in your 10th house today [[{SATURN_FACT_ID}]]."),
        ("hi", f"आज शुक्र आपके 10वें भाव में हैं [[{SATURN_FACT_ID}]]।"),
        ("hi-Latn", f"Aaj Shukra aapke 10ve bhaav mein hain [[{SATURN_FACT_ID}]]."),
    ],
)
def test_the_wrong_graha_with_the_right_number_is_rejected(
    validator: GroundingValidator, two_transits: ValidatedFacts, locale: str, sentence: str
) -> None:
    """The number is in the cited fact, verbatim. The sentence is still false.

    In all three scripts, because the surface forms differ and a check that
    only worked in English would leave two locales exactly as exposed as
    before.
    """
    verdict = validator.check(sentence, two_transits, locale)

    assert verdict.ok is False
    assert verdict.entity_mismatches
    assert verdict.numeric_mismatches == ()


@pytest.mark.parametrize(
    ("locale", "sentence"),
    [
        ("en", f"Saturn is in your 10th house today [[{SATURN_FACT_ID}]]."),
        ("hi", f"आज शनि आपके 10वें भाव में हैं [[{SATURN_FACT_ID}]]।"),
        ("hi-Latn", f"Aaj Shani aapke 10ve bhaav mein hain [[{SATURN_FACT_ID}]]."),
        # §2.3 keeps English loanwords in Hinglish, and a real model writes
        # "Saturn" inside a Hindi reply as readily as शनि. Both must resolve.
        ("hi-Latn", f"Aaj Saturn aapke 10ve bhaav mein hain [[{SATURN_FACT_ID}]]."),
        ("hi", f"आज Saturn आपके 10वें भाव में हैं [[{SATURN_FACT_ID}]]।"),
    ],
)
def test_the_true_sentence_passes_in_every_script(
    validator: GroundingValidator, two_transits: ValidatedFacts, locale: str, sentence: str
) -> None:
    assert validator.check(sentence, two_transits, locale).ok is True


def test_a_synonym_is_the_same_body(validator: GroundingValidator) -> None:
    """बृहस्पति and गुरु are both Jupiter. A check that treated them as
    different would reject a true sentence in Hindi about half the time —
    which is precisely what my first audit script did, and it cried wolf."""
    jupiter = ValidatedFacts(
        snapshots=(transit_house_fact(Graha.JUPITER, 7, SATURN_FACT_ID),)
    )
    for name in ("गुरु", "बृहस्पति"):
        verdict = validator.check(
            f"आज {name} आपके 7वें भाव में हैं [[{SATURN_FACT_ID}]]।", jupiter, "hi"
        )
        assert verdict.ok is True, name


def test_any_overlap_acquits(validator: GroundingValidator, two_transits: ValidatedFacts) -> None:
    """One sentence about several bodies, citing several facts, is normal —
    a real model writes "Sun, Mercury and Moon are all in your 7th"."""
    verdict = validator.check(
        f"Saturn and Venus are both moving through your chart today "
        f"[[{SATURN_FACT_ID}]] [[{VENUS_FACT_ID}]].",
        two_transits,
        "en",
    )
    assert verdict.ok is True


# ---------------------------------------------------------------------------
# What it must NOT flag — the false-positive budget
# ---------------------------------------------------------------------------


def test_a_graha_claim_on_a_fact_with_no_graha_is_left_alone(
    validator: GroundingValidator,
) -> None:
    """"चंद्रमा आज रोहिणी में हैं" cites a panchang nakshatra boundary, which
    holds the nakshatra and NO graha — the Moon is implicit in what a panchang
    nakshatra is.

    The first cut of this check compared all bodies as one set and rejected
    that sentence, which is `moon_nakshatra_note`: the module CL-009 came from,
    failed for being right. Grahas are compared against grahas and nakshatras
    against nakshatras, never across.
    """
    facts = ValidatedFacts(
        snapshots=(
            _snap(
                PANCHANG_NAK,
                FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
                NakshatraBoundaryValue(
                    nakshatra=Nakshatra.ROHINI,
                    nakshatra_index=4,
                    starts_utc=dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
                    ends_utc=dt.datetime(2026, 8, 8, 14, 20, tzinfo=dt.UTC),
                ),
            ),
        )
    )
    verdict = validator.check(f"चंद्रमा आज रोहिणी में हैं [[{PANCHANG_NAK}]]।", facts, "hi")

    assert verdict.ok is True, verdict.reasons


def test_the_nakshatra_half_is_still_checked(validator: GroundingValidator) -> None:
    """Comparing like with like is not the same as not comparing. A sentence
    naming the WRONG nakshatra against a boundary fact is still caught."""
    facts = ValidatedFacts(
        snapshots=(
            _snap(
                PANCHANG_NAK,
                FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
                NakshatraBoundaryValue(
                    nakshatra=Nakshatra.ROHINI,
                    nakshatra_index=4,
                    starts_utc=dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
                    ends_utc=dt.datetime(2026, 8, 8, 14, 20, tzinfo=dt.UTC),
                ),
            ),
        )
    )
    verdict = validator.check(f"चंद्रमा आज अश्विनी में हैं [[{PANCHANG_NAK}]]।", facts, "hi")

    assert verdict.ok is False
    assert verdict.entity_mismatches


def test_a_sentence_naming_no_body_is_never_flagged(
    validator: GroundingValidator, two_transits: ValidatedFacts
) -> None:
    """A timing or house sentence that names no graha has nothing to compare,
    and the numeric check already owns its numbers."""
    verdict = validator.check(
        f"Your 10th house is active today [[{SATURN_FACT_ID}]].", two_transits, "en"
    )
    assert verdict.entity_mismatches == ()


def test_the_marker_net_survived_the_vocabulary_restructure() -> None:
    """`celestial` was a flat list and is now keyed by canonical body.

    Two readers iterate it — the strong lexicon and the claim marker — and the
    restructure silently handed them the dict's KEYS (`sun`, `moon`) instead of
    सूर्य and चंद्र. Every Devanagari and Hinglish graha name left the claim net,
    and `शनि वक्री है।` stopped being a claim at all. Four existing tests caught
    it; this one names the hazard so the next restructure does not have to
    rediscover it.
    """
    validator = GroundingValidator()
    for locale, sentence in (
        ("hi", "शनि वक्री है।"),
        ("hi-Latn", "Shukra vakri hai."),
    ):
        verdict = validator.check(sentence, ValidatedFacts(), locale)
        assert verdict.uncited_claims, f"{locale}: {sentence!r} is no longer a claim"
