# golden-set — astrology validation cases (SPEC §5.5)

The single most important asset in the repo. Grows to 10,000 human-verified cases.

- **Format (lands in M2):** versioned YAML — `{input: birth data, expected: facts, source: JHora|Drik|Jyotish-lead, status: verified|pending}`.
- **Thresholds (§5.5):** positions ≤1 arc-min · boundaries ≤2 min · dasha ≤1 day.
- **CI:** release-blocking from M2 — build FAILS under 99.9% parity on verified cases.
- **Rule (playbook Part 4):** expected values enter as `verified` ONLY via the Jyotish lead's sign-off CLI, sourced from Jagannatha Hora / Drik Panchang. An LLM never verifies ephemeris maths — that is the exact failure §5 exists to prevent.
