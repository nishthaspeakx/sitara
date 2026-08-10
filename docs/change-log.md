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

**The live-path run — now complete. CLOSED 9 August 2026.** The engine half ran
fully against live services — real birth details written through §13's facade, a
real 29-fact natal chart, real panchang — and confirmed the CL-009 shape is still
live: the engine emits the SUN's nakshatra first, and the composer correctly
named the Moon's (`bharani`) citing the Moon's fact.

The browser half could not complete at the time of writing: Firebase phone auth
never fires in the in-app preview browser (no reCAPTCHA, no identitytoolkit
request), so sign-in against live Firebase was recorded as an OPEN item for the
M8 sign-off rather than quietly assumed. **The founder has since verified S03 and
S04 end to end in real Chrome against the live stack, and the item is closed.**
Both halves of §24.4's acceptance have now run against live services, which is
what CLAUDE.md requires before a milestone closes.

**Tara's approximate states.** `concerned_kind` and `safety` still carry borrowed
frames (`TARA_APPROXIMATE_STATES_PENDING`, recorded as due "before M8 ships").
Neither state appears in S01–S13, so M8 is not blocked on them; the record
stands and is still self-checking.

---

## CL-012 — `next dev` and `next build` cannot share an output directory
**Date:** 9 August 2026 · **Approved:** Founder (Nishtha Agarwal) ·
**Raised by:** a dev server failing with "Cannot find the middleware module"
after the M8 builds · **Touches:** the web build setup only; no spec section

**What changed.** `apps/web` now uses three Next output directories — `.next-dev`
for `next dev`, `.next` for `next build`, `.next-test` for the flow suite's
build — and `next.config.ts` chooses between them by build PHASE rather than by
an environment variable.

**Why.** `next build` rewrites manifests in its output directory while a running
`next dev` reads and rewrites the same files. Sharing one directory corrupts
whichever is running. Next 15 reports it as "Cannot find the middleware module"
or `__webpack_modules__ is not a function`, both of which name a symptom and not
the cause, and **deleting the directory does not fix it**: the dev server
rebuilds into it and the next build clobbers it again. Reproduced directly — dev
serving 200, `pnpm build`, then 500.

The collision long predates M8 and was carried as a documented gotcha. M8 made
it fire often enough to stop being one: `design-qa` runs TWO Next builds and is
now the routine command.

**What it was not.** `.next-test` was suspected and is exonerated — a build into
it while dev is live leaves dev untouched, and it was already a partial
mitigation. Turbo's cache is not involved. **The build ordering in `design-qa` is
not involved either**, which corrects the commit that introduced it: that reorder
was about `next-env.d.ts` churn, and that file is now simply not committed.

**What it now permits.** Running any build at any time with a dev server live.

**What it now refuses.** `next dev` cannot be pointed at a build's directory,
even by a stray `NEXT_DIST_DIR` in a shell — the phase decides and a caller
cannot pass a phase. `tests/dist-dirs.spec.ts` refuses a build that collapses the
directories, makes dev overridable again, returns the config to an env-var
`distDir`, names a directory in the `dev`/`build` scripts, or adds a directory
without git-ignoring it. Each assertion was verified by breaking the invariant it
covers.

**Residual risk.** Three build outputs on disk instead of one — a few hundred MB
during development, all git-ignored. `next-env.d.ts` is no longer committed; a
cold clone typechecks without it (verified with no output directories present),
but a future Next version could change that, in which case `pnpm typecheck` on a
fresh clone is where it would show.

**Also fixed on the way.** The `library` Playwright project was starting both web
servers it does not use, because Playwright starts every configured `webServer`
regardless of which projects are selected. On a clean checkout that is a hang
waiting for a `next start` against a `.next-test` nobody has built yet. Servers
are now scoped to the projects that need them.

---

## CL-013 — API routing, and a suite that could not see a 404
**Date:** 9 August 2026 · **Approved:** Founder (Nishtha Agarwal) ·
**Raised by:** every onboarding step 404-ing in a real browser ·
**Touches:** §34.5, §6.2, §34.4, §24.6, §28.1

