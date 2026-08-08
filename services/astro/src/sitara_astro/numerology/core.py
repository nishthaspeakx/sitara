"""Numerology arithmetic: reduction, moolank, bhagyank, name numbers.

Pure functions over a date and a Latin string. Every result carries its
reduction trail so a Trust Sheet can show the working (§5.3 cite-or-die).
"""

from datetime import date

from sitara_schemas import ErrorCode
from sitara_schemas.facts import MasterNumberPolicy, NumerologySystem

from sitara_astro.errors import AstroError
from sitara_astro.numerology.tables import CHALDEAN, MASTER_NUMBERS, PYTHAGOREAN
from sitara_astro.pii import redact

_TABLES: dict[NumerologySystem, object] = {
    NumerologySystem.CHALDEAN: CHALDEAN,
    NumerologySystem.PYTHAGOREAN: PYTHAGOREAN,
}


def reduce_number(
    total: int, policy: MasterNumberPolicy
) -> tuple[int, tuple[int, ...]]:
    """Reduce to a single digit, returning (value, full trail incl. the start).

    Under PRESERVE, reduction halts on 11/22/33 — the Western master-number
    convention. Default REDUCE goes all the way to 1-9 (Indian convention).
    """
    if total < 1:
        raise ValueError(f"numerology totals are positive; got {total}")
    trail = [total]
    current = total
    while current > 9:
        if policy is MasterNumberPolicy.PRESERVE and current in MASTER_NUMBERS:
            break
        current = sum(int(digit) for digit in str(current))
        trail.append(current)
    return current, tuple(trail)


def moolank(dob: date, policy: MasterNumberPolicy) -> tuple[int, tuple[int, ...]]:
    """Root number — the birth DAY alone, reduced."""
    return reduce_number(dob.day, policy)


def bhagyank(dob: date, policy: MasterNumberPolicy) -> tuple[int, tuple[int, ...]]:
    """Destiny number — every digit of the full birth date, reduced."""
    return reduce_number(sum(date_digits(dob)), policy)


def date_digits(dob: date) -> tuple[int, ...]:
    """Always eight digits. Explicit formatting, not strftime: %Y zero-padding
    below year 1000 is platform-dependent and would diverge macOS from CI."""
    return tuple(int(c) for c in f"{dob.year:04d}{dob.month:02d}{dob.day:02d}")


def normalise_name(name: str) -> str:
    """Uppercase A-Z only. Spaces, hyphens and apostrophes carry no value, so
    they drop out; anything else is invalid input (§22.10).

    §13: the name is PII. It is NEVER placed in the exception message — only a
    redacted token plus the offending character CLASS, which is enough to fix a
    bug and not enough to identify a person.
    """
    text = (name or "").strip()
    if not text:
        raise AstroError(
            ErrorCode.ASTRO_NAME_INVALID,
            message_key="errors.astro.name_invalid",
            detail="empty name",
        )
    letters = []
    for char in text.upper():
        if char in CHALDEAN:
            letters.append(char)
        elif char in " -'.":
            continue
        else:
            raise AstroError(
                ErrorCode.ASTRO_NAME_INVALID,
                message_key="errors.astro.name_invalid",
                detail=f"unsupported character class {_char_class(char)} in name {redact(name)}",
            )
    if not letters:
        raise AstroError(
            ErrorCode.ASTRO_NAME_INVALID,
            message_key="errors.astro.name_invalid",
            detail=f"no Latin letters in name {redact(name)}",
        )
    return "".join(letters)


def _char_class(char: str) -> str:
    """Describe a rejected character without echoing it."""
    if char.isdigit():
        return "digit"
    if char.isspace():
        return "whitespace"
    if not char.isascii():
        return "non-latin-script"
    return "punctuation"


def letter_breakdown(name: str, system: NumerologySystem) -> tuple[tuple[str, int], ...]:
    """Per-letter values, in order — the audit trail behind the sum."""
    table = _TABLES[system]
    return tuple((letter, table[letter]) for letter in normalise_name(name))  # type: ignore[index]


def name_number(
    name: str, system: NumerologySystem, policy: MasterNumberPolicy
) -> tuple[int, int, tuple[int, ...]]:
    """Return (reduced value, compound total, reduction trail).

    The compound total is kept because Chaldean tradition reads compound
    numbers (13, 19, 22…) as meaningful in their own right.
    """
    compound = sum(value for _, value in letter_breakdown(name, system))
    value, trail = reduce_number(compound, policy)
    return value, compound, trail
