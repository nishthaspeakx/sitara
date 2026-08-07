# §31.3 change-control entry — DRAFT for founder sign-off (M3, panchang provider layer)

**Status: NOT APPLIED.** This is a proposal. SPEC.md is frozen at v3.4 and has
not been edited. Approve, amend, or reject; on approval these become §26.1
entries and the corresponding SPEC.md paragraphs are updated in one commit.

Nothing here changes a baseline decision. Two are *completions* (a mandated
behaviour with nowhere to live), and three are *reconciliations* (two sections
read together, written down so the next implementer does not re-derive them).

---

## CC-M3-01 — New collection `fact_adjudications` (completion)

**Why.** §32.2 requires that a disputed panchang fact "queues Jyotish
adjudication", and §12 requires an admin "adjudication workflow" over Layer-D
diffs. Neither has anywhere to write: §6.4's collection table has no row for it,
and `audit_logs` is for human sensitive actions (actor + justification), not
machine-generated comparison findings.

**Proposed §6.4 row.**

| Collection | Key fields | Indexes | TTL / retention | Shard key | Encryption |
|---|---|---|---|---|---|
| fact_adjudications | fact_class, fact_key, served_source, delta_seconds, tolerance_seconds, readings (embedded snapshot per source), status, kind, place_label, local_date, created_at | status+created_at; fact_key | 24 months (matches guidance_logs — the audit trail must outlive the guidance built on the fact) | created_at | — |

**Notes.** No user reference: the unit of comparison is date+place+tradition,
because panchang is global (§34.2). Readings are embedded rather than
re-queried — a vendor's answer can change under us, and a reviewer must see
what we actually served against what we actually got.

---

## CC-M3-02 — `FactSnapshot` gains `source` and `confidence` (completion)

**Why.** §5.2 already describes a snapshot as "(id, value, source, confidence)",
but the M2 model shipped without either field, so a Trust Sheet could not state
which layer produced a fact.

**Proposed.** Both optional with defaults (`source=layer_a`, `confidence=null`),
so every artefact written before M3 still validates on read — §34.2 requires old
Trust Sheets to read exactly as generated.

---

## CC-M3-03 — Authority split for boundary instants (reconciliation)

**The tension.** §32.2 lists "nakshatra" under chart facts (Layer A
authoritative, never voted). §5.2 Layer D lists "tithi/nakshatra boundary times
>2 min" as a vendor-comparison tolerance. Our engine computes those instants.

**Proposed reading (founder-approved as decision D1 during M3 planning).**

- **Deterministic astronomy — Layer A authoritative, never voted:** graha
  positions, lagna, dasha, tithi/nakshatra/yoga **boundary instants**,
  sunrise/sunset. Vendor disagreement beyond tolerance raises a *review flag*
  for the §12 dashboard only — never `disputed`, never a confidence downgrade.
- **Calendar interpretation — DivineAPI primary:** amanta/purnimanta month
  naming, choghadiya and rahu-kaal/yamaganda/gulikai day divisions, muhurat
  windows, festival dates. A DivineAPI↔Prokerala gap beyond tolerance serves
  DivineAPI, downgrades confidence to Approximate (§5.4's "disputed fact in
  play"), and queues adjudication.
- **Hybrid, and deliberately so:** boundary instants are *also* panchang facts
  served through the §8 ladder. When Layer A cannot answer, §32.2's plain rule
  takes over — DivineAPI serves and a Prokerala disagreement disputes. This is
  the only way to honour both §32.2's closing line and its DivineAPI-primary
  rule without one silently overriding the other.

This preserves §32.2's closing sentence exactly: two unverified vendors can
never overrule validated deterministic astronomy — including by being the
source we happened to call first.

---

## CC-M3-04 — Superseded rule, stated explicitly (reconciliation)

§5.2 Layer D still reads "the affected fact is served from the **majority
source**". §32.2 replaced that with an authority rule and is the later entry.

**Proposed.** Add to §5.2 Layer D: *"(Serving rule superseded by §32.2 — no
majority vote is taken; see §32.2 for the authority rules.)"* The implementation
contains no vote, and a test asserts none can be reintroduced.

---

## CC-M3-05 — Cache-row provenance, stated explicitly (reconciliation)

**The tension.** §7.2's panchang key ends in `{provider}`, but §6.4's index is
`uniq (date, geo, tradition)` — which would collide the moment two providers
cached the same day.

**Proposed clarification (no behaviour change).** They never collide, because
only DivineAPI rows are ever persisted:

- **Prokerala** is ephemeral by ToS (§5.2) — the cache raises on a write attempt.
- **Layer-A fallbacks** are recomputed on demand, not stored: our engine is
  authoritative for astronomy but is not the system of record for calendar
  facts, and §34.2 already puts global astronomy in `transit_cache`.

So exactly one provider occupies a panchang row and §6.4's index holds as
written. Muhurat and festival rows share the collection under the other §7.2 key
grammars, so the uniq index carries `partialFilterExpression: {kind:"panchang"}`
— scoping §6.4's constraint precisely to the panchang days it was written about.

---

## Also worth recording (no spec change requested)

- **`packages/schemas/python/sitara_schemas/cache_keys.py`** is a second
  hand-written module in the generated-only package. The §7.2 key grammar is
  shared by both services (astro builds global fact subjects from it, api builds
  cache keys); a second copy would drift, and a drifting key silently
  repartitions the cache. Recorded in that package's CLAUDE.md.
- **Rise/set convention** is `upper_limb_refracted` — the definition published
  almanacs use, so our sunrise matches the one a user can look up. Recorded on
  every fact as `FactMethod.rise_set` and adjudicable like any other default.
- **Day-timing rule tables** (rahu kaal / yamaganda / gulikai weekday parts,
  choghadiya sequence) are tradition, not physics. They are implemented as the
  §8 fallback rung and carried into golden-set as `NEEDS_VERIFICATION` pending
  Jyotish sign-off.
