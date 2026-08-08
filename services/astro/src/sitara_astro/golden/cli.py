"""Reviewer CLI:  python -m sitara_astro.golden <command>

    import batch.csv       apply batches of expected values from a spreadsheet
    verify GC-001 …        sign a case off as verified, recording who did it
    report [--gate]        parity report; --gate exits non-zero below threshold
    list                   case inventory with fill state

Three suites share this one CLI, routed by case-id prefix: astrology (GC-, §5.5
≥99.9%), numerology (NC-, §5.5 = 100%, because it is exact arithmetic) and
panchang (PC-, ≥99.9% with the §5.5 ≤2 min boundary tolerance).

Safety property: `import` can only ever write *expected values*. Nothing but
`verify` — which demands a named human and a source — can set a case verified.
"""

import argparse
import csv
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sitara_astro.golden.case import (
    REPO_CASES_DIR,
    CaseSource,
    CaseStatus,
    load_all,
    missing_required,
    save_case,
    set_field,
)
from sitara_astro.golden.numerology_case import REPO_NUMEROLOGY_DIR
from sitara_astro.golden.numerology_case import load_all as load_numerology
from sitara_astro.golden.numerology_case import missing_required as numerology_missing
from sitara_astro.golden.numerology_case import save_case as save_numerology
from sitara_astro.golden.numerology_case import set_field as set_numerology_field
from sitara_astro.golden.numerology_parity import build_report as build_numerology_report
from sitara_astro.golden.panchang_case import REPO_PANCHANG_DIR
from sitara_astro.golden.panchang_case import load_all as load_panchang
from sitara_astro.golden.panchang_case import missing_required as panchang_missing
from sitara_astro.golden.panchang_case import save_case as save_panchang
from sitara_astro.golden.panchang_case import set_field as set_panchang_field
from sitara_astro.golden.panchang_parity import build_report as build_panchang_report
from sitara_astro.golden.parity import build_report as build_astrology_report

REQUIRED_CSV_COLUMNS = {"case_id", "field", "value"}


@dataclass(frozen=True)
class Suite:
    """Both suites share one envelope, one CLI and one sign-off rule; only the
    field paths and the parity threshold differ."""

    name: str
    prefix: str
    directory: Path
    load_all: Callable[..., list[Any]]
    save_case: Callable[..., None]
    set_field: Callable[..., Any]
    missing_required: Callable[..., list[str]]
    build_report: Callable[..., Any]


SUITES: tuple[Suite, ...] = (
    Suite("astrology", "GC-", REPO_CASES_DIR, load_all, save_case, set_field,
          missing_required, build_astrology_report),
    Suite("numerology", "NC-", REPO_NUMEROLOGY_DIR, load_numerology, save_numerology,
          set_numerology_field, numerology_missing, build_numerology_report),
    Suite("panchang", "PC-", REPO_PANCHANG_DIR, load_panchang, save_panchang,
          set_panchang_field, panchang_missing, build_panchang_report),
)


def suite_for(case_id: str) -> Suite:
    for suite in SUITES:
        if case_id.startswith(suite.prefix):
            return suite
    raise KeyError(f"case id {case_id!r} matches no suite (expected GC-…, NC-… or PC-…)")


def targets(args: argparse.Namespace) -> list[tuple[Suite, Path]]:
    """An explicit --cases-dir means "just this directory"; otherwise every
    suite at its repo location."""
    override = getattr(args, "cases_dir", None)
    if not override:
        return [(s, s.directory) for s in SUITES]
    directory = Path(override)
    found = [(s, directory) for s in SUITES if any(directory.glob(f"{s.prefix}*.yaml"))]
    return found or [(SUITES[0], directory)]


def _dir_for(args: argparse.Namespace, suite: Suite) -> Path:
    override = getattr(args, "cases_dir", None)
    return Path(override) if override else suite.directory


