"""Reviewer CLI: batch import from spreadsheet CSV, and sign-off.

The safety property under test: import can never verify a case, and verify
always records a named human (SPEC §5.5 / golden-set README — an LLM never
verifies ephemeris maths).
"""

import shutil
from pathlib import Path

import pytest

from sitara_astro.golden.case import CaseSource, CaseStatus, load_case
from sitara_astro.golden.cli import main
from sitara_astro.golden.numerology_case import load_case as load_numerology_case

REPO_CASES = Path(__file__).resolve().parents[4] / "golden-set" / "cases"


@pytest.fixture()
def cases_dir(tmp_path: Path) -> Path:
    target = tmp_path / "cases"
    target.mkdir()
    for case_id in ("GC-001", "GC-002"):
        shutil.copy(REPO_CASES / f"{case_id}.yaml", target / f"{case_id}.yaml")
    return target


def write_csv(path: Path, rows: list[str]) -> Path:
    path.write_text("case_id,field,value\n" + "\n".join(rows) + "\n")
    return path


def full_expectations(case_id: str) -> list[str]:
    rows = [
        f"{case_id},grahas.{g}.longitude_deg,{10.0 + i}"
        for i, g in enumerate(
            ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu"]
        )
    ]
    rows.append(f"{case_id},lagna.longitude_deg,200.0")
    return rows


class TestImport:
    def test_applies_values(self, cases_dir: Path, tmp_path: Path) -> None:
        csv = write_csv(tmp_path / "b.csv", ["GC-001,grahas.sun.longitude_deg,30.1234"])
        assert main(["import", str(csv), "--cases-dir", str(cases_dir)]) == 0
        assert load_case(cases_dir / "GC-001.yaml").expected.grahas["sun"].longitude_deg == 30.1234

    def test_multiple_cases_and_fields(self, cases_dir: Path, tmp_path: Path) -> None:
        csv = write_csv(
            tmp_path / "b.csv",
            [
                "GC-001,grahas.sun.longitude_deg,30.1",
                "GC-001,grahas.sun.rashi,vrishabha",
                "GC-002,lagna.longitude_deg,111.5",
            ],
        )
        assert main(["import", str(csv), "--cases-dir", str(cases_dir)]) == 0
        one = load_case(cases_dir / "GC-001.yaml")
        assert one.expected.grahas["sun"].rashi == "vrishabha"
        assert load_case(cases_dir / "GC-002.yaml").expected.lagna.longitude_deg == 111.5

    def test_import_never_verifies(self, cases_dir: Path, tmp_path: Path) -> None:
        csv = write_csv(tmp_path / "b.csv", full_expectations("GC-001"))
        main(["import", str(csv), "--cases-dir", str(cases_dir)])
        assert load_case(cases_dir / "GC-001.yaml").status is CaseStatus.PENDING

    def test_dry_run_writes_nothing(self, cases_dir: Path, tmp_path: Path) -> None:
        before = (cases_dir / "GC-001.yaml").read_text()
        csv = write_csv(tmp_path / "b.csv", ["GC-001,grahas.sun.longitude_deg,30.1234"])
        assert main(["import", str(csv), "--cases-dir", str(cases_dir), "--dry-run"]) == 0
        assert (cases_dir / "GC-001.yaml").read_text() == before

    def test_unknown_case_id_aborts_without_writing(self, cases_dir: Path, tmp_path: Path) -> None:
        before = (cases_dir / "GC-001.yaml").read_text()
        csv = write_csv(
            tmp_path / "b.csv",
            ["GC-001,grahas.sun.longitude_deg,30.1", "GC-999,grahas.sun.longitude_deg,1.0"],
        )
        assert main(["import", str(csv), "--cases-dir", str(cases_dir)]) != 0
        assert (cases_dir / "GC-001.yaml").read_text() == before

    def test_bad_field_aborts_atomically(self, cases_dir: Path, tmp_path: Path) -> None:
        before = (cases_dir / "GC-001.yaml").read_text()
        csv = write_csv(
            tmp_path / "b.csv",
            ["GC-001,grahas.sun.longitude_deg,30.1", "GC-001,grahas.sun.nonsense,1.0"],
        )
        assert main(["import", str(csv), "--cases-dir", str(cases_dir)]) != 0
        assert (cases_dir / "GC-001.yaml").read_text() == before

    def test_missing_columns_rejected(self, cases_dir: Path, tmp_path: Path) -> None:
        csv = tmp_path / "b.csv"
        csv.write_text("case,thing\nGC-001,1\n")
        assert main(["import", str(csv), "--cases-dir", str(cases_dir)]) != 0


