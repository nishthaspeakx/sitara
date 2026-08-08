"""CL-001 — the citation exemption for term-bearing, claim-free sentences.

The rule: a sentence carrying a strong term is exempt from citation only when
ALL FIVE hold — no number, no clock, no second-person reference, no temporal
deixis, and no celestial entity asserted to be doing or being anything.

Every case below is one of those five, or the two sentences the exemption
exists to permit. Each has a Devanagari and a Hinglish twin, because the rule
is only worth anything if it holds in the locales §2.4 forbids falling back
from.
"""

from __future__ import annotations

import pytest

from sitara_api.chat_orchestration.grounding import GroundingValidator


@pytest.fixture(scope="module")
def claims() -> GroundingValidator:
    return GroundingValidator()


def is_claim(validator: GroundingValidator, sentence: str, locale: str) -> bool:
    return validator._is_claim(sentence, locale)  # noqa: SLF001 — the unit under test


class TestTheExemptionPermits:
    """The two sentences the spec REQUIRES, which used to fail validation."""

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "Choghadiya are the traditional slots that mark auspicious and "
                   "inauspicious windows."),
            ("hi", "चौघड़िया दिन और रात के शुभ और अशुभ खंड होते हैं।"),
            ("hi-Latn", "Choghadiya din aur raat ke shubh aur ashubh hisse hote hain."),
        ],
    )
    def test_the_23_first_use_gloss_needs_no_citation(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        """§2.3: "Gloss a term in one short clause the first time it appears".
        A gloss defines a category; it asserts nothing about this person."""
        assert not is_claim(claims, sentence, locale)

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "It's all late-night windows rather than daytime ones — so this is a "
                   "partial picture, not the full day's choghadiya."),
            ("hi", "मेरे पास पूरे दिन का चौघड़िया नहीं है, केवल रात के हिस्से हैं।"),
            ("hi-Latn", "Mere paas poore din ka choghadiya nahin hai, sirf raat ke hisse hain."),
        ],
    )
    def test_honesty_about_coverage_needs_no_citation(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        """§0.7: Tara "owns limits without apology-spirals". Saying what she
        does NOT have is the opposite of a fabrication, and punishing it drove
        the turn into the fallback line."""
        assert not is_claim(claims, sentence, locale)

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "I don't have your birth chart yet."),
            ("hi", "मेरे पास आपकी जन्म कुंडली नहीं है।"),
            ("hi-Latn", "Mere paas aapki janm kundli nahin hai."),
        ],
    )
    def test_the_decline_sentence_still_passes(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        """A weak term with no number — §5.3's most important sentence."""
        assert not is_claim(claims, sentence, locale)


class TestTheExemptionRefuses:
    """A named body doing or being anything is never uncited."""

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "Venus is retrograde."),
            ("hi", "शुक्र वक्री है।"),
            ("hi-Latn", "Shukra vakri hai."),
        ],
    )
    def test_a_celestial_body_in_a_state_assertion_is_a_claim(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        """The required case: no number, no clock, no deixis, no "your" — and
        still a claim, because Venus is asserted to be something."""
        assert is_claim(claims, sentence, locale)

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "Saturn is moving through your tenth house."),
            ("hi", "शनि आपके दसवें भाव से गोचर कर रहा है।"),
            ("hi-Latn", "Shani aapke dasve bhaav se gochar kar raha hai."),
        ],
    )
    def test_a_motion_assertion_is_a_claim(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        assert is_claim(claims, sentence, locale)

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "The amrit choghadiya runs from 11:06 pm."),
            ("hi", "अमृत चौघड़िया रात ११:०६ से शुरू होता है।"),
            ("hi-Latn", "Amrit choghadiya 11:06 pm se shuru hota hai."),
        ],
    )
    def test_a_clock_value_is_a_claim(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        """Devanagari digits are normalised before the test — ११:०६ is a clock."""
        assert is_claim(claims, sentence, locale)

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "Today's choghadiya is favourable."),
            ("hi", "आज का चौघड़िया शुभ है।"),
            ("hi-Latn", "Aaj ka choghadiya shubh hai."),
        ],
    )
    def test_temporal_deixis_makes_a_category_term_a_claim(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        """"Choghadiya are auspicious windows" is a gloss; "TODAY's choghadiya
        is favourable" is a statement about this person's day."""
        assert is_claim(claims, sentence, locale)

    @pytest.mark.parametrize(
        ("locale", "sentence"),
        [
            ("en", "Your nakshatra favours steady work."),
            ("hi", "आपका नक्षत्र स्थिर काम के लिए अच्छा है।"),
            ("hi-Latn", "Aapka nakshatra sthir kaam ke liye achha hai."),
        ],
    )
    def test_second_person_makes_a_category_term_a_claim(
        self, claims: GroundingValidator, locale: str, sentence: str
    ) -> None:
        assert is_claim(claims, sentence, locale)


class TestDevanagariMatching:
    """The rule is only as good as the matching underneath it."""

    def test_devanagari_terms_actually_match(self, claims: GroundingValidator) -> None:
        """`\\b` cannot be used here: Devanagari vowel signs are combining
        marks Python does not count as word characters, so `\\bवक्री\\b` never
        fires and every Devanagari term sat inert. Regression guard."""
        assert is_claim(claims, "शनि वक्री है।", "hi")
        assert is_claim(claims, "चंद्रमा मीन राशि में है।", "hi")

    def test_a_term_inside_a_longer_word_does_not_match(
        self, claims: GroundingValidator
    ) -> None:
        """The boundary still has to be a boundary — the lookaround replaces
        `\\b`, it does not remove it."""
        assert not is_claim(claims, "The gulikaimeter reading was fine.", "en")


class TestResidualRisk:
    """The hole the rule leaves, asserted so it is visible rather than folklore."""

    def test_a_bare_category_statement_with_no_marker_passes_uncited(
        self, claims: GroundingValidator
    ) -> None:
        """A tradition statement with a copula but no named body is exempt —
        as designed. It says what a practice IS, not what today holds. If this
        ever needs to be a claim, that is a rule change, not a bug fix.

        Note "rahu kaal" would NOT be exempt: `rahu` is a graha name, so the
        celestial clause fires. The hole is narrower than it first looks."""
        assert not is_claim(claims, "Muhurat selection is an old tradition.", "en")
        assert is_claim(claims, "Rahu kaal is generally considered inauspicious.", "en")
