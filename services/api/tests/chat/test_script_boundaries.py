"""Script-aware matching, and a sweep proving no lexicon has gone inert.

Two Devanagari defects in M5 made matchers silently weaker: `\\b` cannot
delimit a script whose vowel signs are combining marks, and the danda sits
inside the Devanagari block so terms at a sentence's end never matched. Both
failed silently — a safety lexicon that matches nothing looks exactly like a
safe conversation.

`sitara_api.text` is now the one implementation. These tests cover it, every
site that uses it, and — the point of the exercise — assert that every pattern
in the SAFETY corpora can still match something at all.
"""

from __future__ import annotations

import re

import pytest

from sitara_api import text as textutil
from sitara_api.chat_orchestration import config
from sitara_api.chat_orchestration.grounding import GroundingValidator
from sitara_api.chat_orchestration.langquality import LanguageQualityValidator
from sitara_api.chat_orchestration.language import contains_wrong_script, detect_script
from sitara_api.chat_orchestration.safety import FearSellingLint, RuleLexicon
from sitara_api.chat_orchestration.types import RiskClass, Script


def _all_patterns(document: dict, key: str) -> list[tuple[str, str, str]]:
    """(locale, rule id, pattern) for every entry in a policy corpus."""
    rows = []
    for locale, entries in document[key].items():
        for entry in entries:
            for pattern in entry["patterns"]:
                rows.append((locale, entry.get("id") or entry["risk_class"], pattern))
    return rows


SAFETY_PATTERNS = _all_patterns(config.safety_rules(), "rules")
FEAR_PATTERNS = _all_patterns(config.fear_selling_corpus(), "corpus")


class TestNoLexiconIsInert:
    """The sweep. A pattern that cannot match anything is a dead rule."""

    @pytest.mark.parametrize(
        ("locale", "rule_id", "pattern"),
        SAFETY_PATTERNS,
        ids=[f"{loc}-{rid}-{i}" for i, (loc, rid, _) in enumerate(SAFETY_PATTERNS)],
    )
    def test_every_l1_safety_pattern_can_match(
        self, locale: str, rule_id: str, pattern: str
    ) -> None:
        """§9's L1 lexicon is the fail-safe rung — it must work when the
        classifier is down, which means it must work at all."""
        assert not textutil.is_inert(pattern), f"{locale}/{rule_id}: {pattern!r} matches nothing"

    @pytest.mark.parametrize(
        ("locale", "rule_id", "pattern"),
        FEAR_PATTERNS,
        ids=[f"{loc}-{rid}-{i}" for i, (loc, rid, _) in enumerate(FEAR_PATTERNS)],
    )
    def test_every_fear_selling_pattern_can_match(
        self, locale: str, rule_id: str, pattern: str
    ) -> None:
        assert not textutil.is_inert(pattern), f"{locale}/{rule_id}: {pattern!r} matches nothing"

    def test_the_sweep_would_catch_the_defect_it_was_written_for(self) -> None:
        """Guard the guard: if `is_inert` stopped detecting the `\\b` bug, the
        sweep above would pass vacuously forever."""
        assert textutil.is_inert(r"\bवक्री\b")
        assert textutil.is_inert(r"\bआत्महत्या\b")
        assert not textutil.is_inert(r"आत्महत्या")


class TestSharedBoundary:
    @pytest.mark.parametrize(
        ("term", "sentence"),
        [
            ("वक्री", "शुक्र वक्री है।"),
            ("आत्महत्या", "मैं आत्महत्या के बारे में सोच रही हूँ।"),
            ("चौघड़िया", "आज का चौघड़िया।"),
            ("है", "वह ठीक है"),
            ("choghadiya", "aaj ka choghadiya."),
        ],
    )
    def test_a_term_matches_at_a_sentence_end(self, term: str, sentence: str) -> None:
        """The danda case. `\\b` and a block-wide lookaround both fail here."""
        assert re.search(textutil.bounded(term), sentence)

    def test_a_term_inside_a_longer_word_does_not_match(self) -> None:
        assert not re.search(textutil.bounded("kaal"), "kaalchakra")
        assert not re.search(textutil.bounded("गुरु"), "गुरुवार")

    def test_tokenize_drops_the_danda(self) -> None:
        assert textutil.tokenize("आप कैसी हैं।") == ["आप", "कैसी", "हैं"]

    def test_a_stray_danda_is_not_devanagari_script(self) -> None:
        """Punctuation is not evidence of script — otherwise an English reply
        containing a danda reads as MIXED and trips the §2.3 script check."""
        assert not textutil.has_devanagari("hello there ।")
        assert detect_script("hello there ।") is Script.LATIN

    def test_devanagari_digits_normalise(self) -> None:
        assert textutil.ascii_digits("११:०६") == "11:06"


