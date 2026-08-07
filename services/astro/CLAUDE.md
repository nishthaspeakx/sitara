# services/astro — Layer-A astrology engine (SPEC §5) — THE crown jewel

Deterministic pyswisseph engine (Lahiri ayanamsa; whole-sign presented, bhava computed), nakshatra+pada, vimshottari dasha, gochar transits. Output = typed FactSnapshots (§34.2): {fact_id, kind, value, precision, method, valid_from, valid_to, engine_semver, data_revision}.

## Rules
- The LLM NEVER computes astrology — this engine is the only source of astrological facts (§5.3). Cite-or-die.
- Timezone: historical offsets via IANA tzdb from stored place+datetime; NEVER trust an external astrology API for tz.
- Tests FIRST; golden-set parity (§5.5: positions ≤1 arc-min, boundaries ≤2 min, dasha ≤1 day) is release-blocking CI at ≥99.9% on verified cases. Expected values come from JHora/Drik/Jyotish lead — never from an LLM.
- Fact-IDs are logical keys; artefacts embed full snapshots at generation (§34.2). No facts collection.

## Commands
- Run: `uv run uvicorn sitara_astro.main:app --port 8003 --reload`
- Test: `uv run pytest -q` · Golden set (from M2): `/golden`
