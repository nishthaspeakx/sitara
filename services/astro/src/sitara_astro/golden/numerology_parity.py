"""Numerology parity — §5.5 demands 100% against the hand-computed set.

Every numerology check is categorical (exact integers and exact strings), so
the gate is 1.0, not the astrology suite's 0.999: a numerology mismatch is
arithmetic that disagrees, never a tolerance to absorb.
"""

from dataclasses import dataclass
from pathlib import Path

from sitara_schemas.facts import NumerologySystem

from sitara_astro.golden.case import CaseStatus
from sitara_astro.golden.numerology_case import (
    REPO_NUMEROLOGY_DIR,
    TARGET_CASE_COUNT,
    NumerologyCase,
    load_all,
)
from sitara_astro.golden.parity import Check, Dimension
from sitara_astro.numerology.core import bhagyank, moolank, name_number
from sitara_astro.numerology.translit import propose_transliteration, to_iso15919

NUMEROLOGY_PARITY_THRESHOLD = 1.0  # §5.5: 100%, not 99.9%


def _check(case_id: str, field: str, expected: object, actual: object) -> Check:
    return Check(
        case_id=case_id,
        dimension=Dimension.CATEGORICAL,
        field=field,
        expected=str(expected),
        actual=str(actual),
        delta=None,
        tolerance=0.0,
        unit="exact",
        passed=str(expected) == str(actual),
    )


def evaluate_case(case: NumerologyCase) -> list[Check]:
    """Compare filled expectations against the engine. Unfilled fields are not
    failures — they are work the reviewer has not done yet."""
    checks: list[Check] = []
    policy = case.input.master_numbers
    expected = case.expected

    if expected.moolank is not None:
        checks.append(
            _check(
                case.case_id, "moolank", expected.moolank, moolank(case.input.dob, policy)[0]
            )
        )
    if expected.bhagyank is not None:
        checks.append(
            _check(
                case.case_id, "bhagyank", expected.bhagyank, bhagyank(case.input.dob, policy)[0]
            )
        )

    latin = case.input.confirmed_latin
    if latin:
        for system, value_field, compound_field in (
            (NumerologySystem.CHALDEAN, "chaldean_name_number", "chaldean_compound"),
            (NumerologySystem.PYTHAGOREAN, "pythagorean_name_number", "pythagorean_compound"),
        ):
            value, compound, _ = name_number(latin, system, policy)
            if getattr(expected, value_field) is not None:
                checks.append(
                    _check(case.case_id, value_field, getattr(expected, value_field), value)
                )
            if getattr(expected, compound_field) is not None:
                checks.append(
                    _check(
                        case.case_id,
                        compound_field,
                        getattr(expected, compound_field),
                        compound,
                    )
                )

    # §22.10 cross-script cases also pin the transliteration itself
    if expected.iso15919 is not None:
        checks.append(
            _check(
                case.case_id,
                "iso15919",
                expected.iso15919,
                to_iso15919(case.input.name_as_entered),
            )
        )
    if expected.suggested_latin is not None:
        checks.append(
            _check(
                case.case_id,
                "suggested_latin",
                expected.suggested_latin,
                propose_transliteration(case.input.name_as_entered).suggested_latin,
            )
        )
    return checks


@dataclass(frozen=True)
class NumerologyEvaluation:
    case_id: str
    status: CaseStatus
    checks: list[Check]
    error: str | None = None

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


@dataclass(frozen=True)
class NumerologyReport:
    evaluations: list[NumerologyEvaluation]

    @property
    def verified(self) -> list[NumerologyEvaluation]:
        return [e for e in self.evaluations if e.status is CaseStatus.VERIFIED]

    @property
    def pending(self) -> list[NumerologyEvaluation]:
        return [e for e in self.evaluations if e.status is CaseStatus.PENDING]

    @property
    def checks_total(self) -> int:
        return sum(e.total for e in self.verified)

    @property
    def checks_passed(self) -> int:
        return sum(e.passed for e in self.verified)

    @property
    def parity(self) -> float | None:
        return self.checks_passed / self.checks_total if self.checks_total else None

    @property
    def failures(self) -> list[Check]:
        return [c for e in self.verified for c in e.failures]

    @property
    def errors(self) -> list[NumerologyEvaluation]:
        return [e for e in self.evaluations if e.error]

    @property
    def meets_gate(self) -> bool:
        if self.errors:
            return False
        return self.parity is None or self.parity >= NUMEROLOGY_PARITY_THRESHOLD

    def render(self) -> str:
        lines = [
            "=" * 72,
            "NUMEROLOGY PARITY REPORT (SPEC §5.5 — Chaldean primary)",
            "=" * 72,
            f"cases: {len(self.evaluations)}/{TARGET_CASE_COUNT} target  "
            f"verified: {len(self.verified)}  pending: {len(self.pending)}",
            "",
            "Threshold  100% exact vs the hand-computed set (no tolerance: it is arithmetic)",
            "",
            f"verified checks: {self.checks_passed}/{self.checks_total}",
        ]
        if self.parity is None:
            lines.append(
                "PARITY: n/a — no verified expectations yet. The gate arms on the "
                "reviewer's first sign-off."
            )
        else:
            verdict = "PASS" if self.meets_gate else "FAIL"
            gate = f"{NUMEROLOGY_PARITY_THRESHOLD:.0%}"
            lines.append(f"PARITY: {self.parity:.4%}  (gate = {gate})  → {verdict}")
        if self.failures:
            lines += ["", f"FAILURES ({len(self.failures)}):"]
            lines += [f"  ✗ {c.describe()}" for c in self.failures[:40]]
        if self.pending:
            lines += [
                "",
                f"PENDING ({len(self.pending)} cases, not gated) — "
                f"{TARGET_CASE_COUNT - len(self.evaluations)} more cases to author for §5.5.",
            ]
        if self.errors:
            lines += ["", f"ERRORS ({len(self.errors)}):"]
            lines += [f"  ! {e.case_id}: {e.error}" for e in self.errors]
        lines.append("=" * 72)
        return "\n".join(lines)


def build_report(cases_dir: Path | str = REPO_NUMEROLOGY_DIR) -> NumerologyReport:
    evaluations: list[NumerologyEvaluation] = []
    for case in load_all(cases_dir):
        try:
            evaluations.append(
                NumerologyEvaluation(case.case_id, case.status, evaluate_case(case))
            )
        except Exception as exc:
            evaluations.append(
                NumerologyEvaluation(
                    case.case_id, case.status, [], error=f"{type(exc).__name__}: {exc}"
                )
            )
    return NumerologyReport(evaluations=evaluations)
