"""§22.10 determinism promise, as an assertion rather than prose.

"Chaldean values are defined over the Latin transliteration of the name as
spoken … the confirmed Latin form is stored as the canonical numerology input."

The whole point is that HOW a name was entered cannot change the numbers. Enter
"Lakshmi" in Latin (NC-001) or लक्ष्मी in Devanagari (NC-004) and — once the
user has confirmed the transliteration — every number must be identical. If this
file fails, the transliteration pipeline has broken determinism, which is the
exact failure §5 exists to prevent.
"""

import pytest
from sitara_schemas.facts import MasterNumberPolicy, NumerologySystem

from sitara_astro.golden.numerology_case import REPO_NUMEROLOGY_DIR, load_all
from sitara_astro.numerology.core import bhagyank, moolank, name_number
from sitara_astro.numerology.factbuild import ConfirmedName, numerology_facts
from sitara_astro.numerology.inputs import NumerologyOptions
from sitara_astro.numerology.translit import propose_transliteration

CASES = {c.case_id: c for c in load_all(REPO_NUMEROLOGY_DIR)}
OPTIONS = NumerologyOptions()

# (latin case, devanagari twin) — same person, two entry paths.
TWINS = [("NC-001", "NC-004"), ("NC-002", "NC-005")]


@pytest.mark.parametrize(("latin_id", "native_id"), TWINS)
class TestCrossScriptDeterminism:
    def test_confirmed_forms_are_identical(self, latin_id: str, native_id: str) -> None:
        assert CASES[latin_id].input.confirmed_latin == CASES[native_id].input.confirmed_latin

    def test_transliteration_reproduces_the_latin_case(
        self, latin_id: str, native_id: str
    ) -> None:
        """The proposal we would show the user must equal the Latin twin's name —
        otherwise confirmation is doing the work the engine should have done."""
        native = CASES[native_id]
        proposal = propose_transliteration(native.input.name_as_entered)
        assert proposal.needs_confirmation
        assert proposal.suggested_latin == CASES[latin_id].input.confirmed_latin

    @pytest.mark.parametrize("system", list(NumerologySystem))
    def test_name_numbers_are_identical(
        self, latin_id: str, native_id: str, system: NumerologySystem
    ) -> None:
        policy = MasterNumberPolicy.REDUCE
        latin = name_number(CASES[latin_id].input.confirmed_latin, system, policy)  # type: ignore[arg-type]
        native = name_number(CASES[native_id].input.confirmed_latin, system, policy)  # type: ignore[arg-type]
        assert latin == native, f"{latin_id} vs {native_id} diverged under {system}"

    def test_dob_derived_numbers_are_identical(self, latin_id: str, native_id: str) -> None:
        policy = MasterNumberPolicy.REDUCE
        assert CASES[latin_id].input.dob == CASES[native_id].input.dob
        assert moolank(CASES[latin_id].input.dob, policy) == moolank(
            CASES[native_id].input.dob, policy
        )
        assert bhagyank(CASES[latin_id].input.dob, policy) == bhagyank(
            CASES[native_id].input.dob, policy
        )

    def test_emitted_facts_are_value_identical(self, latin_id: str, native_id: str) -> None:
        """End to end: the FactSnapshots an artefact would embed must agree on
        every value, differing only in the recorded name_source provenance."""
        latin_case, native_case = CASES[latin_id], CASES[native_id]
        latin_name = ConfirmedName.from_confirmation(
            latin_case.input.name_as_entered, confirmed=False
        )
        native_name = ConfirmedName.from_confirmation(
            native_case.input.name_as_entered, confirmed=True
        )
        assert latin_name.latin == native_name.latin

        latin_facts = numerology_facts(
            latin_case.input.dob, latin_name, OPTIONS, subject="s", chart_version=1
        )
        native_facts = numerology_facts(
            native_case.input.dob, native_name, OPTIONS, subject="s", chart_version=1
        )
        assert len(latin_facts) == len(native_facts)
        for a, b in zip(latin_facts, native_facts, strict=True):
            assert a.fact_id == b.fact_id
            assert a.kind is b.kind
            assert a.value == b.value, f"{a.kind} diverged between entry scripts"

    def test_provenance_still_distinguishes_the_entry_path(
        self, latin_id: str, native_id: str
    ) -> None:
        """Identical values, honest provenance: the transliterated one records
        the ISO 15919 scheme, the Latin one records none."""
        latin_name = ConfirmedName.from_confirmation(
            CASES[latin_id].input.name_as_entered, confirmed=False
        )
        native_name = ConfirmedName.from_confirmation(
            CASES[native_id].input.name_as_entered, confirmed=True
        )
        assert not latin_name.was_transliterated
        assert native_name.was_transliterated


class TestUserEditBreaksTheTwinDeliberately:
    def test_edited_spelling_must_differ_from_the_proposal(self) -> None:
        """NC-010 is the counter-case: the §22.10 edit affordance is
        authoritative, so "Laxmi" must NOT equal "Lakshmi"."""
        edited, proposed = CASES["NC-010"], CASES["NC-004"]
        assert edited.input.name_as_entered == proposed.input.name_as_entered
        assert edited.input.confirmed_latin != proposed.input.confirmed_latin
        policy = MasterNumberPolicy.REDUCE
        assert name_number(
            edited.input.confirmed_latin, NumerologySystem.CHALDEAN, policy  # type: ignore[arg-type]
        ) != name_number(
            proposed.input.confirmed_latin, NumerologySystem.CHALDEAN, policy  # type: ignore[arg-type]
        )