**What broke.** `GET/PATCH /v1/onboarding` came back 404 in Chrome, at
`http://localhost:3000/hi/v1/onboarding`. next-intl's middleware exists to put a
locale on every route it sees, and its matcher excluded `auth` but not `v1` — so
it 307'd `/v1/onboarding` to `/<locale>/v1/onboarding`, which matches no rewrite
and no page. `/auth/session` worked and `/v1/*` did not, for a reason nothing in
the code connected. **API routes are never locale-prefixed**; the locale travels
in the request body or comes from the session.

**What was fixed.**

1. **The prefix, at source.** The matcher excludes every proxied prefix.
   `src/lib/api.ts` holds the one list, `tests/api-routing.spec.ts` asserts the
   three places that must agree — the list, the rewrites, the matcher — and
   `apiUrl()` throws on a locale-prefixed path at the call site.

2. **One API door.** `session.ts` and `onboarding.ts` each built their own paths
   and handled their own errors. Both now call `apiCall`, which is also where
   the §34.4 envelope is guaranteed: a 404 or a proxy error carries no envelope,
   and returning the raw body handed screens `undefined.message_key`.

3. **A step that failed silently.** S02 switched locale AND persisted, and it
   switched first — which replaces the React tree, so the failed PATCH set its
   error on a component that no longer existed. The user tapped a language and
   *nothing happened*: no error, no retry, no advance. The order is now
   persist-then-navigate, with the locale carried into the forward navigation,
   and `tests/onboarding-errors.spec.ts` drives a forced failure through EVERY
   step that writes and asserts the envelope surfaces and does not advance.

4. **Resume sent users backwards.** Found by asserting persisted state rather
   than navigation: S03, S04 and S06 advanced without recording themselves, and
   `next_step` is the lowest UNrecorded step — so a user who had signed in,
   consented and given her birth details resumed at the sign-up screen.

**Why the suite was green.** It used `page.route("**/v1/onboarding", …)`, which
intercepts in the BROWSER. The request never left, so the Next server — and with
it the middleware and the rewrite — never saw it. The suite verified that the
client handles a response the test invented, and had never once verified the URL
that produces it. **A browser-level intercept structurally cannot observe a
redirect issued by the server it prevented the request from reaching.**

Replaced by `scripts/stub-api.mjs`, a real process the app proxies to, so every
request travels browser → `next start` → middleware → rewrite → API. Confirmed
by regression: restoring the old matcher now fails `api-routing.spec.ts`.

**A trap found while fixing it.** The first attempt made the API base URL
client-configurable via `NEXT_PUBLIC_API_BASE_URL`, which `.env.example` already
shipped as `http://localhost:8001`. Every developer build picked it up and every
call became cross-origin: CORS refused the preflight, and any call that had got
through would have arrived **without the httpOnly session cookie**. §34.5 and
§6.2 require the browser to call its own origin and the server to proxy — "one
site" is the design, not an implementation detail. The knob is removed rather
than defaulted-to-empty; the origin is still env-configured in exactly one
place, `API_PROXY_TARGET`, on the server side of the proxy.

**Also recorded.** Next evaluates `rewrites()` at BUILD time and bakes the
destination into `routes-manifest.json`, so `API_PROXY_TARGET` on `next start`
does nothing — silently, with the server up and the routes working. It cost a
debugging session in which the flow suite's stub was receiving nothing while a
developer's real `sitara-api` quietly served the tests. Playwright no longer
reuses running servers either: a `next start` left over from an earlier build
serves that build, which failed five design-qa tests that pass in isolation.

**Residual risk.** `apiUrl` validates prefixes at runtime, so a bad path throws
in the browser rather than at build time. The three-way agreement is asserted by
a test rather than derived from one source, because Next requires the middleware
matcher to be a static literal it can analyse at build time.

