"""ISO 15919 transliteration + the §22.10 confirmation contract.

Chaldean values are defined over the Latin transliteration of the name AS
SPOKEN. Non-Latin entry produces a *proposal* the user must confirm or edit;
the confirmed Latin form is canonical and is what the engine sums. Nothing here
decides on the user's behalf.

Devanagari only for M2 (hi/hi-Latn launch locales). Additional scripts arrive
with their language wave; an unsupported non-Latin script still requires
confirmation, it simply has no auto-proposal.
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal

from sitara_schemas import ErrorCode

from sitara_astro.errors import AstroError
from sitara_astro.pii import redact

ISO15919_SCHEME = "iso15919"
Script = Literal["latin", "devanagari", "unknown"]

VIRAMA = "्"

_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "ā", "इ": "i", "ई": "ī", "उ": "u", "ऊ": "ū",
    "ऋ": "r̥", "ॠ": "r̥̄", "ऌ": "l̥", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}

# Devanagari has no short/long e-o contrast, so ISO 15919's ē/ō carry no extra
# information here; plain e/o keeps the confirmation prompt readable (§22.10).
_MATRAS = {
    "ा": "ā", "ि": "i", "ी": "ī", "ु": "u", "ू": "ū", "ृ": "r̥", "ॄ": "r̥̄",
    "ॢ": "l̥", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}

_MARKS = {"ं": "ṁ", "ः": "ḥ", "ँ": "m̐"}

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ",
    "च": "c", "छ": "ch", "ज": "j", "झ": "jh", "ञ": "ñ",
    "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "ळ": "ḷ", "व": "v",
    "श": "ś", "ष": "ṣ", "स": "s", "ह": "h",
    # nukta forms (Urdu/Persian loans common in Indian names)
    "क़": "q", "ख़": "k͟h", "ग़": "ġ", "ज़": "z", "ड़": "ṛ", "ढ़": "ṛh", "फ़": "f",
}

# ISO 15919 diacritics → the readable ASCII the user actually confirms.
_FOLD = {
    "ā": "a", "ī": "i", "ū": "u", "ē": "e", "ō": "o",
    "r̥̄": "ri", "r̥": "ri", "l̥": "li",
    "ṅ": "n", "ñ": "n", "ṇ": "n", "ṭ": "t", "ḍ": "d", "ḷ": "l", "ṛ": "r",
    "ś": "sh", "ṣ": "sh", "ḥ": "h", "ġ": "g", "k͟h": "kh", "m̐": "n",
}
_LABIALS = frozenset("pbm")


def detect_script(text: str) -> Script:
    """Non-Latin wins on mixed input — the safe direction, since a mixed string
    still needs the user's eyes (§22.10)."""
    has_latin = False
    has_devanagari = False
    for char in text:
        if not char.isalpha():
            continue
        if "ऀ" <= char <= "ॿ":
            has_devanagari = True
        elif char.isascii():
            has_latin = True
    if has_devanagari:
        return "devanagari"
    if has_latin:
        return "latin"
    return "unknown"


def to_iso15919(text: str) -> str:
    """Devanagari → ISO 15919. Latin passes through untouched."""
    if detect_script(text) != "devanagari":
        return text
    # NFC keeps nukta consonants as single code points where possible
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    pending_inherent = False

    def flush() -> None:
        nonlocal pending_inherent
        if pending_inherent:
            out.append("a")
            pending_inherent = False

    index = 0
    while index < len(text):
        char = text[index]
        pair = text[index : index + 2]
        if pair in _CONSONANTS:  # decomposed nukta form
            flush()
            out.append(_CONSONANTS[pair])
            pending_inherent = True
            index += 2
            continue
        if char in _CONSONANTS:
            flush()
            out.append(_CONSONANTS[char])
            pending_inherent = True
        elif char in _MATRAS:
            pending_inherent = False  # the matra replaces the inherent vowel
            out.append(_MATRAS[char])
        elif char == VIRAMA:
            pending_inherent = False  # …and virama deletes it
        elif char in _INDEPENDENT_VOWELS:
            flush()
            out.append(_INDEPENDENT_VOWELS[char])
        elif char in _MARKS:
            flush()
            out.append(_MARKS[char])
        elif char == "़":  # standalone nukta: already handled above
            pass
        else:
            flush()
            out.append(char)
        index += 1
    flush()
    return "".join(out)


def fold_to_ascii(iso: str) -> str:
    """ISO 15919 → readable ASCII. This is the string shown for confirmation and,
    once confirmed, the string the Chaldean sum is taken over."""
    text = unicodedata.normalize("NFC", iso)
    out: list[str] = []
    index = 0
    while index < len(text):
        # anusvara assimilates to the following consonant's place of articulation
        # (ānaṁda → "ananda", not "anamda") — this is why folding is contextual.
        if text[index] == "ṁ":
            nxt = text[index + 1] if index + 1 < len(text) else ""
            out.append("m" if (nxt in _LABIALS or not nxt.isalpha()) else "n")
            index += 1
            continue
        for length in (3, 2, 1):
            chunk = text[index : index + length]
            if chunk in _FOLD:
                out.append(_FOLD[chunk])
                index += length
                break
        else:
            out.append(text[index])
            index += 1
    # strip any residual combining marks so the result is plain A-Z
    decomposed = unicodedata.normalize("NFD", "".join(out))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass(frozen=True)
class TransliterationProposal:
    """What the UI shows at onboarding step 10 (S10) before anything is stored.

    `confirmation_message_key` + `confirmation_params` keep the copy in the CMS
    per locale — the engine never emits user-facing English (§2.4).
    """

    original: str
    script: Script
    iso15919: str | None
    suggested_latin: str
    needs_confirmation: bool
    scheme: str | None
    confirmation_message_key: str = "numerology.transliteration.confirm"

    @property
    def confirmation_params(self) -> dict[str, str]:
        return {"name": self.suggested_latin}


def propose_transliteration(name: str) -> TransliterationProposal:
    """Build the confirmation proposal for a name as entered."""
    text = (name or "").strip()
    if not text:
        raise AstroError(
            ErrorCode.ASTRO_NAME_INVALID,
            message_key="errors.astro.name_invalid",
            detail="empty name",
        )
    script = detect_script(text)
    if script == "unknown":
        # No letters in ANY script: nothing to transliterate and nothing to
        # confirm — that is invalid input, not the §22.10 flow state.
        raise AstroError(
            ErrorCode.ASTRO_NAME_INVALID,
            message_key="errors.astro.name_invalid",
            detail=f"no alphabetic characters in name {redact(name)}",
        )
    if script == "latin":
        # Already Latin: no transliteration happened, so there is nothing to
        # confirm and nothing to second-guess about the user's own spelling.
        return TransliterationProposal(
            original=text,
            script=script,
            iso15919=None,
            suggested_latin=text,
            needs_confirmation=False,
            scheme=None,
        )
    iso = to_iso15919(text)
    suggested = " ".join(word.capitalize() for word in fold_to_ascii(iso).split())
    return TransliterationProposal(
        original=text,
        script=script,
        iso15919=iso if script == "devanagari" else None,
        suggested_latin=suggested,
        needs_confirmation=True,
        scheme=ISO15919_SCHEME if script == "devanagari" else None,
    )
