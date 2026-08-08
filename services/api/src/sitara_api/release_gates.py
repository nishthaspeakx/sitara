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

#: §32.5's cross-lingual recall gate. The vectors are recorded from the real
#: provider; without them the ≥0.85 claim is unproven and must be reported as
#: such rather than skipped quietly in a green suite.
CROSSLINGUAL_VECTORS = (
    Path(__file__).resolve().parents[2] / "tests" / "memory" / "crosslingual" / "vectors.json"
)

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


def _glossary_review_status() -> str:
    from sitara_api.chat_orchestration.config import glossary_review_status

    return glossary_review_status()


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
            id="memory.crosslingual_recall",
            spec_ref="§32.5",
            blocks=Stage.CLOSED_BETA,
            status=(
                "reviewed"
                if CROSSLINGUAL_VECTORS.exists()
                else "awaiting recorded provider vectors"
            ),
            detail=(
                "§32.5 claims cross-lingual recall ≥0.85 on embed-multilingual-v3. Only real "
                "vectors can support that; the 50-pair starter set and harness exist, and the "
                "gate stays open until vectors.json is recorded with a Cohere key."
            ),
        ),
        Gate(
            id="chat.numeric_mismatch_attribution",
            spec_ref="§5.3 step 9",
            blocks=Stage.CLOSED_BETA,
            status="open — cause not yet demonstrated",
            detail=(
                "Two clock values were rejected as numeric mismatches in the M5 hi-Latn "
                "reproduction ('12:53', '12:26 pm') on sentences that DID cite a fact. Not yet "
                "shown whether the model quoted a time from a fact other than the one it cited "
                "(validator correct) or the local-clock rendering missed (validator wrong). "
                "Deliberately unpatched: fixing the wrong one would either mask a real "
                "fabrication or loosen §5.3 on a guess."
            ),
        ),
        Gate(
            id="auth.zone_corroboration_coverage",
            spec_ref="§37.2 / §22.4",
            blocks=Stage.CLOSED_BETA,
            status="open — fails closed outside the mapped calling codes",
            detail=(
                "The §22.4 age gate needs a corroborated timezone and derives it from the "
                "E.164 phone country. A sign-up with no phone (Google) or an unmapped calling "
                "code cannot be age-checked and is REFUSED as retryable. Closes when geo-IP "
                "corroboration is wired or the coverage table reaches every market that can "
                "reach the app."
            ),
        ),
        Gate(
            id="i18n.glossary_forbidden_renderings",
            spec_ref="§2.4 / §14",
            blocks=Stage.CLOSED_BETA,
            status=_glossary_review_status(),
            detail=(
                "§2.4 keeps the glossary terms native in all locales. The per-locale lists of "
                "forbidden renderings are what enforce it; they are drafts until the §14 named "
                "native reviewer signs off, same as the safety corpora."
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
