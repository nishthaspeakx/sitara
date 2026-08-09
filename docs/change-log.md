# Implementation change log

Decisions that change how a validator, job or contract **behaves**, without
changing a decision the specification makes.

This is deliberately **not** §31.3 change control. That door is for the spec,
and its entries are spec sections (§34 = 001 … §37 = 004). An entry here says:
the spec's rule is unchanged, and here is a decision we made about how to
enforce it, what it now permits or refuses, and what risk that leaves. If an
entry ever needs to change what the spec *says*, it belongs in §31.3 instead
and this log should say so.

Each entry: what changed · why · what it now permits · what it now refuses ·
residual risk · who approved it.

---

## CL-001 — the grounding validator's citation exemption
**Date:** 8 August 2026 · **Approved:** Founder (Nishtha Agarwal) ·
**Raised by:** M5 acceptance testing · **Touches:** §5.3 step 9, §9, §2.3, §0.7

**What changed.** `chat_orchestration/grounding.py` no longer treats every
sentence containing an astrology term as a claim requiring a `fact_id`. A
sentence carrying a strong term is exempt from citation only when ALL FIVE
hold: no number, no clock value, no second-person reference, no temporal
deixis, and no celestial entity asserted to be doing or being anything.

**Why.** §5.3 requires that "every claim cites a fact-ID". The implementation
read "claim" as "sentence mentioning a term", which is broader, and the gap
between the two caught sentences the spec *requires Tara to say*:

* §2.3: "Gloss a term in one short clause the first time it appears." The
  gloss defines a category and asserts nothing about the person.
* §0.7: she "owns limits without apology-spirals". The sentence that exposed
  this was *"it's all late-night windows rather than daytime ones — so this is
  a partial picture, not the full day's choghadiya"* — honesty about coverage,
  rejected as a fabrication.

Both failed on every attempt, so the turn spent its one §9 regeneration and
served the fallback line. Two prompt revisions could not fix it: the model was
behaving correctly and the validator was wrong about what a claim is.

**What it now permits (uncited).** Category glosses and coverage statements —
"Choghadiya are the traditional slots that mark auspicious and inauspicious
windows"; "I only have the night windows, not the full day".

**What it still refuses.** Everything with a number, a clock, "your", "today",
or a named body in an assertion. Specifically including the case this rule was
stress-tested against: **"Venus is retrograde"** — no number, no clock, no
deixis, no second person — is still a claim, because Venus is asserted to be
something. Held in Devanagari and Hinglish too.

**Residual risk.** Listed in full in the module docstring. In short: bare
tradition statements pass uncited; subjecthood is approximated by
co-occurrence rather than parsed; the marker lists are per-locale data
reviewed with the §14 language pass; sentence splitting is punctuation-based.

**Found while implementing.** Two matching defects, both fixed with
regression tests, both of which had made the rule weaker than it read:

1. `\b` cannot delimit Devanagari. Vowel signs and the virama are combining
   marks Python excludes from `\w`, so `\bवक्री\b` never matched — **every
   Devanagari term in the claim lexicons was inert.**
2. The danda `।` (U+0964) sits inside the Devanagari block, so a lookaround
   built on the whole block treated it as word-internal and no term at the end
   of a Devanagari sentence matched. The class now stops at U+0963 and resumes
   at U+0966.

Both made the validator stricter, not looser.

---

## CL-002 — absence-of-fact exemption, and calendar dates
**Date:** 9 August 2026 · **Approved:** Founder · **Raised by:** the 20-turn
hi/hi-Latn reproduction · **Touches:** §5.3 step 9, §2.4

**What changed.** Two narrow additions to CL-001's claim test.

*(a) Absence.* A sentence stating that a fact is MISSING is not a claim.
§5.3 forbids inventing facts, not admitting to lacking one, and no rewrite can
make such a sentence pass — there is nothing to cite. Guarded on two sides: a
celestial-entity state assertion, or a number beside a strong term, in the same
sentence keeps the citation duty. `"I don't have rahu kaal, but Saturn is in
your 10th house"` is still rejected, in all three locales.

*(b) Dates.* A number inside a full date expression ("9 August 2026",
`2026-08-09`, "9 अगस्त 2026") no longer triggers the weak-term+number rule. A
bare ordinal never counts as a date, so "4th house" and "चौथे भाव" still fire.

**Why.** 22 of 24 grounding rejections in the hi/hi-Latn reproduction were
Tara saying she lacked a fact. Hindi and Hinglish place "अभी"/"abhi" in those
sentences far more naturally than English does, so CL-001's deixis clause
caught them and the turn burned its regeneration and served the fallback line.

**Also.** "Rahu kaal" is now separated from the graha `rahu` — it names a
window, not the node — so a bare statement about that window is exempt while
one about the node is not.

---

