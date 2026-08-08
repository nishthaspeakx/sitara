"""Stage 1 — language/script detection (§9, §2.3, §2.4).

Detection decides what the user WROTE. It never decides what Tara answers in:
§2.4 rules 3 and 4 are explicit that a mixed-language or Latin-typed turn is
answered "in the account locale", so the answering locale is the account
locale, full stop. What detection buys us is the ability to mirror borrowed
words naturally, and a recorded mismatch the language-quality validator can
check the reply against.

Deterministic, local, no model call: script is a Unicode-range question and
the Hinglish/English split is a closed marker lexicon. Spending a classifier
call on the first stage of every turn would cost latency (§8) for a decision
that regexes make correctly.
"""

from __future__ import annotations

import re
import unicodedata

from sitara_api import text as textutil
from sitara_api.chat_orchestration.types import LAUNCH_LOCALES, DetectedLanguage, Script

_LATIN_LETTER = re.compile(r"[A-Za-z]")

# Script detection and tokenising go through sitara_api.text: the Devanagari
# block contains the danda ।, so a naive [ऀ-ॿ] reads an English sentence with
# a stray danda as Devanagari and tokenises "हैं।" as one word — which no
# marker lexicon can then match.

#: Hinglish function words — the grammar of the sentence, not its nouns.
#: Nouns are unreliable here on purpose: "meeting", "budget" and "salary" are
#: natural English loanwords in Hinglish (§2.3 code-switching), so counting
#: them would read every Hinglish turn as English.
_HINGLISH_MARKERS: frozenset[str] = frozenset(
    {
        "aap", "aapka", "aapki", "aapke", "hai", "hain", "hoon", "ho", "tha", "thi", "the",
        "nahi", "nahin", "kya", "kyun", "kyon", "kaise", "kab", "kahan", "kaun", "kitna",
        "mera", "meri", "mere", "main", "mujhe", "hum", "humein", "tum", "tumhara",
        "karo", "karna", "karne", "kar", "kiya", "karta", "karti", "hoga", "hogi", "hoge",
        "achha", "accha", "theek", "thik", "bahut", "thoda", "abhi", "aaj", "kal", "phir",
        "lekin", "aur", "ya", "bhi", "toh", "to", "se", "ko", "ka", "ki", "ke", "mein",
        "par", "liye", "wala", "wali", "sahi", "galat", "shukriya", "dhanyavaad",
        "batao", "bataye", "chahiye", "sakta", "sakti", "raha", "rahi", "rahe", "gaya",
    }
)

#: Astrology vocabulary is native in every locale (§2.3), so seeing "nakshatra"
#: in a Latin-script turn says nothing about the language.
_LOCALE_NEUTRAL: frozenset[str] = frozenset(
    {
        "tithi", "nakshatra", "muhurat", "panchang", "rahu", "kaal", "choghadiya",
        "lagna", "rashi", "dasha", "kundli", "tara", "sitara", "yoga", "karana",
    }
)


def detect(text: str, account_locale: str) -> DetectedLanguage:
    """Return the answering locale (always the account locale) plus evidence."""
    script = detect_script(text)
    detected = _detect_locale(text, script)
    # Only a launch locale is ever named. An unrecognised language is reported
    # as a mismatch against the account locale rather than guessed at (§2.4).
    if detected not in LAUNCH_LOCALES:
        detected = account_locale

    confidence = _confidence(text, script, detected)
    return DetectedLanguage(
        locale=account_locale,
        script=script,
        detected_locale=detected,
        matches_profile=detected == account_locale,
        confidence=confidence,
    )


def detect_script(text: str) -> Script:
    has_deva = textutil.has_devanagari(text)
    has_latin = bool(_LATIN_LETTER.search(text))
    if has_deva and has_latin:
        return Script.MIXED
    if has_deva:
        return Script.DEVANAGARI
    if has_latin:
        return Script.LATIN
    return Script.UNKNOWN


def script_of_locale(locale: str) -> Script:
    """The script a reply in `locale` must be written in (§2.3)."""
    return Script.DEVANAGARI if locale == "hi" else Script.LATIN


def _detect_locale(text: str, script: Script) -> str:
    if script in (Script.DEVANAGARI, Script.MIXED):
        return "hi"
    if script is Script.UNKNOWN:
        return ""
    words = textutil.tokenize(text)
    meaningful = [w for w in words if w not in _LOCALE_NEUTRAL]
    if not meaningful:
        return ""
    hits = sum(1 for w in meaningful if w in _HINGLISH_MARKERS)
    # One function word in a short turn is weak evidence; the ratio carries
    # short turns and the absolute count carries long ones.
    if hits >= 2 or (hits == 1 and len(meaningful) <= 4):
        return "hi-Latn"
    return "en"


def _confidence(text: str, script: Script, detected: str) -> float:
    if script is Script.UNKNOWN or not detected:
        return 0.0
    if script in (Script.DEVANAGARI, Script.MIXED):
        return 0.95
    words = textutil.tokenize(text)
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in _HINGLISH_MARKERS)
    ratio = hits / len(words)
    if detected == "hi-Latn":
        return round(min(0.95, 0.5 + ratio * 2), 2)
    return round(max(0.5, 1 - ratio * 2), 2)


def contains_wrong_script(text: str, locale: str) -> bool:
    """Script-match check for the language-quality validator (§9).

    A Hindi reply that drifted into Latin, or an English reply carrying
    Devanagari, is a §2.4 failure — not a stylistic preference. Digits,
    punctuation and glossary terms (Tara, Sitara) are script-neutral and are
    stripped before the check so they cannot trip it.
    """
    stripped = _strip_neutral(text)
    if not stripped:
        return False
    expected = script_of_locale(locale)
    if expected is Script.DEVANAGARI:
        # Hindi may carry a few Latin loanwords; a majority-Latin reply is the
        # failure. §2.3 caps Hindi at ≤10% English tokens.
        latin = len(_LATIN_LETTER.findall(stripped))
        deva = len(re.findall(f'[{textutil.DEVANAGARI_LETTERS}]', stripped))
        return deva == 0 or latin > deva
    return textutil.has_devanagari(stripped)


def _strip_neutral(text: str) -> str:
    kept = []
    for char in text:
        if char.isdigit() or unicodedata.category(char).startswith("P") or char.isspace():
            continue
        kept.append(char)
    out = "".join(kept)
    for term in ("Tara", "Sitara"):
        out = out.replace(term, "")
    return out