**M8's last open item is closed.** CL-011 recorded that sign-in against live
Firebase was unverified for the rebuilt S03/S04, because phone auth does not fire
in the in-app preview browser. The founder verified both screens end to end in
real Chrome against the live stack on 9 August 2026 — the same browser and stack
that surfaced the routing defect above — so M8 closes with both halves of its
acceptance run against live services, and nothing carried forward.


---

## CL-014 — Today's payload, and four things §28.2 could not be built without

**Date:** 9 August 2026 · **Approved:** Founder (Nishtha Agarwal) ·
**Raised by:** M9 implementation · **Touches:** §28.2, §32.1, §7.1, §30.4, §24.2

M6 built §7.1's pipeline end to end and stored `daily_briefings` rows that
**nothing could read** — there was no HTTP surface at all. `GET /v1/today` is
that surface. Four decisions were needed to render §28.2 against it, and none
changes a decision the spec makes.

**1. Tara's line is composed, but it is not an eighteenth module.** §28.2 item
(2) — "one warm sentence for this moment … always present" — is not one of
§34.3's seventeen, and the enum is closed. `templates.compose_taras_line`
writes it in two registers: cited when it leans on the day's nakshatra,
claimless when there are no facts. The claimless register is what makes "always
present" compatible with §5.3's cite-or-die, and it is the register a
first-session or failed morning uses.

*What it refuses:* an English fallback when a locale has no catalog entry — the
line is simply absent, per §2.4 rule 7.

*Found while building it:* a cited line must be **one sentence**. `_cite` places
the marker before the final stop, so a two-sentence line leaves the claim in
sentence one uncited — perfectly cited text failing its own validator, which is
the hazard `services/api/CLAUDE.md` already records for module templates. Caught
by running every band × locale through the grounding validator.

**2. A festival is nudged into the ranking, not exempted from it.** §28.2 puts a
festival on two surfaces: §32.1's banner (the only thing permitted above the
core card) and a contextual card among the max four. Left at its default
relevance, `festival_observance` sits mid-pool and loses the MED-density cut to
`family_reminder` and `priorities` — so a festival morning rendered **no
festival anywhere**. `service._relevance_for` raises its relevance when the fact
is present, which is precisely what `RankingContext.relevance` was written for
("a festival today, a family birthday tomorrow").

*What it refuses:* nothing new. The module is still gated on holding a
`FESTIVAL_OBSERVANCE` fact (§5.3) and still named in-locale or not at all (§2.4).

**3. `sources_line` is derived from the confidence state, not the snapshot
count.** The first cut read `len(module.snapshots)`, and the recorded fixtures
made the result visible immediately: a Trust Sheet whose plain line said
"checked against two sources" directly above a source row saying "one source
available today". A module's snapshot count is how many **different facts** it
stands on, not how many sources agreed on one. §32.2 already encodes
corroboration in the confidence state, so both lines now read it and cannot
contradict.

**4. The sky gradient carries no text.** §28.2 asks the header for a "sky
gradient matching local time"; §24.2/§34.8 freeze the palette and define no
dawn/day/dusk sky. Rather than open a §31.3 entry for four new primitives, the
bands are composed from existing tokens — and the header's strings were moved
OFF the gradient after `token-lint` rejected six declared pairs, every one a
real defect:

* `ink-muted` on `gold-soft` is 3.33:1 and on `line` is 3.75:1 — the tithi line
  would have failed AA on two of four bands in the light theme;
* `gold-soft` is a **light** fill in the night theme too, so a morning band
  there put light ink on cream at 1.17:1;
* `text-inverse` means "the opposite of this theme's ink", so on a fixed dark
  sky it is navy in the night theme — 1.02:1, invisible, in the one theme the
  night band exists for.

A gradient is the worst surface to measure against anyway: the value under a
word depends on where the word landed. Text now sits on solid `bg-canvas`, a
pair the matrix already verifies in both themes. This is CC-005 working as
intended — the failures were found by the lint, before a screenshot, and none
of them is a threshold worth relaxing.

**Also recorded.**

