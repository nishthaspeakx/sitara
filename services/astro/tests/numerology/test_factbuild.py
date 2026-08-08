"""Numerology FactSnapshots + the §22.10 confirmation contract at the fact layer.

The binding rule: a name number may ONLY be computed from a Latin string the
user has confirmed. An unconfirmed non-Latin name raises the §34.4 envelope
code ASTRO_NAME_UNCONFIRMED rather than guessing a transliteration.
"""

from datetime import date

import pytest
from sitara_schemas import ErrorCode
from sitara_schemas.facts import (
    FACT_ID_PATTERN,
    BhagyankValue,
    FactKind,
    MasterNumberPolicy,
    MoolankValue,
    NameNumberValue,
    NameSource,
    NumerologySystem,
)

from sitara_astro.errors import AstroError
from sitara_astro.numerology.factbuild import ConfirmedName, numerology_facts
from sitara_astro.numerology.inputs import NumerologyOptions

DOB = date(1990, 5, 15)
CONFIRMED = ConfirmedName(latin="Lakshmi", source=NameSource.CONFIRMED_TRANSLITERATION,
                          original="लक्ष्मी")
OPTIONS = NumerologyOptions()


def build(name: ConfirmedName | None = CONFIRMED, options: NumerologyOptions = OPTIONS):  # noqa: ANN201
    return numerology_facts(DOB, name, options, subject="user123", chart_version=1)


class TestFactShape:
    def test_emits_moolank_bhagyank_and_both_name_systems(self) -> None:
        facts = build()
        assert [f.kind for f in facts].count(FactKind.NUMEROLOGY_MOOLANK) == 1
        assert [f.kind for f in facts].count(FactKind.NUMEROLOGY_BHAGYANK) == 1
        names = [f for f in facts if f.kind is FactKind.NUMEROLOGY_NAME_NUMBER]
        assert len(names) == 2
        systems = {f.value.system for f in names}  # type: ignore[union-attr]
        assert systems == set(NumerologySystem)

    def test_fact_ids_follow_the_grammar(self) -> None:
        ids = {f.fact_id for f in build()}
        for fact_id in ids:
            assert FACT_ID_PATTERN.match(fact_id), fact_id
        assert "fact:numerology.moolank/profile/user123@v1" in ids
        assert "fact:numerology.bhagyank/profile/user123@v1" in ids
        assert "fact:numerology.name_number.chaldean/profile/user123@v1" in ids
        assert "fact:numerology.name_number.pythagorean/profile/user123@v1" in ids

    def test_values_are_hand_checkable(self) -> None:
        facts = {f.kind: f.value for f in build() if f.kind is not FactKind.NUMEROLOGY_NAME_NUMBER}
        moolank = facts[FactKind.NUMEROLOGY_MOOLANK]
        bhagyank = facts[FactKind.NUMEROLOGY_BHAGYANK]
        assert isinstance(moolank, MoolankValue) and isinstance(bhagyank, BhagyankValue)
        assert moolank.birth_day == 15
        assert moolank.value == 6  # 1+5
        assert bhagyank.digits == (1, 9, 9, 0, 0, 5, 1, 5)
        assert bhagyank.value == 3  # 30 → 3

    def test_name_fact_carries_the_audit_trail(self) -> None:
        chaldean = next(
            f for f in build()
            if f.kind is FactKind.NUMEROLOGY_NAME_NUMBER
            and f.value.system is NumerologySystem.CHALDEAN  # type: ignore[union-attr]
        )
        value = chaldean.value
        assert isinstance(value, NameNumberValue)
        assert value.latin_name == "Lakshmi"
        assert value.compound_value == 19
        assert sum(v for _, v in value.letter_values) == value.compound_value

    def test_facts_are_permanent_until_profile_edit(self) -> None:
        """§7.3 cache key `numerology:{subject}:{system}` is permanent until the
        profile changes — expressed here as an open-ended validity window."""
        for fact in build():
            assert fact.valid_to is None

    def test_profile_edit_is_a_version_bump(self) -> None:
        v1 = {f.fact_id for f in numerology_facts(DOB, CONFIRMED, OPTIONS,
                                                  subject="user123", chart_version=1)}
        v2 = {f.fact_id for f in numerology_facts(DOB, CONFIRMED, OPTIONS,
                                                  subject="user123", chart_version=2)}
        assert v1.isdisjoint(v2)


