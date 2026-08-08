"""Per-case parity, so pytest reports each case by name.

A pending case skips: its expected values are NEEDS_VERIFICATION placeholders
awaiting the Jyotish lead's sign-off against Jagannatha Hora. The AI never
verifies ephemeris maths (golden-set/cases/README.md). The aggregate ≥99.9%
gate lives in test_parity_gate.py.
"""

import pytest

from sitara_astro.golden.case import CaseStatus, GoldenCase
from sitara_astro.golden.parity import Dimension, compute_case, evaluate_case


@pytest.fixture()
def evaluation(case: GoldenCase):  # noqa: ANN201
    if case.status is not CaseStatus.VERIFIED:
        pytest.skip(f"{case.case_id}: pending Jyotish verification")
    return evaluate_case(case, compute_case(case))


@pytest.mark.parametrize("dimension", list(Dimension))
def test_dimension_within_threshold(evaluation, dimension: Dimension) -> None:  # noqa: ANN001
    failures = [c for c in evaluation.failures if c.dimension is dimension]
    assert not failures, "\n".join(c.describe() for c in failures)


def test_case_has_checks(evaluation) -> None:  # noqa: ANN001
    """A verified case with nothing filled would silently pass every threshold."""
    assert evaluation.total > 0, f"{evaluation.case_id} is verified but has no expected values"
