"""Numerology golden-case format — same envelope as the astrology suite.

§5.5 requires 100% parity against a 500-case HAND-COMPUTED set (not 99.9%:
numerology is exact arithmetic, so any mismatch is a bug, never a tolerance).
§22.10 extends the set with 200 cross-script cases per launch language, which
is why every case carries both the name as entered and the confirmed Latin form.
"""

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sitara_schemas.facts import MasterNumberPolicy, NameSource

from sitara_astro.golden.case import (
    NEEDS_VERIFICATION,
    CaseSource,
    CaseStatus,
    _dumps,
    _fmt,
)

SCHEMA_VERSION = 1
REPO_NUMEROLOGY_DIR = Path(__file__).resolve().parents[5] / "golden-set" / "numerology"
TARGET_CASE_COUNT = 500  # §5.5


class NumerologyInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name_as_entered: str
    script: str
    # §22.10: what the user confirmed. None means "no name yet" — date-only case.
    confirmed_latin: str | None = None
    name_source: NameSource | None = None
    dob: date
    master_numbers: MasterNumberPolicy = MasterNumberPolicy.REDUCE


class NumerologyExpected(BaseModel):
    """Hand-computed by the reviewer from the published tables."""

    model_config = ConfigDict(validate_assignment=True)

    moolank: int | None = Field(default=None, ge=1, le=33)
    bhagyank: int | None = Field(default=None, ge=1, le=33)
    chaldean_name_number: int | None = Field(default=None, ge=1, le=33)
    chaldean_compound: int | None = Field(default=None, ge=1)
    pythagorean_name_number: int | None = Field(default=None, ge=1, le=33)
    pythagorean_compound: int | None = Field(default=None, ge=1)
    # §22.10 cross-script cases also pin the transliteration itself
    iso15919: str | None = None
    suggested_latin: str | None = None


class NumerologyCase(BaseModel):
    schema_version: int = SCHEMA_VERSION
    case_id: str = Field(pattern=r"^NC-\d{3}$")
    category: str
    status: CaseStatus = CaseStatus.PENDING
    source: CaseSource | None = None
    verified_by: str | None = None
    verified_on: date | None = None
    notes: str = ""
    input: NumerologyInput
    expected: NumerologyExpected


_LEAF_FIELDS = tuple(NumerologyExpected.model_fields)


def _clean(mapping: dict[str, Any] | None) -> dict[str, Any]:
    return {k: (None if v == NEEDS_VERIFICATION else v) for k, v in (mapping or {}).items()}


def parse_case(raw: dict[str, Any]) -> NumerologyCase:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{raw.get('case_id', '?')}: unsupported schema_version")
    return NumerologyCase.model_validate(
        {**raw, "notes": raw.get("notes") or "", "expected": _clean(raw.get("expected"))}
    )


def load_case(path: Path | str) -> NumerologyCase:
    return parse_case(yaml.safe_load(Path(path).read_text()))


def load_all(directory: Path | str = REPO_NUMEROLOGY_DIR) -> list[NumerologyCase]:
    paths = sorted(Path(directory).glob("NC-*.yaml"))
    if not paths:
        raise FileNotFoundError(f"no numerology cases in {directory}")
    return [load_case(p) for p in paths]


def dump_case(case: NumerologyCase) -> str:
    expected = "\n".join(
        f"  {field}: {_fmt(getattr(case.expected, field))}" for field in _LEAF_FIELDS
    )
    inp = case.input
    return f"""schema_version: {case.schema_version}
case_id: {case.case_id}
category: {case.category}
status: {case.status.value}          # ONLY `golden verify` (a named human) may set this
source: {_fmt(case.source) if case.source else "null"}
verified_by: {_fmt(case.verified_by) if case.verified_by else "null"}
verified_on: {_fmt(case.verified_on) if case.verified_on else "null"}
notes: {_dumps(case.notes)}
input:
  name_as_entered: {_dumps(inp.name_as_entered)}
  script: {inp.script}
  confirmed_latin: {_dumps(inp.confirmed_latin) if inp.confirmed_latin else "null"}
  name_source: {inp.name_source.value if inp.name_source else "null"}
  dob: {_fmt(inp.dob)}
  master_numbers: {inp.master_numbers.value}
expected:                # hand-computed from the published tables — §5.5 needs 100%
{expected}
"""


def save_case(case: NumerologyCase, path: Path | str) -> None:
    Path(path).write_text(dump_case(case))


def set_field(case: NumerologyCase, dotted: str, raw_value: str) -> NumerologyCase:
    if dotted not in _LEAF_FIELDS:
        raise KeyError(f"unknown field path: {dotted!r}")
    updated = case.model_copy(deep=True)
    text = (raw_value or "").strip()
    setattr(updated.expected, dotted, None if text in ("", NEEDS_VERIFICATION) else text)
    return updated


def missing_required(case: NumerologyCase) -> list[str]:
    """Moolank and bhagyank are always required; name numbers only when the case
    carries a confirmed name."""
    required = ["moolank", "bhagyank"]
    if case.input.confirmed_latin:
        required += ["chaldean_name_number", "pythagorean_name_number"]
    return [f for f in required if getattr(case.expected, f) is None]
