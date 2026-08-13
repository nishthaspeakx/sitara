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


def _brief_copy_review_status() -> str:
    """§7.1's morning-brief copy. The strings live in `packages/i18n/messages`
    where every user-facing string lives; this reads the review status off the
    manifest that describes them."""
    path = Path(__file__).parent / "daily_guidance" / "policy" / "brief_copy.json"
    if not path.exists():
        return "missing — brief_copy.json not found"
    return json.loads(path.read_text(encoding="utf-8")).get(
        "review_status", "missing — no review_status field"
    )


def _policy_review_status(filename: str) -> str:
    path = POLICY_DIR / filename
    if not path.exists():
        return f"missing — {filename} not found"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("review_status", "missing — no review_status field")


def _indic_streaming_stt_status() -> str:
    """Read the gate's answer off the CAPABILITY MATRIX, never off a constant.

    A gate whose status is a literal is a gate that stays red after the thing
    it watches is fixed, and amber-forever gates are how a real blocker gets
    tuned out. This reads `voice.providers.routing`, so the day Sarvam's
    streaming cell goes IMPLEMENTED the gate closes itself.
    """
    from sitara_api.voice.providers.routing import Modality, blocked_locales

    blocked = blocked_locales(Modality.STREAMING, ("en", "hi", "hi-Latn"))
    if not blocked:
        return "reviewed — every launch locale has a streaming recogniser"
    return f"blocked — no streaming STT for {', '.join(blocked)}"


def gates() -> tuple[Gate, ...]:
    """Every human-closed gate, with its status read from the artefact."""
    return (
        Gate(
            id="call.indic_streaming_stt",
            spec_ref="§25.3 / §33.5 / §3.3 (CC-010)",
            blocks=Stage.PUBLIC_LAUNCH,
            status=_indic_streaming_stt_status(),
            detail=(
                "hi/hi-Latn live calls are blocked pending Sarvam realtime STT. Cartesia "
                "Ink's STREAMING endpoint recognises English only (its batch endpoint "
                "carries 49 languages, which is why §25.4's voice notes work in all three "
                "locales). Those calls are therefore EXPLICITLY UNAVAILABLE rather than "
                "routed to an English recogniser: an English model fed Hindi audio does "
                "not fail, it produces fluent nonsense, which then reaches §9 as the "
                "user's question — and every validator downstream gates what Tara SAYS, "
                "so none of them can see it. Closing this needs Sarvam's streaming cell "
                "in `voice.providers.routing.CAPABILITIES` to go IMPLEMENTED with an "
                "adapter behind it; the status above is read from that matrix, so this "
                "gate closes itself and cannot go stale."
            ),
        ),
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
            status="policy resolved (§37.3) — open on calling-code coverage only",
            detail=(
                "RESOLVED: sign-up is phone-first (§37.3), so the §22.4 gate always has a "
                "phone country to corroborate its timezone with and needs no geo-IP "
                "dependency. What remains is DATA: a phone whose calling code is outside "
                "phone_country_zones.json still fails closed and refuses a legitimate user. "
                "Closes when the table covers every market that can reach the app."
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
            id="i18n.brief_templates_and_terms",
            spec_ref="§7.1 / §2.4 / §14",
            blocks=Stage.CLOSED_BETA,
            status=_brief_copy_review_status(),
            detail=(
                "The §34.3 module templates and the closed-set term names (nakshatra, "
                "graha, day-timing, choghadiya, paksha) that the morning brief "
                "interpolates. These are the words Tara says every morning in three "
                "locales, and §2.4 forbids a silent English fallback — a term missing "
                "in-locale DROPS its card rather than rendering English, so an "
                "unreviewed catalog shows up as a thinner brief, not as an error. "
                "Drafts until the §14 named native reviewer signs off, same as the "
                "safety corpora."
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
