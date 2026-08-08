"""Release gates that code cannot close on its own (§31.7, §14, §22.9).

Some things are only finished when a named human says so: a safety corpus
reviewed in its own language, a helpline number verified against the body that
publishes it. Those cannot be a passing test, and a passing test suite that
stays silent about them reads as "ready" when it is not.

So they are declared here as gates with an honest status, and `/shipcheck`
reports them beside lint and tests. A gate closes when the artefact it names
exists and says it was reviewed — never because someone remembered to edit a
checklist.

    uv run python -m sitara_api.release_gates                  # report
    uv run python -m sitara_api.release_gates --stage closed_beta   # exit 1 if open
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

POLICY_DIR = Path(__file__).parent / "chat_orchestration" / "policy"

#: §22.9's region-specific helpline table. Absent by design until a human has
#: verified every number against its publishing body — §5.3's rule against
#: inventing facts binds hardest where the fact is a number in a crisis.
HELPLINE_TABLE = Path(__file__).parent / "chat_orchestration" / "policy" / "helplines.json"

_REVIEWED_PREFIX = "reviewed"


class Stage(StrEnum):
    CLOSED_BETA = "closed_beta"
    PUBLIC_LAUNCH = "public_launch"


@dataclass(frozen=True)
class Gate:
    id: str
    spec_ref: str
    blocks: Stage
    status: str
    detail: str

    @property
    def open(self) -> bool:
        return not self.status.lower().startswith(_REVIEWED_PREFIX)


def _policy_review_status(filename: str) -> str:
    path = POLICY_DIR / filename
    if not path.exists():
        return f"missing — {filename} not found"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("review_status", "missing — no review_status field")


def gates() -> tuple[Gate, ...]:
    """Every human-closed gate, with its status read from the artefact."""
    return (
        Gate(
            id="safety.helpline_table",
            spec_ref="§22.9 / §9 L4",
            blocks=Stage.CLOSED_BETA,
            status=(
                "reviewed" if HELPLINE_TABLE.exists() else "awaiting human-verified numbers"
            ),
            detail=(
                "The L4 auto-response points at the in-app support surface. Region-specific "
                "helpline numbers are facts and are never hardcoded from memory; the table "
                "closes this gate once every number is verified against its publishing body."
            ),
        ),
        Gate(
            id="safety.l1_rule_lexicon",
            spec_ref="§14 language QA / §9",
            blocks=Stage.CLOSED_BETA,
            status=_policy_review_status("safety_rules.json"),
            detail=(
                "Per-locale L1 detection patterns. §14 requires the named native safety "
                "reviewer per locale; a language ships only behind their sign-off."
            ),
        ),
        Gate(
            id="safety.fear_selling_corpus",
            spec_ref="§14 safety QA / §9",
            blocks=Stage.CLOSED_BETA,
            status=_policy_review_status("fear_selling.json"),
            detail=(
                "Per-locale fear-selling lint. §14: fatalism reads differently by language, "
                "so the corpus is reviewed per locale, not translated."
            ),
        ),
    )


def report(stage: Stage | None = None) -> int:
    """Print the gates. Returns the number that are open for `stage`."""
    selected = [gate for gate in gates() if stage is None or gate.blocks is stage]
    width = max(len(gate.id) for gate in selected)
    open_count = 0
    for gate in selected:
        mark = "OPEN " if gate.open else "CLOSED"
        if gate.open:
            open_count += 1
        print(f"[{mark}] {gate.id.ljust(width)}  {gate.spec_ref}  blocks={gate.blocks.value}")
        print(f"{' ' * (width + 10)}{gate.status}")
    return open_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Human-closed release gates")
    parser.add_argument(
        "--stage",
        choices=[stage.value for stage in Stage],
        help="Exit 1 if any gate blocking this stage is still open.",
    )
    args = parser.parse_args(argv)
    stage = Stage(args.stage) if args.stage else None

    open_count = report(stage)
    if stage is None:
        # A plain report never fails a dev build; it exists to be visible.
        print(f"\n{open_count} gate(s) open — reported, not enforced (pass --stage to enforce).")
        return 0
    if open_count:
        print(f"\n{open_count} gate(s) block {stage.value}.")
        return 1
    print(f"\nAll gates for {stage.value} are closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
