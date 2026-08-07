"""Letter-value tables. Published constants — never computed, never guessed."""

from types import MappingProxyType

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Chaldean: values 1-8 only. 9 is held sacred and assigned to no letter — that
# property is asserted in the tests, because losing it silently would change
# every name number in the product.
_CHALDEAN_GROUPS: dict[int, str] = {
    1: "AIJQY",
    2: "BKR",
    3: "CGLS",
    4: "DMT",
    5: "EHNX",
    6: "UVW",
    7: "OZ",
    8: "FP",
}

CHALDEAN: MappingProxyType[str, int] = MappingProxyType(
    {letter: value for value, letters in _CHALDEAN_GROUPS.items() for letter in letters}
)

# Pythagorean: straight A1..Z26 folded mod 9.
PYTHAGOREAN: MappingProxyType[str, int] = MappingProxyType(
    {letter: (index % 9) + 1 for index, letter in enumerate(ALPHABET)}
)

MASTER_NUMBERS: frozenset[int] = frozenset({11, 22, 33})
