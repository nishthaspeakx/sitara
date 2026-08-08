# Numerology hand-check runbook (§5.5, §22.10)

20 seed cases (NC-001..NC-020) of a **500-case** target. §5.5 requires **100%**
parity here — not 99.9%. Numerology is exact arithmetic over published tables,
so a mismatch is a bug, never a tolerance to absorb.

**Every expected value is hand-computed by a human.** An AI never fills these
and never sets `status: verified`.

Run from `services/astro/`.

## The tables you compute from

**Chaldean (primary).** 9 is held sacred and assigned to no letter:

| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|
| A I J Q Y | B K R | C G L S | D M T | E H N X | U V W | O Z | F P |

**Pythagorean (secondary).** Straight A=1…Z=26 folded mod 9 (A/J/S=1 … I/R=9).

- **Moolank** = birth **day** alone, reduced to a single digit (15 → 6).
- **Bhagyank** = every digit of the full date `YYYYMMDD`, reduced
  (1990-05-15 → 1+9+9+0+0+5+1+5 = 30 → 3).
- **Compound** = the pre-reduction sum. Record it too — Chaldean tradition reads
  compound numbers (13, 19, 22…) in their own right.
- `master_numbers: reduce` (the default) means reduce all the way to 1-9.
  `preserve` stops at 11/22/33 — NC-015 exists specifically to prove the policy
  changes the answer.

## What each case asks of you

`input.confirmed_latin` is the string you sum — **not** the native-script name.
That is the §22.10 rule: Chaldean values are defined over the Latin
transliteration of the name as spoken, as confirmed by the user.

Cross-script cases (NC-004..NC-009) additionally ask you to confirm the
transliteration itself:

- `iso15919` — the scholarly form (e.g. `lakṣmī`, `kr̥ṣṇa`, `gaṇeśa`)
- `suggested_latin` — the readable form we would show in
  "We read your name as '…' — correct?" (e.g. `Lakshmi`, `Krishna`, `Ganesha`)

If you disagree with a suggested spelling, say so — the fold is a product
decision, not a fact, and the user can always override it in the app.

## Workflow

```bash
uv run python -m sitara_astro.golden list          # both suites, fill state
```

Fill a spreadsheet, export CSV with header `case_id,field,value`:

```csv
case_id,field,value
NC-001,moolank,6
NC-001,bhagyank,3
NC-001,chaldean_name_number,1
NC-001,chaldean_compound,19
NC-001,pythagorean_name_number,1
NC-001,pythagorean_compound,28
NC-004,iso15919,lakṣmī
NC-004,suggested_latin,Lakshmi
```

```bash
uv run python -m sitara_astro.golden import batch.csv --dry-run
uv run python -m sitara_astro.golden import batch.csv
uv run python -m sitara_astro.golden verify NC-001 --reviewer "Your Name" --source JyotishLead
uv run python -m sitara_astro.golden report
```

Fields: `moolank` · `bhagyank` · `chaldean_name_number` · `chaldean_compound` ·
`pythagorean_name_number` · `pythagorean_compound` · `iso15919` ·
`suggested_latin`. Verify refuses until moolank and bhagyank are filled (plus
both name numbers when the case has a confirmed name).

## Cases worth extra attention

- **NC-004 vs NC-001** — same person, one entered in Devanagari. After
  confirmation both sum the identical Latin string, so **every number must
  match**. If they diverge, the transliteration pipeline is broken.
- **NC-010 vs NC-004** — the user edited "Lakshmi" to "Laxmi". These **must
  differ**: the §22.10 edit affordance is authoritative over our proposal.
- **NC-014 vs NC-015** — identical input, opposite `master_numbers` policy.
- **NC-008** — anusvara assimilation (`ānaṁda` → "Ananda", not "Anamda").
- **NC-019** — no name at all: only moolank and bhagyank apply.
- **NC-020** — apostrophe in "D'Souza" carries no value.

## Data rule (§13)

Cases live in git forever. **Use synthetic names and dates only** — never copy a
real user's profile into a case file, however convenient. The seed set is
fictional; keep it that way as it grows.

## Growing to 500

§22.10 wants 200 cross-script cases **per launch language**. The seed set covers
Devanagari only; Gujarati, Punjabi, Tamil and Telugu arrive with their language
waves, and the engine will need a transliteration table per script before those
cases can be authored.
