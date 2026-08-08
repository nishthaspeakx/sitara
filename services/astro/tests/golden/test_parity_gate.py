"""The §5.5 release gate: ≥99.9% parity across VERIFIED golden cases.

Skips while zero cases are verified — the gate arms itself the moment the
Jyotish lead signs off the first case. From then on, this test failing means
the release is blocked (CI golden-set job).
"""

import pytest

from sitara_astro.golden.parity import PARITY_THRESHOLD, build_report

from .conftest import CASES_DIR, VERIFIED_CASES


@pytest.fixture(scope="module")
def report():  # noqa: ANN201
    return build_report(CASES_DIR)


def test_no_case_errored(report) -> None:  # noqa: ANN001
    """Every case must at least compute, verified or not."""
    assert not report.errors, "\n".join(f"{e.case_id}: {e.error}" for e in report.errors)


def test_parity_gate(report) -> None:  # noqa: ANN001
    if not VERIFIED_CASES:
        pytest.skip("no verified cases yet — gate arms when the Jyotish lead signs off")
    assert report.parity is not None, "verified cases carry no filled expectations"
    assert report.meets_gate, (
        f"parity {report.parity:.4%} < {PARITY_THRESHOLD:.1%} over "
        f"{report.checks_total} checks:\n"
        + "\n".join(f"  {c.describe()}" for c in report.failures)
    )


def test_report_is_printable(report) -> None:  # noqa: ANN001
    rendered = report.render()
    assert "GOLDEN-SET PARITY REPORT" in rendered
    assert str(len(VERIFIED_CASES)) in rendered
