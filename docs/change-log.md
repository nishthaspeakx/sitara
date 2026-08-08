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