class TestProvenance:
    def test_method_records_system_policy_and_name_source(self) -> None:
        for fact in build():
            assert fact.method.master_numbers is MasterNumberPolicy.REDUCE
            assert fact.method.ayanamsa is None  # numerology has no ayanamsa
            assert fact.method.ephe_source is None  # …and no ephemeris
            if fact.kind is FactKind.NUMEROLOGY_NAME_NUMBER:
                assert fact.method.name_source is NameSource.CONFIRMED_TRANSLITERATION
                assert fact.method.transliteration_scheme == "iso15919"
                assert fact.method.numerology_system is not None

    def test_latin_entry_records_no_transliteration_scheme(self) -> None:
        latin = ConfirmedName(latin="Priya", source=NameSource.LATIN_AS_ENTERED, original="Priya")
        name_fact = next(
            f for f in build(latin) if f.kind is FactKind.NUMEROLOGY_NAME_NUMBER
        )
        assert name_fact.method.name_source is NameSource.LATIN_AS_ENTERED
        assert name_fact.method.transliteration_scheme is None

    def test_precision_is_exact(self) -> None:
        for fact in build():
            assert fact.precision.unit == "exact"
            assert fact.precision.tolerance == 0


class TestConfirmationContract:
    def test_date_only_facts_when_no_name_supplied(self) -> None:
        """Moolank/bhagyank need only the date — the reveal moment (§10-9) still
        works before the name step."""
        facts = build(None)
        assert {f.kind for f in facts} == {
            FactKind.NUMEROLOGY_MOOLANK,
            FactKind.NUMEROLOGY_BHAGYANK,
        }

    def test_unconfirmed_name_is_refused(self) -> None:
        with pytest.raises(AstroError) as exc_info:
            ConfirmedName.from_confirmation("लक्ष्मी", confirmed=False)
        assert exc_info.value.code is ErrorCode.ASTRO_NAME_UNCONFIRMED

    def test_non_latin_confirmed_value_is_refused(self) -> None:
        """Confirming must yield a LATIN form — a rubber-stamped Devanagari
        string is not a numerology input."""
        with pytest.raises(AstroError) as exc_info:
            ConfirmedName(latin="लक्ष्मी", source=NameSource.USER_EDITED, original="लक्ष्मी")
        assert exc_info.value.code is ErrorCode.ASTRO_NAME_UNCONFIRMED

    def test_user_edit_overrides_the_proposal(self) -> None:
        """The §22.10 edit affordance: whatever the user settles on is canonical."""
        edited = ConfirmedName.from_confirmation(
            "लक्ष्मी", confirmed=True, edited_latin="Laxmi"
        )
        assert edited.latin == "Laxmi"
        assert edited.source is NameSource.USER_EDITED
        fact = next(f for f in build(edited) if f.kind is FactKind.NUMEROLOGY_NAME_NUMBER)
        assert fact.value.latin_name == "Laxmi"  # type: ignore[union-attr]

    def test_accepting_the_proposal_records_the_transliteration_source(self) -> None:
        accepted = ConfirmedName.from_confirmation("लक्ष्मी", confirmed=True)
        assert accepted.latin == "Lakshmi"
        assert accepted.source is NameSource.CONFIRMED_TRANSLITERATION

    def test_latin_input_needs_no_confirmation_step(self) -> None:
        name = ConfirmedName.from_confirmation("Priya", confirmed=False)
        assert name.source is NameSource.LATIN_AS_ENTERED
        assert name.latin == "Priya"