*The web's Today fixtures are recorded, never authored.* `stub-api.mjs` replays
57 payloads produced by the real pipeline
(`services/api/scripts/record_today_fixtures.py`). A hand-written brief in the
stub would be a brief nobody's engine produced, and all 109 §24.8 baselines
taken from it would stay green through any regression in ranking, composition
or the §7.1 ladder. `tests/today-fixtures.spec.ts` re-validates every recording
against the generated schema so one cannot be edited into fiction.

*`compose_brief` was split out of `generate_for`* so §7.1's four outcomes are
reachable with no store, queue or clock. That is what let the dev variant
switcher run the **real** ladder instead of needing a fake `BriefStore` — and
per CLAUDE.md a fake that accepts what the real one rejects is a defect in the
fake, so the better answer was not to need one.

*§7.1's DEGRADE had two entrances and only one worked — now fixed.* The
grounding `fail` edge fired correctly; "facts too thin" could not, because
`rank`'s base modules are a superset of what `core_cards` wants under the same
`emittable` gate, so a fact set that leaves `rank` empty leaves `core_cards`
empty too and lands on FAILED. The single way through was an accident of
density — LOW skips the panchang row, so a nakshatra-only morning reached the
degrade there and nowhere else. **Two users with identical evidence and
different density settings therefore got different honesty:** the skeptic was
told the reading was incomplete, the devout user was shown one card and no
explanation. `service._is_core_cards_only` is the real trigger and requires BOTH
halves — the fact stage named something missing, AND nothing beyond
`ranking.CORE_CARD_MODULES` survived. A core-cards-only morning with every fact
in hand is a quiet LOW-density day, and labelling it degraded would tell a
skeptic their reading failed every morning. The degrade also skips polish, per
§7.1's "no LLM".

Two consequences worth recording. The dev fixture no longer needs a stub model
to reach the degrade, so `UngroundedLLM` is deleted — the switcher carries no
stub at all. And `moon_nakshatra_note` is promoted to the core card when it is
the only card left, because a degraded screen whose one card sits inside the
panchang summary row has no centre; `PanchangRow` then renders the strip alone,
so it never appears twice.

*A test named for the wrong thing hid it.* `test_thin_facts_degrade_to_core_cards`
asserted `POLISHED`. Anyone scanning the test list saw the degrade covered; the
body said the opposite, and the body was right. Renamed to
`test_a_missing_chart_alone_is_a_real_brief_not_a_degrade`.

*The three fact-free modules are wired — now fixed.* `priorities`, `goal_check`
and `family_reminder` are gated on `RankingContext.available_inputs`, and
**nothing built that dict**, so all three were structurally unreachable in a real
brief for three milestones — the most personal cards in the product, never once
shown. `daily_guidance/personal_inputs.py` is the loader, called by BOTH
generation paths. Three rules hold it: a slug is not a sentence
(`profiles.priorities` resolves through `start.priorities.option.*`, and a
priority we cannot name in this locale yields no card); a goal is already in the
user's words (`goals.text` verbatim, never translated); and a CSFLE name that
reads back as ciphertext declines rather than composing a card around a blob. A
leap-day birthday gets no card rather than a guessed one. Verified on the live
stack: all three composed for a synthetic persona, in en and hi.

**S15–S17 close the routes.** `/today/timings`, `/today/festival` and
`/today/brief/[card]/why` (§29.1) now exist, so §28.2 item (6)'s link points
somewhere and the 404 RSC prefetch that hung every `networkidle` wait is gone.
Two things the why-route settled: §30.4's three layers must each say something
the others do not — layer 1 was the confidence description, which the
ConfidenceChip also renders, so the sheet showed one sentence three times; it is
now the CLAIM, which is how §30.4's own worked example opens. And S16 needed
structured windows on the wire (`TodayTiming`) plus `place_label`, because §30.2
forbids implying the place a timing was computed for, and a timezone is not a
city anyone chose.

**Residual risk.** The density control §28.2 calls "user-tunable in settings" is
unbuilt: density is read from `profiles.density` (set at S09), and the dev
switcher is what exercises LOW and HIGH.
