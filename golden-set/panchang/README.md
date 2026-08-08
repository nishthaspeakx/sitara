# panchang golden cases (PC-*) — SPEC §5.2, §5.5

Sunrise/sunset, tithi and nakshatra boundary instants, and the sunrise-anchored
day divisions, for one local date at one place.

## What is being verified, and by which authority

The two halves of each case have different standing, and the reviewer should
treat them differently:

**Deterministic astronomy — Layer A is authoritative (§32.2, decision D1).**
`sun`, `tithi` and `nakshatra` are computed by our own ephemeris. Verify them
against Drik Panchang / Jagannatha Hora exactly as for the GC-* suite. A
mismatch here is an engine bug.

**Tradition rule tables — DivineAPI is primary for the served value.**
`day_timings` and `choghadiya` come from published weekday tables (rahu kaal,
yamaganda, gulikai part numbers; the seven-name choghadiya cycle and its
weekday entry points). Our implementation exists so that §8's degradation
ladder has a real internal rung when DivineAPI is down — it is not what a user
normally sees. A mismatch here may mean **our table is wrong**, not our
arithmetic, and the Jyotish lead's ruling on the table is the answer.

## Conventions pinned by these cases

- **Rise/set:** upper limb with refraction — the definition published almanacs
  use, so our sunrise matches the one a user can look up. Recorded on every
  fact as `FactMethod.rise_set`.
- **The panchang day runs from sunrise**, not local midnight: the tithi and
  nakshatra named for a date are the ones running AT sunrise.
- **All expected values are LOCAL time** at the case's place. The engine works
  in UTC; the harness converts. This is deliberate — a reviewer reads a
  published almanac in local time, and asking them to convert invites error.

## Coverage rationale

| case | why it exists |
|---|---|
| PC-001 | Mumbai baseline; anchors the rise/set convention |
| PC-002 | Sunday (rahu kaal in the last eighth) + purnimanta reckoning |
| PC-003 | Southern hemisphere (§5.2 Layer C names it) — winter solstice |
| PC-004 | DST spring-forward morning (§5.5's 600-case suite) |
| PC-005 | High latitude, ~21h day — stresses the eight-part division |
| PC-006 | Near-equatorial, December — seasonal bugs show as anomalies |
| PC-007 | UTC+12: local sunrise is the previous UTC date (§5.3 cache-key guard) |
| PC-008 | Full-moon date where amanta and purnimanta name different months |

Polar day/night is deliberately **not** a golden case: there is no expected
value to verify. The engine declines (`ASTRO_INSUFFICIENT_BIRTH_DATA`), and
that behaviour is pinned in `services/astro/tests/engine/test_riseset.py`.

## Rule

Only the Jyotish lead's sign-off CLI may set `status: verified`
(`golden verify … --reviewer …`). An LLM never verifies ephemeris maths or a
tradition table — that is the exact failure §5 exists to prevent.
