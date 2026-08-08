# Golden case verification runbook (Jyotish reviewer)

These 25 seed cases (GC-001..GC-025) exercise the §5.5 edge list. Every `expected`
value is a `NEEDS_VERIFICATION` placeholder. **Only a human fills them, and only from
Jagannatha Hora (or Drik Panchang for boundary times). An AI or engineer never
sets `status: verified` — that is the exact failure §5 exists to prevent.**

Run everything below from `services/astro/`.

## JHora setup (do this BEFORE reading any values)

1. **Ayanamsa → Lahiri (Chitrapaksha).** JHora's out-of-box default is *True
   Chitrapaksha*, which is NOT the same as Lahiri. Preferences → Related to
   Calculations → Ayanamsa → Lahiri.
2. **Nodes → Mean.** Confirm the node setting matches `input.options.node_type`
   in the case file (all seeds use `mean`). Note it in `notes` if you deviate.
3. **Dasha year length → 365.25 days.** All seeds use `dasha_year: days_365_25`.
4. **Location/time:** enter `input` exactly — date, local time, lat/lon.
   **Trust the case's `tz_expected.utc_offset` over JHora's own timezone guess** —
   offsets here come from the IANA tzdb, the project's sole timezone authority
   (§5.2). For GC-010/GC-020 (DST-gap births) enter the *shifted* wall time
   (original + `gap_shifted_minutes`). For GC-011/GC-012 note the `fold`: same
   wall clock, different real instant — the charts MUST differ.

## 1. See what needs filling

```bash
uv run python -m sitara_astro.golden list
```

## 2. Fill values in a spreadsheet, export CSV, import

The CSV is long-format — one row per value, so you can fill in any order and
import repeatedly. Required header: `case_id,field,value`.

```csv
case_id,field,value
GC-001,grahas.sun.longitude_deg,30.1234
GC-001,grahas.sun.rashi,vrishabha
GC-001,grahas.sun.nakshatra,krittika
GC-001,grahas.sun.pada,2
GC-001,lagna.longitude_deg,201.5017
GC-001,dasha.maha_at_birth.lord,venus
GC-001,dasha.maha_at_birth.start,1988-03-11
GC-001,boundaries.moon_nakshatra_end_utc,1990-05-15T18:22:00Z
```

```bash
uv run python -m sitara_astro.golden import my-batch.csv --dry-run   # validate
uv run python -m sitara_astro.golden import my-batch.csv             # apply
```

Import validates every row before writing anything — a bad graha name, an
out-of-range pada or an unknown case id aborts the whole batch, leaving files
untouched. Import can **never** mark a case verified.

**Field paths:** `grahas.<graha>.{longitude_deg,rashi,nakshatra,pada}` ·
`lagna.{longitude_deg,rashi}` · `dasha.{maha_at_birth,antar_at_birth}.{lord,start,end}` ·
`boundaries.{moon_nakshatra_end_utc,tithi_end_utc}` ·
`transit.{saturn_whole_sign_house,moon_nakshatra}` (GC-001 and GC-025 only).
Lowercase Sanskrit names (`mesha`..`meena`, `ashwini`..`revati`); dates ISO
(`1990-05-15`); boundary times ISO-8601 UTC (`…T18:22:00Z`).

## 3. Sign off

```bash
uv run python -m sitara_astro.golden verify GC-001 --reviewer "Your Name" --source JHora
```

`--source` is `JHora`, `DrikPanchang`, or `JyotishLead`. Verify refuses until all
nine graha longitudes and the lagna are filled, and records your name and the
date in the case file. **From that moment the case gates releases.**

## 4. Check parity any time

```bash
uv run python -m sitara_astro.golden report
```

Thresholds (§5.5): positions ≤1 arc-min · boundary times ≤2 min · dasha
boundaries ≤1 day · rashi/nakshatra/pada/lord exact. CI runs this with `--gate`
and fails the build below 99.9% on verified cases.

## Open convention flags (reviewer adjudicates, engine follows)

- **Mean vs true nodes** — engine defaults to mean; ruling for true means we flip
  the `EngineOptions` default and re-baseline.
- **Bhava system** — Sripati bhava computed alongside whole-sign presentation.
- **Dasha year basis** — 365.25 days default; sidereal/savana available.
- **Transit house reference** — houses are counted from the natal **lagna**.
  Traditional gochar is often read from the **Moon** (janma rashi, sade sati).
  If you want Moon-relative transits, say so and we add them as a distinct fact.
