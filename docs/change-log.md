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

---

## CL-008 — the morning wave: five decisions §7.1 implies but does not state
**Date:** 9 August 2026 · **Approved:** Founder (Nishtha Agarwal) ·
**Raised by:** M6 implementation (§7.1 pipeline build) ·
**Touches:** §7.1, §7.2, §23.4, §28.2, §32.13, §32.7, diagram 5

Five decisions the §7.1 build had to make. **None changes what the spec says**;
each writes down a reading the spec permits and the implementation had to pick
between. Items 1 and 2 are the ones a reviewer should disagree with first —
they are readings, not deductions, and the alternative reading is coherent.

**1. The lead window is a SCHEDULE, not a filter.** §7.1 says two things: the
tick selects users "whose local brief_time falls 90–30 min ahead", and "waves
spread across the 60-min lead window hashed by user_id". Taken as membership
alone, a 60-minute window sampled every 15 minutes contains each user for FOUR
consecutive ticks, so every user is enqueued four times and §32.13's key throws
three away — correct, and it wastes three quarters of the wave's queue traffic
at exactly the moment §7.1 is trying to smooth. **Final: the hash assigns each
user one stable lead in [30, 90) minutes and they fire at the single tick that
lead lands in.** Membership becomes a consequence rather than a test. The
5,000-user simulation is the evidence: the 07:00 band spreads 24.5/23.4/25.9/
24.8/1.5% across five ticks, every one of the sixty lead slots is occupied, and
no user is selected twice in a day (`simulate` raises if one is).