class TestVerify:
    def _fill(self, cases_dir: Path, tmp_path: Path, case_id: str = "GC-001") -> None:
        csv = write_csv(tmp_path / "full.csv", full_expectations(case_id))
        main(["import", str(csv), "--cases-dir", str(cases_dir)])

    def test_records_reviewer_source_and_date(self, cases_dir: Path, tmp_path: Path) -> None:
        self._fill(cases_dir, tmp_path)
        code = main(
            [
                "verify", "GC-001",
                "--reviewer", "Pandit R. Sharma",
                "--source", "JHora",
                "--cases-dir", str(cases_dir),
            ]
        )
        assert code == 0
        case = load_case(cases_dir / "GC-001.yaml")
        assert case.status is CaseStatus.VERIFIED
        assert case.verified_by == "Pandit R. Sharma"
        assert case.source is CaseSource.JHORA
        assert case.verified_on is not None

    def test_refuses_when_expectations_incomplete(self, cases_dir: Path) -> None:
        code = main(
            ["verify", "GC-001", "--reviewer", "R", "--source", "JHora",
             "--cases-dir", str(cases_dir)]
        )
        assert code != 0
        assert load_case(cases_dir / "GC-001.yaml").status is CaseStatus.PENDING

    def test_reviewer_name_is_mandatory(self, cases_dir: Path, tmp_path: Path) -> None:
        self._fill(cases_dir, tmp_path)
        with pytest.raises(SystemExit):
            main(["verify", "GC-001", "--source", "JHora", "--cases-dir", str(cases_dir)])

    def test_blank_reviewer_rejected(self, cases_dir: Path, tmp_path: Path) -> None:
        self._fill(cases_dir, tmp_path)
        code = main(
            ["verify", "GC-001", "--reviewer", "   ", "--source", "JHora",
             "--cases-dir", str(cases_dir)]
        )
        assert code != 0
        assert load_case(cases_dir / "GC-001.yaml").status is CaseStatus.PENDING

    def test_unknown_case_id(self, cases_dir: Path) -> None:
        code = main(
            ["verify", "GC-999", "--reviewer", "R", "--source", "JHora",
             "--cases-dir", str(cases_dir)]
        )
        assert code != 0


class TestReportCommand:
    def test_report_runs_and_exits_zero_with_no_verified_cases(
        self, cases_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["report", "--cases-dir", str(cases_dir)]) == 0
        assert "PARITY REPORT" in capsys.readouterr().out

    def test_gate_flag_passes_when_nothing_verified_yet(self, cases_dir: Path) -> None:
        assert main(["report", "--cases-dir", str(cases_dir), "--gate"]) == 0

    def test_gate_flag_fails_on_bad_verified_case(
        self, cases_dir: Path, tmp_path: Path
    ) -> None:
        csv = write_csv(tmp_path / "full.csv", full_expectations("GC-001"))
        main(["import", str(csv), "--cases-dir", str(cases_dir)])
        main(["verify", "GC-001", "--reviewer", "R", "--source", "JHora",
              "--cases-dir", str(cases_dir)])
        # the imported longitudes are placeholders, not the engine's values
        assert main(["report", "--cases-dir", str(cases_dir), "--gate"]) != 0


REPO_NUMEROLOGY = Path(__file__).resolve().parents[4] / "golden-set" / "numerology"


@pytest.fixture()
def numerology_dir(tmp_path: Path) -> Path:
    target = tmp_path / "numerology"
    target.mkdir()
    for case_id in ("NC-001", "NC-004", "NC-019"):
        shutil.copy(REPO_NUMEROLOGY / f"{case_id}.yaml", target / f"{case_id}.yaml")
    return target


