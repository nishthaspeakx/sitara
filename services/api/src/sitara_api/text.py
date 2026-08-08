"""Script-aware text primitives. One implementation, used everywhere.

Two defects found in M5 motivate this module, both of which made a matcher
silently weaker rather than noisily broken:

1. **`\\b` cannot delimit Devanagari.** Vowel signs (093A–094F) and the virama
   are Unicode combining marks, which Python excludes from `\\w`. So the "word"
   `वक्री` ends at `क्` as far as `\\b` is concerned, and `\\bवक्री\\b` never
   matches anything. Every Devanagari term in a `\\b`-delimited lexicon is
   inert, and nothing tells you.

2. **The danda `।` is inside the Devanagari block.** A lookaround written as
   `(?<![\\wऀ-ॿ])` treats U+0964 as word-internal, so any term at the end of a
   Devanagari sentence — which is most of the interesting ones — fails to
   match.

Both are the kind of bug that makes a SAFETY lexicon quietly stop working, so
the fix lives in one place with one set of tests rather than being re-derived
per module.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: Devanagari letters, signs, marks and digits — everything that is part of a
#: word. Deliberately stops before the danda ।(U+0964) and double danda
#: ॥(U+0965), which END words, and resumes at the digits (U+0966–096F).
DEVANAGARI_WORDISH = "ऀ-ॣ०-ॿ"

#: Devanagari letters and marks only, without digits — for tokenising.
DEVANAGARI_LETTERS = "ऀ-ॣॱ-ॿ"

#: The character class a term must not be adjacent to, to count as a whole
#: word. `\w` covers Latin/other scripts; the range covers Devanagari's
#: combining marks, which `\w` misses.
WORDISH = rf"\w{DEVANAGARI_WORDISH}"

#: Sentence-ending punctuation, Latin and Devanagari.
SENTENCE_END = r".!?।॥"

_DEVANAGARI_ANY = re.compile(f"[{DEVANAGARI_LETTERS}]")
_TOKEN = re.compile(f"[A-Za-z{DEVANAGARI_LETTERS}]+")
_SENTENCE_SPLIT = re.compile(f"(?<=[{SENTENCE_END}])\\s+")

#: Devanagari digits ०–९ → ASCII, so one number regex serves both scripts.
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def bounded(term: str) -> str:
    """Regex source matching `term` as a whole word, in any script.

    Use this instead of `\\b{term}\\b`. The lookarounds are what make it work
    for Devanagari; see the module docstring for why `\\b` cannot.
    """
    return rf"(?<![{WORDISH}]){re.escape(term)}(?![{WORDISH}])"


def alternation(terms: Iterable[str], *, min_length: int = 1) -> re.Pattern[str]:
    """One case-insensitive whole-word alternation over `terms`.

    Longest-first, so a multi-word term wins over its own prefix ("moon sign"
    over "moon"). An empty set compiles to a pattern that cannot fire, rather
    than to an empty alternation that matches everywhere.
    """
    ordered = sorted({t for t in terms if len(t) >= min_length}, key=len, reverse=True)
    if not ordered:
        return re.compile(r"(?!x)x")
    body = "|".join(re.escape(term) for term in ordered)
    return re.compile(rf"(?<![{WORDISH}])(?:{body})(?![{WORDISH}])", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Lower-cased word tokens, punctuation and digits removed.

    The danda is excluded from the token class, so "हैं।" tokenises as "हैं"
    rather than "हैं।" — a marker lexicon compares against the former.
    """
    return [token.lower() for token in _TOKEN.findall(text)]


def sentences(text: str) -> list[str]:
    """Split on Latin and Devanagari sentence enders."""
    return [chunk.strip() for chunk in _SENTENCE_SPLIT.split(text.strip()) if chunk.strip()]


def has_devanagari(text: str) -> bool:
    """True when the text carries Devanagari LETTERS — a stray danda alone is
    punctuation, not evidence of script."""
    return bool(_DEVANAGARI_ANY.search(text))


def ascii_digits(text: str) -> str:
    return text.translate(DEVANAGARI_DIGITS)


def is_inert(pattern: str) -> bool:
    """Can this regex match anything at all?

    A structural check for lexicon rot: build the plainest string the pattern
    describes — literals kept, `\\s+` a space, `\\b` dropped, alternations
    resolved to their first branch — and see whether the pattern matches it.
    It cannot prove a pattern is right; it proves the pattern is not DEAD,
    which is the failure mode `\\b`-over-Devanagari produces.
    """
    probe = _probe_string(pattern)
    if not probe:
        # A pattern the prober cannot reduce to any literal is a FINDING, not
        # a pass: it is exactly the shape a dead rule takes, and the sweep is
        # worthless if it waves through what it cannot understand.
        return True
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return True
    # Embed in a sentence: leading/trailing context is where boundary bugs bite.
    return not any(
        compiled.search(candidate)
        for candidate in (probe, f"{probe}।", f"तो {probe} ।", f"well {probe}.")
    )


_GROUP = re.compile(r"\((?:\?:)?([^()]*)\)")
_CHAR_CLASS = re.compile(r"\[(\^?)([^\]]*)\]")


def _probe_string(pattern: str) -> str:
    """The plainest string the pattern describes.

    Order matters. Optional tokens are dropped BEFORE classes are expanded,
    or `[-\\s]?` becomes a literal "-" and "self-harm" probes as "self-aharm".
    """
    text = pattern
    for _ in range(4):  # resolve nested groups a few levels deep
        text = _GROUP.sub(lambda m: m.group(1).split("|")[0], text)

    # .{0,20} → one filler char, not nothing: the surrounding `\s+` on both
    # sides needs something between them to sit around.
    text = re.sub(r"\.\{[^}]*\}", "x", text)
    text = re.sub(r"(?:\[[^\]]*\]|\\.|[^\\\[])\?", "", text)  # drop optional tokens
    text = text.replace(r"\s+", " ").replace(r"\s*", " ").replace(r"\s", " ")
    text = text.replace(r"\d", "5").replace(r"\w", "a")
    text = _CHAR_CLASS.sub(_first_member, text)
    text = re.sub(r"\\b|\\B|\^|\$", "", text)
    text = re.sub(r"[+*]", "", text)
    text = text.replace(r"\.", ".").replace("\\", "")
    return re.sub(r"\s{2,}", " ", text).strip()


def _first_member(match: re.Match[str]) -> str:
    """One character a class accepts. `[1-9]` → "1"; `[^x]` → "a"."""
    negated, body = match.group(1), match.group(2)
    if negated or not body:
        return "a"
    return body[0] if body[0] not in "-^" else (body[1] if len(body) > 1 else "a")


__all__ = [
    "DEVANAGARI_DIGITS",
    "DEVANAGARI_LETTERS",
    "DEVANAGARI_WORDISH",
    "SENTENCE_END",
    "WORDISH",
    "alternation",
    "ascii_digits",
    "bounded",
    "has_devanagari",
    "is_inert",
    "sentences",
    "tokenize",
]