**2. Dormancy is the RESIDUAL tier, not a second dimension.** §7.1 writes
"paying users > trial > dormant" without saying whether dormancy is crossed
with entitlement. Read as orthogonal ("has not opened the app lately"), a
paying subscriber who takes a fortnight's holiday comes home to no brief,
having paid for one every day of it. **Final: PAYING if they pay, else TRIAL if
inside a trial, else DORMANT.** §7.1's justification for skipping dormant users
is "no waste", and there is none to save on someone who is paying; §28.2's Free
variant already says the residual tier sees generic panchang and locked
personal cards, so there is no personalised brief to pre-generate for them.
Payment-grace and past-due stay PAYING (§22.13, §28.2's grace variant).

**3. §32.13's key carries three components; the unique index carries two.** Not
a contradiction — it is the mechanism §32.7 needs. If locale were part of
uniqueness, a user who switched language at 06:50 would end the morning holding
two briefs for one local date and §32.13's "one brief per user-local calendar
date" would be false. **Final: `(user_id, date)` stays unique and the locale
rides inside the stored key**, so a generator comparing computed key against
stored key learns the row is for the wrong language and §32.7 has something to
act on. The collapse key (§23.4) deliberately omits locale for the same reason
in reverse: a regenerated brief must REPLACE its push, not add a second one.

**4. The brief enforces a citation rule the chat pipeline cannot.**
`GroundingValidator` decides claim-hood from vocabulary, which is the only
signal free-form conversation has — so "A good window opens between 11:48 and
12:36" names no graha, rashi or tradition term and passes uncited. In a
template that is not an edge case, it is every morning. **Final: a module
composed FROM snapshots must come back citing at least one of them, checked
structurally before the vocabulary test runs.** The chat validator is unchanged
and still owns "is this id one we served?".

**5. Where a preference lives.** §6.4 has no `preferences` row and §7.1 needs a
per-user `brief_time`; §23.5's picker, §28.2's density mode and §30.2's
follow-timezone toggle are the same shape. **Final: on `profiles`**, which is
already the 1:1 settings row, with `brief_time` stored as zero-padded local
"HH:MM" so a string range scan on the new index answers the lead-window query
(the padding is load-bearing: unpadded, "7:00" sorts after "10:00" and the wave
silently misses a band). `brief_place` joins them for the §7.2 cache cell.

**Also recorded (no decision required).** `local_instant` returns UTC because
PEP 495 makes an aware datetime that is AMBIGUOUS in its zone compare unequal
to its own instant elsewhere while comparing neither less nor greater —
trichotomy fails, and any `==`, `in`, dict key or sort over such a value is
quietly wrong on fall-back days. Consolidation's dedupe elects one canonical
per CLUSTER rather than per pair: pairwise folding builds chains (A→B→C) in
which a duplicate points at another duplicate. The morning-brief templates and
the closed-set term names ship as drafts carrying
`review_status: "draft — awaiting §14 named native reviewer"`, surfaced as the
`i18n.brief_templates_and_terms` release gate — and §2.4's no-silent-fallback
rule means an unreviewed locale shows up as a THINNER brief (the card is
dropped) rather than as English in a Hindi brief.

**Residual risk.** Chart facts are not wired: the astrology facade still
declines `NATAL_CHART`/`TRANSITS` (M5), so `personal_chart_theme`, `work` and
`relationship` cannot be composed in production today and the brief degrades
through §7.1's stated path. Named rather than stubbed, so the gap is visible in
`BriefFacts.missing` and in the degrade reason rather than hidden behind
plausible-looking data.

---

## CL-009 — the chart tools, and four defects the M6 acceptance found
**Date:** 9 August 2026 · **Approved:** Founder · **Raised by:** M6 acceptance +
`/review` · **Touches:** §5.2 Layer A, §6.4 `charts`, §7.2, §13, §23.4

**What changed.** `NATAL_CHART`/`TRANSITS` no longer decline. A third adapter
over the internal engine (`astrology/chart_adapter.py`, breaker and typed
snapshots like panchang and numerology) sits under `AstrologyFacade`, which is
§13's single door to birth details: it decrypts the row, narrows it to the five
values the engine needs, caches the natal chart per §7.2, and separates the two
declines §5.3 and §8 mean differently — thin birth data (Tara ASKS) from an
engine outage (Tara degrades).

**Four defects, all found by running it rather than by reading it.**

1. **A cited sentence that was false.** `moon_nakshatra_note` took the first
   nakshatra-shaped value in the payload. `natal.graha.nakshatra` is emitted for
   all NINE grahas and the Sun's arrives first, so the first live run produced
   *"The Moon sits in Purva Bhadrapada today"* citing the SUN's nakshatra. Every
   gate passed: the id was in the served payload, the name did match the fact it
   named. The citation machinery checks that a sentence stands on a fact, never
   that it stands on the RIGHT one — so the reader has to, and now `_nakshatra`
   requires `Graha.MOON`.

2. **A regenerate that cancelled the morning push.** §7.1's own worked example
   ("user flew to London overnight") keeps the LOCALE, so it minted the same
   `message_id`, superseded the queued row, then failed to insert its
   replacement on §23.4's unique index — 0 queued, 1 superseded, no
   notification. The existing test passed because it changed the locale. Fixed
   three ways: `enqueue` INSERTS BEFORE it supersedes (so a failed insert can
   never leave a user with nothing), `supersede` takes `keep`, and the revision
   fingerprints what would be DELIVERED — rendered modules plus schedule —
   rather than a clock. A clock was the obvious choice and is wrong twice: two
   generations inside one second collide, and an unchanged regenerate would
   send a second push for no reason.

3. **Every scheduled brief silently lost its panchang.**
   `SubjectRepository._to_subject` (the tick's bulk loader) never carried
   `brief_place`, while `wiring.load_subject` (the per-user task and every
   regenerate) did. Nothing failed — `CompositeBriefFacts` simply skips the
   panchang half without a place — so scheduled briefs shipped chart-only and
   regenerated ones came back with timings. Two loaders, one shape;
   `test_repository_mongo.py::test_the_two_loaders_agree` is now the side-by-side
   that would have caught it.

4. **A `charts` row twenty times §6.4's bound.** The engine returns the FULL
   vimshottari tree — 9 × 9 × 9 = 819 periods, 817 KB beside a 26 KB natal
   chart, against a cell that reads "bounded ~40KB". Three periods are in effect
   at any instant, so the row stores those and refreshes the window when it
   stops covering `now`; a size guard refuses a write past the bound rather than
   letting it grow back. Measured after the fix: 29.1 KB.

**Also fixed from `/review`.** `build_astrology_facade` opened a Mongo client
and provisioned a CSFLE codec per call and closed neither — once per Celery
task, i.e. once per user per morning; the codec now borrows the task's own
client and `build_service`'s teardown is real work rather than a `return None`.
`_read_chart` filtered on `(subject_id, engine_version)` while §7.2's key is
`natal_chart:{subject}:{engine_v}:{ayanamsa}` — an ayanamsa change without an
engine bump would have served a chart whose every house was quietly wrong. The
chart tools no longer fall back to UTC for a profile with no timezone (§5.3:
decline rather than guess — the local date is the date the transits are computed
for). `scripts/brief.py` gained `db/seed.py`'s HOST guard: `environment`
defaults to `"dev"`, so an env check alone would have let a production
`MONGODB_URI` seed synthetic users into production (§22.12).

**Residual risk, named.** The Hindi and Hinglish house ordinals are wrong for
houses 1–2 — the templates render `{house}वें भाव`, so house 1 reads "1वें भाव"
where Hindi wants "पहले भाव". Visible in the live run. It is inside the
`i18n.brief_templates_and_terms` gate, which is what that gate is for, and is
called out here so the §14 reviewer is looking for it rather than at it.

---

## CL-010 — house ordinals as words, and the rule the Moon/Sun defect earned
**Date:** 9 August 2026 · **Approved:** Founder · **Touches:** §2.3, §5.3 step 9,
§7.1, §14

**What changed.** House ordinals render as this locale's own WORD — `पहले भाव`,
`pehle bhaav`, `1st house` — for all twelve houses in all three locales, from a
`terms.ordinal_house` catalogue. The first cut appended a fixed suffix inside
each template (`{house}वें भाव`), which is right for ten houses and wrong for
two: Hindi wants `पहले` and `दूसरे`, not `1वें` and `2वें`. A rule wrong for two
of twelve is not a rule, so the forms are data like every other closed set here.

**The part worth reading.** Switching to words would have quietly RETIRED the
§5.3 house check for Hindi and Hinglish. `ordinal_house_patterns` matched digits
only, so once the templates stopped emitting digits, a polished line that moved
a graha from the 7th house to the 1st would have passed in two of three locales
while the English equivalent was caught. The patterns now carry the word forms
and `ordinal_house_words` maps them back to a number, so the numbers-verbatim
check still runs; an unmapped form fails closed. Editing an ordinal word means
editing both files, and the gate's reviewer notes say so.

The copy stays draft behind `i18n.brief_templates_and_terms`. The notes now open
with ORDINALS and name what to look at: the oblique agreement with `भाव`, the
spelling of पाँचवें / छठे / नौवें, and the twelve Hinglish transliterations —
written by the implementer, not a native speaker.

**The rule.** Root `CLAUDE.md` gains a non-negotiable, earned by CL-009's first
defect:

> Every milestone's acceptance includes an end-to-end run of the real path
> against live services with real data — the test suite alone never closes a
> milestone. A citation gate verifies a sentence stands on a fact; only
> role-aware fact selection and live-path runs verify it stands on the RIGHT
> fact. When a module consumes a fact, it must select by role/entity, never by
> "first matching shape."

The M6 acceptance run is why: three defects that a green suite could not see —
a true-shaped citation to the wrong body, scheduled briefs silently losing their
panchang, and a regenerate cancelling the push it was meant to replace.

---

## CL-011 — the onboarding stack, and two defects the M8 acceptance found
**Date:** 9 August 2026 · **Approved:** Founder (Nishtha Agarwal) ·
**Raised by:** M8 implementation and its live-path run ·
**Touches:** §5.4, §30.4, §24.8, §2.4, §0.11

M8 built S01–S13 on the §24.3 library. Four decisions and two defects are worth
recording; the rest is in the commits.

### 1. The two languages had drifted on §5.4's confidence vocabulary

`sitara_api` serves §5.4's own wording — `verified_limited_birth_data`,
`tradition_based_general` — on every guidance payload. The M7 component library
typed `verified_limited` and `tradition_general`. **Two of the five states the
API can return could never have rendered a chip**, and nothing failed because no
screen consumed a confidence state until S13.

**Final:** `packages/schemas/src/confidence-states.json` is the one source, the
TS side is generated from it, and `test_parity.py` asserts it against the
hand-written Python enum in both directions. No spec decision moves — §5.4's
five states and §34.7's five treatments are unchanged; only the slug the two
languages agree on.

**Residual risk:** none known. The guard fails on divergence in either
direction, and the enum stays hand-written in `facts.py` so the test checks
rather than assumes generation.

### 2. The first reading claimed two sources when one had answered — LIVE FINDING

The M8 acceptance run against live services found the ceremony rendering
"computed from your chart · verified against 2 sources ✓" with a `verified`
chip, while both panchang vendors were unreachable and the calendar layer had
come from Layer A alone.

Every fact was real. Every citation resolved. The §30.4 badge was hardcoded,
and the confidence state was computed from the birth time without reference to
how many sources had actually agreed. **No test could have caught it** — the
fixtures supply facts, not provider health, and the sentence is true of the
facts it cites while being false about their provenance.

**Final:** `FirstReading` carries a `source_state` derived from the
`PanchangResult`'s own `sources`/`degraded`/`disputed`, S13 renders it rather
than assuming `default`, and a reading is never more confident than its thinnest
half — §5.4's Verified row wants "engine parity clean", which one source cannot
demonstrate. `tests/onboarding/test_reading.py` now covers all four cases.

**Residual risk:** the same shape exists anywhere else a `VerifiedSourceRow` is
rendered with a literal state. M8 ships the only such surface; M9's Today and
Trust Sheet must take theirs from the payload.

### 3. `i18n-lint`'s namespace list is the gate's blind spot

Gate 2 scans app source for literal keys using a hardcoded namespace
alternation. A namespace absent from it is not scanned at all, so the gate keeps
reporting OK while the app references keys nobody wrote. Adding `start` and
`launch` was not housekeeping: without it the **entire** onboarding string set
would have escaped the check, and the user-visible failure mode is a raw dotted
key on screen in Hindi.

**Final:** the list is extended and the reason is now a comment above it, so the
next person adding a namespace knows the gate does not find it on its own.

**Residual risk:** the list still has to be maintained by hand. A future
improvement is to derive it from the catalogs' top-level keys.

### 4. What S13 is allowed to do, and what it never does

Written as tests before the screen existed. Four invariants hold on every path:
no `aria-busy` survives the client deadline, what replaces the skeleton is a
real localised sentence or an honest ErrorState, no raw i18n key can leak (the
API returns line IDs from a closed set, never message keys — a server-supplied
key is invisible to `i18n-lint`), and "meet your mornings" always works.

The ceremony is composed template-only, with no model. §7.1's polish is a good
trade for a brief read every day and a bad one inside a moment §0.17 measures in
seconds, where it adds a round trip and a second failure mode to the screen
whose whole job is not failing.

### Also recorded (no decision required)

**S01 ships silent.** §0.11's "Sitara Arrival" is a W10 deliverable and does not
exist. §0.11 already specifies the silent path — "the animation is composed to
work perfectly mute" — so the gesture check and the audio hook ship, the file
does not, and the analytics event records `audio: "silent"` as a path rather
than a failure. All five §0.11 paths are otherwise built and covered.

**The short form's trigger is a product judgement.** §0.11 fixes what each form
IS but not when the short one runs. It runs when a ceremony has already played
today, per §0.19: a 5.5s arrival on every app open is the product asking for
attention rather than giving something.

**The live-path run was partial.** The engine half ran fully against live
services — real birth details written through §13's facade, a real 29-fact natal
chart, real panchang — and confirmed the CL-009 shape is still live: the engine
emits the SUN's nakshatra first, and the composer correctly named the Moon's
(`bharani`) citing the Moon's fact. The browser half could not complete: Firebase
phone auth never fires in the in-app preview browser (no reCAPTCHA, no
identitytoolkit request), so **sign-in against live Firebase with the test number
is NOT yet verified for the rebuilt S03/S04**. The auth logic is M1's and
unchanged, but the rebuilt markup has only been exercised against the fake
adapter. This is an open item for the M8 sign-off, not a closed one.

**Tara's approximate states.** `concerned_kind` and `safety` still carry borrowed
frames (`TARA_APPROXIMATE_STATES_PENDING`, recorded as due "before M8 ships").
Neither state appears in S01–S13, so M8 is not blocked on them; the record
stands and is still self-checking.