class TestNumerologyRouting:
    """The CLI routes by case-id prefix — NC- must reach the numerology suite
    with its own field paths, its own required-field rule and its 100% gate."""

    def test_import_applies_numerology_fields(self, numerology_dir: Path, tmp_path: Path) -> None:
        csv = write_csv(
            tmp_path / "n.csv",
            ["NC-001,moolank,6", "NC-001,bhagyank,3", "NC-001,chaldean_compound,19"],
        )
        assert main(["import", str(csv), "--cases-dir", str(numerology_dir)]) == 0
        case = load_numerology_case(numerology_dir / "NC-001.yaml")
        assert case.expected.moolank == 6
        assert case.expected.bhagyank == 3
        assert case.expected.chaldean_compound == 19

    def test_astrology_field_path_rejected_on_a_numerology_case(
        self, numerology_dir: Path, tmp_path: Path
    ) -> None:
        before = (numerology_dir / "NC-001.yaml").read_text()
        csv = write_csv(tmp_path / "n.csv", ["NC-001,grahas.sun.longitude_deg,30.1"])
        assert main(["import", str(csv), "--cases-dir", str(numerology_dir)]) != 0
        assert (numerology_dir / "NC-001.yaml").read_text() == before

    def test_unknown_prefix_is_rejected(self, numerology_dir: Path, tmp_path: Path) -> None:
        csv = write_csv(tmp_path / "n.csv", ["XX-001,moolank,6"])
        assert main(["import", str(csv), "--cases-dir", str(numerology_dir)]) != 0

    def test_verify_requires_name_numbers_only_when_the_case_has_a_name(
        self, numerology_dir: Path, tmp_path: Path
    ) -> None:
        """NC-019 is date-only, so moolank + bhagyank are the whole requirement."""
        csv = write_csv(tmp_path / "n.csv", ["NC-019,moolank,6", "NC-019,bhagyank,3"])
        main(["import", str(csv), "--cases-dir", str(numerology_dir)])
        code = main(
            ["verify", "NC-019", "--reviewer", "Test Reviewer", "--source", "JyotishLead",
             "--cases-dir", str(numerology_dir)]
        )
        assert code == 0
        assert load_numerology_case(numerology_dir / "NC-019.yaml").status is CaseStatus.VERIFIED

    def test_verify_refuses_a_named_case_missing_its_name_numbers(
        self, numerology_dir: Path, tmp_path: Path
    ) -> None:
        csv = write_csv(tmp_path / "n.csv", ["NC-001,moolank,6", "NC-001,bhagyank,3"])
        main(["import", str(csv), "--cases-dir", str(numerology_dir)])
        code = main(
            ["verify", "NC-001", "--reviewer", "R", "--source", "JyotishLead",
             "--cases-dir", str(numerology_dir)]
        )
        assert code != 0
        assert load_numerology_case(numerology_dir / "NC-001.yaml").status is CaseStatus.PENDING

    def test_report_uses_the_numerology_threshold(
        self, numerology_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["report", "--cases-dir", str(numerology_dir)]) == 0
        out = capsys.readouterr().out
        assert "NUMEROLOGY PARITY REPORT" in out
        assert "GOLDEN-SET PARITY REPORT" not in out  # astrology suite not touched

    def test_gate_fails_on_a_wrong_verified_numerology_value(
        self, numerology_dir: Path, tmp_path: Path
    ) -> None:
        # NC-019 is 1990-05-15 → moolank 6; 7 is wrong and 100% allows no slack
        csv = write_csv(tmp_path / "n.csv", ["NC-019,moolank,7", "NC-019,bhagyank,3"])
        main(["import", str(csv), "--cases-dir", str(numerology_dir)])
        main(["verify", "NC-019", "--reviewer", "R", "--source", "JyotishLead",
              "--cases-dir", str(numerology_dir)])
        assert main(["report", "--cases-dir", str(numerology_dir), "--gate"]) != 0

    def test_list_shows_numerology_cases(
        self, numerology_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["list", "--cases-dir", str(numerology_dir)]) == 0
        out = capsys.readouterr().out
        assert "NC-001" in out and "NC-019" in out


class TestBadCasesDir:
    def test_missing_directory_is_a_clean_error(self, tmp_path: Path) -> None:
        assert main(["report", "--cases-dir", str(tmp_path / "nope")]) == 2

    def test_empty_directory_is_a_clean_error(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        assert main(["list", "--cases-dir", str(tmp_path / "empty")]) == 2