class TestFixedSites:
    """One test per site that used a hand-rolled boundary."""

    @pytest.mark.asyncio
    async def test_l1_rules_fire_on_devanagari_at_a_sentence_end(self) -> None:
        """The site that mattered most: a crisis message ending in a danda."""
        scores = RuleLexicon().score("मैं अब जीना नहीं चाहती।", "hi")

        assert scores.get(RiskClass.ACUTE_CRISIS, 0.0) >= 0.9

    def test_fear_selling_fires_on_devanagari_at_a_sentence_end(self) -> None:
        verdict = FearSellingLint().check("इसका कोई उपाय नहीं है।", "hi")

        assert not verdict.ok

    def test_grounding_matches_devanagari_at_a_sentence_end(self) -> None:
        validator = GroundingValidator()

        assert validator._is_claim("शनि वक्री है।", "hi")  # noqa: SLF001

    def test_glossary_lint_matches_devanagari_at_a_sentence_end(self) -> None:
        """§2.3's honorific check: "तू" as the last word before a danda."""
        verdict = LanguageQualityValidator().check("आज तू आराम कर।", "hi")

        assert not verdict.ok
        assert any("intimate" in failure for failure in verdict.failures)

    def test_script_check_still_flags_an_english_reply_to_a_hindi_user(self) -> None:
        assert contains_wrong_script("Today is a calm day for finishing things.", "hi")
        assert not contains_wrong_script("आज का दिन शांत है।", "hi")


class TestEveryCelestialBodyHasASurfaceInEveryLocale:
    """The claim lexicon must be able to NAME every body the engine can emit.

    Found by hand on 16 Aug 2026: `terms.rashi.*` did not exist in any catalog,
    so `_celestial_map` fell back to the bare enum value and the twelve rashis
    had no English surface beyond their Sanskrit id. A reply saying "your Moon
    is in Libra" named a rashi the entity check could not identify — so the
    (d) check (a sentence about a different BODY from the fact it cites) was
    blind for rashis in English.

    It surfaced only as a `brief term missing` log line during seeding, which
    is exactly how CL-015 hid too: the validator does not fail when a surface
    is absent, it simply stops recognising the claim.
    """

    LOCALES = ("en", "hi", "hi-Latn")

    @pytest.mark.parametrize("locale", LOCALES)
    def test_every_enum_member_resolves_from_its_own_locale_rendering(
        self, locale: str
    ) -> None:
        from sitara_schemas.facts import Graha, Nakshatra, Rashi

        from sitara_api.chat_orchestration.grounding import GroundingValidator
        from sitara_api.localisation import MissingString, resolve

        surfaces = GroundingValidator()._celestial_map(locale).surfaces
        for enum, kind in ((Graha, "graha"), (Rashi, "rashi"), (Nakshatra, "nakshatra")):
            for member in enum:
                try:
                    rendered = resolve(f"terms.{kind}.{member.value}", locale)
                except MissingString:  # pragma: no cover - the failure being guarded
                    raise AssertionError(
                        f"terms.{kind}.{member.value} missing in {locale} — the claim "
                        "lexicon cannot name it, so a sentence about it is not a claim"
                    ) from None
                assert surfaces.get(rendered.lower()) == member.value, (
                    f"{locale}: {rendered!r} does not resolve to {member.value!r}"
                )

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_western_sign_names_resolve_too(self, locale: str) -> None:
        """§2.3 keeps English loanwords in every locale, and a reply may say
        "Libra" rather than "Tula" — in English, and in a Hinglish sentence."""
        from sitara_api.chat_orchestration.grounding import GroundingValidator

        surfaces = GroundingValidator()._celestial_map(locale).surfaces
        for western, canonical in (
            ("libra", "tula"),
            ("taurus", "vrishabha"),
            ("capricorn", "makara"),
            ("pisces", "meena"),
        ):
            assert surfaces.get(western) == canonical, f"{locale}: {western} unmapped"
