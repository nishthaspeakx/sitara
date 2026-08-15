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
    #: §7's Stage-2 scale band. A gate here is a real ceiling that is NOT a
    #: launch blocker — the distinction matters, because filing a scale
    #: ceiling under `closed_beta` is how a genuine blocker gets tuned out by
    #: the people reading this list every week.
    SCALE = "scale"


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


def _atlas_search_status() -> str:
    """Read from the code rather than a constant.

    The gate closes when a second backend exists, which is exactly what
    `test_search_provenance.py` asserts does not. Reading it here means the
    gate cannot go stale in either direction.
    """
    from sitara_api.journal import search as journal_search

    backends = [
        name
        for name in dir(journal_search)
        if name.endswith("Search") and name != "JournalSearch"
    ]
    if backends == ["ExactTextSearch"]:
        return "keyword search only — no Atlas index (scan-capped, logged)"
    return f"reviewed — backends: {', '.join(sorted(backends))}"


def _live_rails_status() -> str:
    """Read the answer off the PAYMENT CAPABILITY MATRIX, never off a constant.

    Same discipline as `_indic_streaming_stt_status`, and the same reason: a
    gate whose status is a literal stays red after the thing it watches is
    fixed, and an amber-forever gate is how a real blocker gets tuned out. The
    day Razorpay's cell goes IMPLEMENTED, this gate closes itself.
    """
    from sitara_api.payments.providers.routing import unimplemented_rails

    pending = unimplemented_rails()
    if not pending:
        return "reviewed — every billing region has an implemented rail"
    named = ", ".join(f"{provider.value}/{region.value}" for provider, region in pending)
    return f"declared, not implemented — {named}"


def gates() -> tuple[Gate, ...]:
    """Every human-closed gate, with its status read from the artefact."""
    return (
        Gate(
            id="payments.live_rails",
            spec_ref="§30.3 / §22.13 / §22.1",
            blocks=Stage.CLOSED_BETA,
            status=_live_rails_status(),
            detail=(
                "§30.3 specifies Razorpay for India (INR, GST-invoiced) and Stripe India "
                "for the diaspora (USD, zero-rated export under LUT, §22.1). NEITHER is "
                "implemented. The whole §30.3 flow — purchase, the UPI pending hold, "
                "receipts, §22.13's grace and read-only ladder, recovery, cancellation, "
                "refunds, gifting with credit conversion, and billing-region migration — "
                "runs end to end against `payments.providers.simulator`, which moves no "
                "money.\n"
                "\n"
                "This is a REAL gap and not a partial one: no subscription revenue can be "
                "collected until it closes, so it blocks closed beta rather than launch.\n"
                "\n"
                "What is missing is mostly NOT code. Each rail needs an account with KYC "
                "completed for the Indian entity, keys and a webhook secret in AWS Secrets "
                "Manager (§13, never an env file), and a plan/price catalogue matching "
                "`payments.money.PRICES` — a price that lives in two systems is a price "
                "that will differ in one of them. §22.1 puts both rails' KYC, GST "
                "registration and the LUT filing in W2 procurement, owned by legal counsel "
                "and finance. Razorpay additionally needs the UPI Autopay per-transaction "
                "cap checked against prevailing RBI limits (§22.13 states the fallback if "
                "a cap intervenes); Stripe additionally needs SCA/3DS handled, which maps "
                "onto the `pending` state §30.3's UPI hold already uses.\n"
                "\n"
                "The CODE is one matrix cell per rail — DECLARED → IMPLEMENTED in "
                "`payments.providers.routing.CAPABILITIES` — plus an adapter implementing "
                "the five `PaymentProvider` methods, a failure-code mapping onto "
                "`PaymentFailureReason`, and that rail's signature verification. "
                "`payments/service.py` does not change: it has never known which rail "
                "answered. `razorpay.py` and `stripe.py` hold the place and every method "
                "raises, so a caller that constructs one directly fails loudly rather "
                "than quietly succeeding. The status above is READ from the matrix, so "
                "this gate closes itself and cannot go stale."
            ),
        ),
        Gate(
            id="payments.gst_invoice_rate",
            spec_ref="§22.1 / §29.2 (S31 acceptance)",
            blocks=Stage.CLOSED_BETA,
            status="open — no rate stated in the spec; finance owns it (§22.1, W2)",
            detail=(
                "§29.2's S31 acceptance requires the total including tax before the "
                "payment rail, and `PriceCard` will not render without one. That line is "
                "SATISFIED: §22.1 makes international billing a zero-rated export under "
                "LUT (tax is nil, total = price), and the India prices are declared "
                "tax-INCLUSIVE in `payments.money`, which is Indian consumer convention "
                "and needs no rate to display.\n"
                "\n"
                "What is missing is the INVOICE SPLIT. §22.1 says Razorpay bills India "
                "'GST-invoiced', so a compliant invoice must show a net-of-tax line and a "
                "GST line — and no section of the spec states the rate. A plausible 18% "
                "is exactly the kind of number this codebase does not invent (§5.3's rule "
                "about facts, pointed at money), and getting it wrong is a filing error "
                "rather than a display bug. Closes when finance supplies the rate and the "
                "HSN/SAC code, alongside the GST registration §22.1 schedules for W2."
            ),
        ),
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
            id="journal.atlas_search",
            spec_ref="§30.5 / §6.4 (CC-011 §44)",
            blocks=Stage.SCALE,
            status=_atlas_search_status(),
            detail=(
                "§30.5 specifies P0 search as keyword+filters over Journal+thread "
                "\"via Atlas Search\". The CONTRACT is met — every artefact containing "
                "every term, newest first — by `journal.search.ExactTextSearch`, which "
                "scans the user's own rows. What is missing is the INDEX, and that is a "
                "scale property rather than a correctness one, which is why this blocks "
                "`scale` and not `closed_beta`.\n"
                "\n"
                "The ceiling is concrete: the scan is capped at DEFAULT_SCAN_LIMIT rows "
                "per source and LOGS when it truncates, so a heavy journal returns "
                "incomplete results and says so rather than pretending. Fix this before "
                "journals get big, not before they work.\n"
                "\n"
                "Deliberately NOT closed by a capability probe. The memory module asks "
                "the deployment whether it has Atlas Search and picks a backend; doing "
                "the same here would select an UNEXERCISED `$search` path in production "
                "on the first real query, against an index nothing creates — Community "
                "mongo has no `createSearchIndexes`, so it could never have run once "
                "before shipping. `tests/journal/test_search_provenance.py` is the "
                "marker and asserts there is exactly ONE backend; closing this gate "
                "means an Atlas deployment, a search-index spec in `db.registry`, and "
                "the parity test that file already carries."
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
