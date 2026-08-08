"""Redact `age=` targets from `audit_logs` (§13, §37.2).

An earlier build of the §22.4 age gate wrote the applicant's exact age into
`audit_logs.target`. That collection carries no CSFLE marks in §6.4 and keeps
rows for seven years, so a birth-detail derivative sat in the clear in an
append-only legal log — §13 puts birth details under field-level encryption
with "never in logs".

This rewrites those targets in place to the outcome the row was recording,
which is what §37.2 says the row should have held. It does NOT delete rows:
§6.4 marks the collection append-only, and destroying an audit record to fix
its contents would be a worse violation than the one being fixed. The row
survives, its provenance survives, the derived attribute does not.

    uv run python -m sitara_api.db.redact_age_targets --dry-run
    uv run python -m sitara_api.db.redact_age_targets
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

#: `age=17;min=18` → the outcome it implied. The threshold is re-read from the
#: row rather than assumed, in case it ever moves.
_AGE_TARGET = re.compile(r"^age=(\d+);min=(\d+)$")


def redacted_target(target: str) -> str | None:
    """The replacement for an `age=` target, or None if it is not one."""
    match = _AGE_TARGET.match(target or "")
    if not match:
        return None
    age, minimum = int(match.group(1)), int(match.group(2))
    outcome = "passed" if age >= minimum else "refused"
    return f"outcome={outcome};min={minimum}"


async def run(db, *, dry_run: bool = False) -> tuple[int, int]:  # noqa: ANN001
    """Returns (scanned, redacted)."""
    scanned = redacted = 0
    cursor = db.audit_logs.find({"action": "auth.age_gate"})
    async for row in cursor:
        scanned += 1
        replacement = redacted_target(row.get("target", ""))
        if replacement is None:
            continue
        redacted += 1
        if not dry_run:
            await db.audit_logs.update_one(
                {"_id": row["_id"]},
                {"$set": {"target": replacement, "redacted_reason": "§13:age_derivative"}},
            )
    return scanned, redacted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Redact age= audit targets (§13)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from sitara_api.config import Settings
    from sitara_api.db import make_mongo

    client, db = make_mongo(Settings())
    try:
        scanned, redacted = asyncio.run(run(db, dry_run=args.dry_run))
    finally:
        client.close()
    prefix = "would redact" if args.dry_run else "redacted"
    print(f"audit_logs auth.age_gate rows scanned={scanned} {prefix}={redacted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