## CL-003 — one script-aware boundary helper (`sitara_api.text`)
**Date:** 9 August 2026 · **Approved:** Founder (sweep requested) ·
**Touches:** §9 L1 lexicon, §9 post-check, §2.3, §2.4

**What changed.** Every hand-rolled word boundary moved to `sitara_api.text`.
`\b` cannot delimit Devanagari — vowel signs and the virama are combining
marks Python excludes from `\w` — and the danda `।` sits inside the Devanagari
block, so a block-wide lookaround treats it as word-internal and no term at a
sentence's end matches.

**What the sweep found.** `test_script_boundaries.py` now asserts that **no
pattern in either safety corpus is inert** (120 patterns, parametrised
individually). Result: the L1 lexicon and the fear-selling corpus were NOT
affected — their Devanagari entries are bare substrings, not `\b`-delimited.
The defect was confined to the claim lexicons, the glossary/honorific lint and
language detection, all now fixed and covered. Two collateral fixes:
`detect_script` no longer reads a stray danda as Devanagari, and `tokenize`
no longer produces "हैं।" as one token.

The sweep guards itself: a test asserts `is_inert` still flags
`\bवक्री\b`, so it cannot pass vacuously if the detector rots.

---

## CL-004 — per-turn output cap raised to 2048
**Date:** 9 August 2026 · **Approved:** Founder · **Touches:** §9 token budgets

Hinglish replies were hitting §9's per-turn hard cap and being cut off
mid-sentence, spending the one corrective regeneration on brevity. §9 fixes
that a cap exists, not its value. **Open and tracked:** two clock values were
rejected as numeric mismatches on sentences that DID cite a fact; whether that
is per-sentence misattribution (validator right) or a rendering gap (validator
wrong) is not yet demonstrated, so it is deliberately unpatched and carried in
`release_gates` as `chat.numeric_mismatch_attribution`.

---

## CL-006 — review findings from the CL-002..005 diff
**Date:** 9 August 2026 · **Approved:** Founder · **Raised by:** `/review`

Eight findings; all actioned. The first two were introduced by CL-001..005
and are the reason this log exists separately from the spec.

1. **Age-gate bypass (blocker).** The client-declared timezone was used
   unverified, so `Pacific/Kiritimati` bought a day. Now corroborated —
   see §37.2, restated. Fixing a false-negative had opened a false-positive,
   which is the worse direction for a hard gate.
2. **Exact age in a plaintext seven-year log.** Removed; the row records the
   outcome, the zone set and its provenance. `db.redact_age_targets` rewrites
   rows already written — it does not delete them, because destroying an
   append-only audit record to fix its contents is a worse violation than the
   one being fixed.
3. **Six dangling citations** to a §36 subsection that does not exist. Fixed to §37.2, and
   `tests/spec/test_citations_resolve.py` now fails on any citation that does
   not resolve. It immediately found six MORE, pre-existing: §10's journey
   stages are cited with a HYPHEN in the spec (`10-6`), and four files wrote
   the dotted form, which resolves to nothing.
4. **`audit_logs` is now STRICT** (`additionalProperties: false`) with its
   full field set declared. An undeclared field on an append-only legal record
   is a field nobody reviewed for §13 content — which is exactly how `age=`
   got there.
5. **Glossary enforcement replaced.** The old check compared CASE, which never
   enforced §2.4's "kept native" rule and did flag a sentence-initial
   "Nakshatra". Each term now carries per-locale forbidden renderings
   ("almanac", "birth star"), drafts pending the §14 reviewer.
6. **"No audit, no decision"** is now the documented policy: the write
   precedes the outcome, and a failed write returns retryable
   SYS_UNAVAILABLE rather than an unaudited admission OR refusal.
7. **`is_inert` treats an empty probe as a finding**, not a pass — a sweep
   that waves through what it cannot parse is not a sweep.
8. Dead branch removed.

---

## CL-007 — phone-first sign-up
**Date:** 9 August 2026 · **Approved:** Founder · **Touches:** §37.3, §22.5, §33.2

Recorded in the spec as **§37.3**, not as a new subsection of §36: entry 003
is frozen at three items, while §37 is the live entry for v3.7. A citation to
a §36 subsection that does not exist is exactly what
`tests/spec/test_citations_resolve.py` now fails on — including in this file.

A Sitara account is created by phone verification only; Google and Apple link
to an existing account through §22.5. This closes the POLICY half of
`auth.zone_corroboration_coverage` — the §22.4 gate always has a phone country
now, with no geo-IP dependency — and leaves the DATA half open: an unmapped
calling code still fails closed.

The refusal is `AUTH_FORBIDDEN` with an in-locale next step, deliberately
distinct from the retryable `SYS_UNAVAILABLE` an unresolvable timezone
produces. One tells the client to retry; the other tells the person what to
do. Tests cover both, plus the case that must keep working: an existing user
signing in with an already-linked Google identity, since the phone check sits
after the identity lookup rather than before it.
