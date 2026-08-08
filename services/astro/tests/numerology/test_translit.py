"""ISO 15919 transliteration + the §22.10 confirmation contract.

§22.10: "Chaldean values are defined over the Latin transliteration of the name
as spoken. At onboarding, non-Latin name entry triggers an automatic ISO 15919
-based transliteration shown to the user for confirmation … the confirmed Latin
form is stored as the canonical numerology input."
"""

import pytest
from sitara_schemas import ErrorCode

from sitara_astro.errors import AstroError
from sitara_astro.numerology.translit import (
    ISO15919_SCHEME,
    detect_script,
    fold_to_ascii,
    propose_transliteration,
    to_iso15919,
)


class TestScriptDetection:
    @pytest.mark.parametrize(
        ("text", "script"),
        [
            ("Lakshmi", "latin"),
            ("लक्ष्मी", "devanagari"),
            ("Priya", "latin"),
            ("प्रिया", "devanagari"),
            ("  ", "unknown"),
        ],
    )
    def test_detect(self, text: str, script: str) -> None:
        assert detect_script(text) == script

    def test_mixed_script_reports_non_latin(self) -> None:
        """A mixed string still needs confirmation — the safe direction."""
        assert detect_script("Priya प्रिया") == "devanagari"


class TestIso15919:
    @pytest.mark.parametrize(
        ("devanagari", "iso"),
        [
            ("लक्ष्मी", "lakṣmī"),
            ("प्रिया", "priyā"),
            ("राम", "rāma"),
            ("सीता", "sītā"),
            ("अर्जुन", "arjuna"),
            ("कृष्ण", "kr̥ṣṇa"),
            ("गणेश", "gaṇeśa"),
            ("आनंद", "ānaṁda"),
            ("सुरेश", "sureśa"),
            ("अनिल", "anila"),
        ],
    )
    def test_known_names(self, devanagari: str, iso: str) -> None:
        assert to_iso15919(devanagari) == iso

    def test_inherent_vowel_and_virama(self) -> None:
        assert to_iso15919("क") == "ka"  # inherent a
        assert to_iso15919("क्") == "k"  # virama kills it
        assert to_iso15919("कि") == "ki"  # matra replaces it

    def test_independent_vs_dependent_vowels(self) -> None:
        assert to_iso15919("अ") == "a"
        assert to_iso15919("आ") == "ā"
        assert to_iso15919("इ") == "i"
        assert to_iso15919("का") == "kā"

    def test_anusvara_and_visarga(self) -> None:
        assert to_iso15919("कं") == "kaṁ"
        assert to_iso15919("कः") == "kaḥ"

    def test_conjunct_cluster(self) -> None:
        assert to_iso15919("क्ष") == "kṣa"

    def test_spaces_preserved(self) -> None:
        assert to_iso15919("राम कुमार") == "rāma kumāra"

    def test_latin_passes_through(self) -> None:
        assert to_iso15919("Lakshmi") == "Lakshmi"


class TestAsciiFold:
    @pytest.mark.parametrize(
        ("iso", "ascii_form"),
        [
            ("lakṣmī", "lakshmi"),
            ("priyā", "priya"),
            ("kr̥ṣṇa", "krishna"),
            ("gaṇeśa", "ganesha"),
            ("sītā", "sita"),
            ("ānaṁda", "ananda"),
            ("sureśa", "suresha"),
        ],
    )
    def test_fold(self, iso: str, ascii_form: str) -> None:
        assert fold_to_ascii(iso) == ascii_form

    def test_output_is_pure_ascii_letters(self) -> None:
        folded = fold_to_ascii("kr̥ṣṇa gaṇeśa")
        assert folded.replace(" ", "").isascii()
        assert folded.replace(" ", "").isalpha()


class TestProposalContract:
    def test_devanagari_requires_confirmation(self) -> None:
        proposal = propose_transliteration("लक्ष्मी")
        assert proposal.needs_confirmation
        assert proposal.original == "लक्ष्मी"
        assert proposal.script == "devanagari"
        assert proposal.iso15919 == "lakṣmī"
        assert proposal.suggested_latin == "Lakshmi"  # title-cased for display
        assert proposal.scheme == ISO15919_SCHEME

    def test_prompt_matches_the_spec_wording(self) -> None:
        """§22.10 quotes: "We read your name as 'Lakshmi' — correct?" — the
        engine supplies the key + value, the copy itself is i18n (§2.4)."""
        proposal = propose_transliteration("लक्ष्मी")
        assert proposal.confirmation_message_key == "numerology.transliteration.confirm"
        assert proposal.confirmation_params == {"name": "Lakshmi"}

    def test_latin_input_needs_no_confirmation(self) -> None:
        proposal = propose_transliteration("Lakshmi")
        assert not proposal.needs_confirmation
        assert proposal.suggested_latin == "Lakshmi"
        assert proposal.iso15919 is None

    def test_empty_input_rejected(self) -> None:
        """Empty is invalid input, not an unconfirmed transliteration (§34.4)."""
        with pytest.raises(AstroError) as exc_info:
            propose_transliteration("   ")
        assert exc_info.value.code is ErrorCode.ASTRO_NAME_INVALID

    def test_multiword_name(self) -> None:
        proposal = propose_transliteration("राम कुमार")
        assert proposal.suggested_latin == "Rama Kumara"
        assert proposal.needs_confirmation
