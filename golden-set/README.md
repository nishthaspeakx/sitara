# golden-set — astrology validation cases (SPEC §5.5)

The single most important asset in the repo. Grows to 10,000 human-verified cases.

- **Format:** versioned YAML in `cases/GC-*.yaml`, `schema_version: 2` —
  `{case_id, category, status, source, verified_by, verified_on, notes, input, tz_expected, expected}`.
  `input` carries date, time, `time_accuracy` (exact|window|date_only), fold,
  place/lat/lon/tz and engine options; `expected` carries grahas, lagna, dasha,
  boundary times and transits. Unfilled values are the literal
  `NEEDS_VERIFICATION` sentinel.
- **Thresholds (§5.5):** positions ≤1 arc-min · boundary times ≤2 min ·
  dasha boundaries ≤1 day · rashi/nakshatra/pada/lord exact.
- **CI:** release-blocking — the `golden-set` job runs the harness and
  `python -m sitara_astro.golden report --gate`, which FAILS the build under
  99.9% parity on verified cases. Pending cases are computed and reported but
  never gate.
- **Rule (playbook Part 4):** expected values enter as `verified` ONLY via the
  Jyotish lead's sign-off CLI (`golden verify … --reviewer …`), sourced from
  Jagannatha Hora / Drik Panchang. An LLM never verifies ephemeris maths — that
  is the exact failure §5 exists to prevent.

## Suites

| suite | cases | gate (§5.5) | runbook |
|---|---|---|---|
| astrology `cases/GC-*.yaml` | 25 seeded | ≥99.9% on verified | [cases/README.md](cases/README.md) |
| numerology `numerology/NC-*.yaml` | 20 seeded of 500 | **100%** (exact arithmetic) | [numerology/README.md](numerology/README.md) |

Both share one envelope, one CLI (`python -m sitara_astro.golden`, routed by
case-id prefix) and one rule: only a named human may set `status: verified`.
Harness code: `services/astro/src/sitara_astro/golden/`, tests in
`services/astro/tests/golden/`.
