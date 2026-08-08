"""Parser for the SPEC §6.4 collection table.

The frozen table is the source of truth for the data layer, so rather than
transcribing it into code and hoping the two stay in step, we read it. The
registry declares what we build; `tests/db/test_registry_matches_spec.py` reads
the table with this parser and fails the build when the two disagree.

Only the shape of the table is understood here — no judgement about what any
row *means*. Interpretation lives in registry.py, where it can be cited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[5] / "docs" / "spec" / "SPEC.md"

_TABLE_HEADER = "| Collection | Key fields / embedding strategy |"
_EM_DASH = "—"


@dataclass(frozen=True)
class SpecIndex:
    """One index as the §6.4 "Indexes" cell describes it.

    The cell's grammar, in full:
      `uniq a+b`        unique compound index
      `a+b`             plain compound index
      `uniq (a,b,c)`    same as `uniq a+b+c` — the table uses both spellings
      `x uniq`          trailing form (payments' `provider_event_id uniq`)
      `uniq a+b active` unique, restricted to the rows where b == "active"
      `vector index (…)`  an Atlas Search vector index, not a btree one
    """

    keys: tuple[str, ...]
    unique: bool = False
    partial_value: str | None = None
    vector: bool = False
    raw: str = ""


@dataclass(frozen=True)
class SpecRow:
    """One row of the §6.4 table, parsed but not interpreted."""

    collections: tuple[str, ...]
    fields_cell: str
    indexes_cell: str
    retention_cell: str
    shard_cell: str
    encryption_cell: str

    @property
    def indexes(self) -> tuple[SpecIndex, ...]:
        return parse_index_cell(self.indexes_cell)

    @property
    def mandates_ttl_index(self) -> bool:
        """§6.4 marks three collections `TTL <n> days` and describes every other
        retention in prose ("24mo", "8 years (tax)", "with user"). That
        distinction is load-bearing: a TTL index on `payments` would silently
        delete financial records the table says to keep for eight years, so we
        build a TTL index exactly where the table says TTL and nowhere else.
        """
        return self.retention_cell.strip().lower().startswith("ttl ")

    @property
    def ttl_days(self) -> int | None:
        match = re.match(r"TTL\s+(\d+)\s+days?", self.retention_cell.strip(), re.IGNORECASE)
        return int(match.group(1)) if match else None

    @property
    def shard_key(self) -> str | None:
        cell = self.shard_cell.strip()
        return None if cell.startswith(_EM_DASH) else cell

    @property
    def encrypted(self) -> bool:
        return not self.encryption_cell.strip().startswith(_EM_DASH)


def parse_index_cell(cell: str) -> tuple[SpecIndex, ...]:
    out: list[SpecIndex] = []
    for term in cell.split(";"):
        term = term.strip()
        if not term:
            continue
        if term.lower().startswith("vector index"):
            out.append(SpecIndex(keys=(), vector=True, raw=term))
            continue

        unique = False
        body = term
        if body.lower().startswith("uniq "):
            unique, body = True, body[5:].strip()
        elif body.lower().endswith(" uniq"):
            unique, body = True, body[:-5].strip()

        # `uniq user_id+status active` — the trailing word names the value the
        # partial filter pins the LAST key to.
        partial_value: str | None = None
        parts = body.split()
        if len(parts) == 2:
            body, partial_value = parts[0], parts[1]

        body = body.strip("()")
        keys = tuple(k.strip() for k in re.split(r"[+,]", body) if k.strip())
        out.append(SpecIndex(keys=keys, unique=unique, partial_value=partial_value, raw=term))
    return tuple(out)


def load_spec_rows(path: Path | None = None) -> dict[str, SpecRow]:
    """Return the §6.4 table keyed by collection name.

    A row naming two collections (`feature_flags / experiments`) yields one
    entry per collection, both pointing at the same row.
    """
    text = (path or SPEC_PATH).read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(_TABLE_HEADER))
    except StopIteration:  # pragma: no cover - the spec is frozen; this is a tripwire
        raise RuntimeError(f"§6.4 collection table not found in {path or SPEC_PATH}") from None

    rows: dict[str, SpecRow] = {}
    for line in lines[start + 2 :]:  # skip header + separator
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            continue
        names = tuple(n.strip() for n in cells[0].split("/") if n.strip())
        row = SpecRow(
            collections=names,
            fields_cell=cells[1],
            indexes_cell=cells[2],
            retention_cell=cells[3],
            shard_cell=cells[4],
            encryption_cell=cells[5],
        )
        for name in names:
            rows[name] = row
    return rows
