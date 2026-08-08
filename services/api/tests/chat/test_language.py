"""§2.3 / §2.4 — detection in, language-quality validation out."""

import pytest

from sitara_api.chat_orchestration.langquality import LanguageQualityValidator
from sitara_api.chat_orchestration.language import contains_wrong_script, detect
from sitara_api.chat_orchestration.types import Script


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How does today look for me?", "en"),
        ("Aap batayein, aaj ka din kaisa hai?", "hi-Latn"),
        ("आज का दिन कैसा रहेगा?", "hi"),
    ],
)
def test_detects_the_launch_locales(text: str, expected: str) -> None:
    assert detect(text, "en").detected_locale == expected


def test_reply_locale_is_always_the_account_locale() -> None:
    """§2.4 rules 3 and 4: a mixed or Latin-typed turn is answered in the
    account locale. Detection informs; it never decides."""
    detected = detect("Aaj ka din kaisa hai?", account_locale="hi")

    assert detected.locale == "hi"
    assert detected.detected_locale == "hi-Latn"
    assert not detected.matches_profile


def test_devanagari_is_recognised_as_its_script() -> None:
    assert detect("आज", "hi").script is Script.DEVANAGARI
    assert detect("aaj", "hi").script is Script.LATIN
    assert detect("आज ka din", "hi").script is Script.MIXED


def test_astrology_vocabulary_does_not_decide_the_language() -> None:
    """§2.3 keeps astrology vocabulary native in every locale, so "nakshatra"
    in Latin script says nothing about which language was typed."""
    assert detect("What is my nakshatra?", "en").detected_locale == "en"


def test_script_mismatch_is_a_failure_not_a_preference() -> None:
    assert contains_wrong_script("Today is a calm day for finishing things.", "hi")
    assert not contains_wrong_script("आज का दिन शांत है।", "hi")
    assert not contains_wrong_script("Today is a calm day.", "en")


def test_hindi_reply_may_carry_a_few_english_loanwords() -> None:
    """§2.3 caps Hindi at ≤10% English tokens — a few is fine, a majority is not."""
    assert not contains_wrong_script("आज आपकी meeting अच्छी रहेगी।", "hi")


# --------------------------------------------------------------------------
# The validator
# --------------------------------------------------------------------------


def _check(text: str, locale: str):  # noqa: ANN202
    return LanguageQualityValidator(glossary=(("Tara", ()), ("Sitara", ()))).check(text, locale)


def test_english_reply_to_a_hindi_account_fails() -> None:
    """§2.4 rule 8's whole point: never an English reply without consent."""
    verdict = _check("Today is a good day to finish what you started.", "hi")

    assert not verdict.ok
    assert any("script" in failure for failure in verdict.failures)


def test_intimate_address_is_a_failure() -> None:
    """§2.3: Tara never switches to intimate forms uninvited."""
    verdict = _check("Tu aaj thoda aaram kar le.", "hi-Latn")

    assert not verdict.ok
    assert any("intimate" in failure for failure in verdict.failures)


def test_tara_is_never_called_an_avatar() -> None:
    verdict = _check("I'm your avatar guide for today.", "en")

    assert not verdict.ok
    assert any("avatar" in failure for failure in verdict.failures)


def test_respectful_hinglish_passes() -> None:
    verdict = _check(
        "Aaj aapka din shaant rahega — jo shuru kiya tha, use poora karein.", "hi-Latn"
    )

    assert verdict.ok, verdict.failures


@pytest.mark.parametrize(
    "text",
    [
        "Is tarah se aap apna din shuru kar sakti hain, dheere dheere.",
        "Kis tarah ka kaam aaj aapke liye theek rahega, sochte hain.",
    ],
)
def test_a_glossary_term_inside_another_word_is_not_a_violation(text: str) -> None:
    """"tarah" is everyday Hinglish for "way". A substring check reads "Tara"
    inside it and burns §9's single regeneration on a word Tara may use."""
    verdict = _check(text, "hi-Latn")

    assert verdict.ok, verdict.failures


def test_a_genuinely_altered_glossary_term_is_still_caught() -> None:
    verdict = _check("Main tara hoon, aapki guide.", "hi-Latn")

    assert not verdict.ok
    assert any("Tara" in failure for failure in verdict.failures)


def test_a_short_reply_is_not_convicted_of_drift() -> None:
    """Three words carry too little signal to accuse a reply of switching
    language; §14's native reviewer owns the judgement calls."""
    verdict = _check("Bilkul.", "hi-Latn")

    assert verdict.ok, verdict.failures


def test_a_capitalised_domain_term_is_not_an_altered_glossary_term() -> None:
    """glossary.json's rule for the domain terms is "kept native in all
    locales" — about translation, not capitalisation. Flagging a
    sentence-initial "Nakshatra" failed ordinary replies (CL-005)."""
    validator = LanguageQualityValidator()

    for text in (
        "Nakshatra ke hisaab se aaj ka din shaant hai.",
        "Aaj Panchang dekhte hain.",
        "Muhurat ke liye shaam achhi hai.",
    ):
        assert validator.check(text, "hi-Latn").ok, text


def test_the_proper_nouns_are_still_case_sensitive() -> None:
    """Tara and Sitara are brand names, not domain vocabulary."""
    verdict = LanguageQualityValidator().check("Main tara hoon, aapki guide.", "hi-Latn")

    assert not verdict.ok
    assert any("Tara" in failure for failure in verdict.failures)


def test_devanagari_in_a_hinglish_reply_is_still_a_script_failure() -> None:
    """§2.3: Hinglish is Latin script. The validator was right about this one
    — the fix is in the prompt, not here."""
    verdict = LanguageQualityValidator().check("Aaj ka नक्षत्र rohini hai.", "hi-Latn")

    assert not verdict.ok
    assert any("script" in failure for failure in verdict.failures)