def cmd_import(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"error: no such file: {csv_path}", file=sys.stderr)
        return 2
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        if not REQUIRED_CSV_COLUMNS <= columns:
            missing = ", ".join(sorted(REQUIRED_CSV_COLUMNS - columns))
            header = ",".join(sorted(REQUIRED_CSV_COLUMNS))
            print(f"error: CSV is missing required column(s): {missing}", file=sys.stderr)
            print(f"       expected header: {header}", file=sys.stderr)
            return 2
        rows = list(reader)

    loaded: dict[str, dict[str, Any]] = {}
    touched: dict[str, tuple[Suite, Any]] = {}
    applied = 0
    # Apply everything in memory first: one bad row must not leave a half-import.
    for line_no, row in enumerate(rows, start=2):
        case_id = (row["case_id"] or "").strip()
        field = (row["field"] or "").strip()
        value = row["value"] or ""
        if not case_id and not field:
            continue
        try:
            suite = suite_for(case_id)
        except KeyError as exc:
            print(f"error: line {line_no}: {exc.args[0]}", file=sys.stderr)
            return 1
        if suite.name not in loaded:
            loaded[suite.name] = {c.case_id: c for c in suite.load_all(_dir_for(args, suite))}
        current = touched[case_id][1] if case_id in touched else loaded[suite.name].get(case_id)
        if current is None:
            print(f"error: line {line_no}: unknown case_id {case_id!r}", file=sys.stderr)
            return 1
        try:
            touched[case_id] = (suite, suite.set_field(current, field, value))
        except KeyError as exc:
            print(f"error: line {line_no}: {exc.args[0]}", file=sys.stderr)
            return 1
        except (ValidationError, ValueError) as exc:
            print(f"error: line {line_no}: bad value for {field!r}: {exc}", file=sys.stderr)
            return 1
        applied += 1

    if args.dry_run:
        print(f"dry run: {applied} value(s) across {len(touched)} case(s); nothing written")
        return 0

    for case_id, (suite, case) in sorted(touched.items()):
        suite.save_case(case, _dir_for(args, suite) / f"{case_id}.yaml")
    print(f"imported {applied} value(s) into {len(touched)} case(s)")
    for case_id, (suite, case) in sorted(touched.items()):
        remaining = suite.missing_required(case)
        state = "ready to verify" if not remaining else f"{len(remaining)} required field(s) left"
        print(f"  {case_id}: {state}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    reviewer = (args.reviewer or "").strip()
    if not reviewer:
        print("error: --reviewer must name the human who checked this case", file=sys.stderr)
        return 2
    try:
        suite = suite_for(args.case_id)
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 1
    directory = _dir_for(args, suite)
    cases = {c.case_id: c for c in suite.load_all(directory)}
    case = cases.get(args.case_id)
    if case is None:
        print(f"error: unknown case_id {args.case_id!r}", file=sys.stderr)
        return 1
    remaining = suite.missing_required(case)
    if remaining:
        print(
            f"error: {case.case_id} still has {len(remaining)} unfilled required field(s):",
            file=sys.stderr,
        )
        for field in remaining:
            print(f"  - {field}", file=sys.stderr)
        print("import the expected values first, then verify.", file=sys.stderr)
        return 1

    verified = case.model_copy(
        update={
            "status": CaseStatus.VERIFIED,
            "verified_by": reviewer,
            "verified_on": date.today(),
            "source": CaseSource(args.source),
        }
    )
    suite.save_case(verified, directory / f"{case.case_id}.yaml")
    print(f"{case.case_id} verified by {reviewer} ({args.source}) on {verified.verified_on}")
    print("this case now counts toward the release-blocking parity gate (§5.5).")
    return 0


def _resolve(args: argparse.Namespace) -> list[tuple[Suite, Path]] | None:
    """None means "already reported a clean error" — never a traceback."""
    override = getattr(args, "cases_dir", None)
    if override and not Path(override).is_dir():
        print(f"error: no such directory: {override}", file=sys.stderr)
        return None
    found = targets(args)
    for suite, directory in found:
        if not any(Path(directory).glob(f"{suite.prefix}*.yaml")):
            print(
                f"error: no {suite.name} cases ({suite.prefix}*.yaml) in {directory}",
                file=sys.stderr,
            )
            return None
    return found


def cmd_report(args: argparse.Namespace) -> int:
    resolved = _resolve(args)
    if resolved is None:
        return 2
    failed = False
    for suite, directory in resolved:
        report = suite.build_report(directory)
        print(report.render())
        if args.gate and not report.meets_gate:
            failed = True
            print(f"\nGATE FAILED ({suite.name}) — release blocked (§5.5).", file=sys.stderr)
    return 1 if failed else 0


def cmd_list(args: argparse.Namespace) -> int:
    resolved = _resolve(args)
    if resolved is None:
        return 2
    for suite, directory in resolved:
        for case in suite.load_all(directory):
            remaining = len(suite.missing_required(case))
            mark = "✓" if case.status is CaseStatus.VERIFIED else " "
            detail = (
                f"verified by {case.verified_by} ({case.source.value if case.source else '?'})"
                if case.status is CaseStatus.VERIFIED
                else f"{remaining} required field(s) unfilled"
            )
            print(f"{mark} {case.case_id}  {case.category:<20} {case.status.value:<9} {detail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sitara_astro.golden",
        description="Golden-set case management and parity reporting (SPEC §5.5).",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--cases-dir",
        default=None,
        help="operate on this directory only (default: every suite at its repo location)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser(
        "import",
        parents=[common],
        help="apply expected values from a spreadsheet CSV (case_id,field,value)",
    )
    importer.add_argument("csv")
    importer.add_argument("--dry-run", action="store_true", help="validate without writing")
    importer.set_defaults(func=cmd_import)

    verifier = subparsers.add_parser(
        "verify", parents=[common], help="sign a case off as verified"
    )
    verifier.add_argument("case_id")
    verifier.add_argument("--reviewer", required=True, help="name of the human who checked it")
    verifier.add_argument(
        "--source", required=True, choices=[s.value for s in CaseSource], help="value provenance"
    )
    verifier.set_defaults(func=cmd_verify)

    reporter = subparsers.add_parser("report", parents=[common], help="print the parity report")
    reporter.add_argument(
        "--gate", action="store_true", help="exit non-zero if any suite is below its threshold"
    )
    reporter.set_defaults(func=cmd_report)

    lister = subparsers.add_parser(
        "list", parents=[common], help="inventory of cases and fill state"
    )
    lister.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
