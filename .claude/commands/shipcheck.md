Run every gate below and summarise red/green per gate. Report honestly: a gate that cannot be closed by code is still reported, never omitted.

## Automated gates
1. **Lint** — `cd services/api && uv run ruff check .` (repeat for services/astro, services/realtime)
2. **Types** — `cd services/api && uv run pyright`
3. **Tests** — `cd services/api && uv run pytest -q` (repeat per service)
4. **i18n parity + references** — `node packages/i18n/scripts/i18n-lint.mjs` (§2.4 — no silent English fallback; also fails on a key app source references but no catalog defines, and on an undeclared runtime-built key)
5. **Token lint** — `pnpm token-lint` (§24.2/§29.4 — no hardcoded hex/px, no fill token used as text, and every declared contrast pair AA-verified numerically in BOTH themes)
6. **DB drift** — `cd services/api && uv run python -m sitara_api.db.verify` (§6.4, exit 1 on drift)
7. **Design system** — `pnpm --filter web test` (§24.3/§34.7 — the library is 48 components, each declared, storied and exported)
8. **Per-locale screenshot diff** — `pnpm --filter web build-storybook && pnpm --filter web screenshots` (§24.8 design-QA gate, §14 Language QA — 48 components × 4 locales × 2 themes, plus the §0.12 reduced-motion paths)

`pnpm design-qa` runs 4, 5, and 7–8 together with types and lint, in order.

## Human-closed gates (§31.7)
7. **Release gates** — `cd services/api && uv run python -m sitara_api.release_gates`

These close only when a named human signs off, so they are reported every run and never silently pass. Currently open, per §37:
- `safety.helpline_table` (§22.9) — **closed-beta blocker**, status "awaiting human-verified numbers". The L4 auto-response points at the in-app support surface; no helpline number is hardcoded from memory. Closes when `policy/helplines.json` exists with every number verified against its publishing body.
- `safety.l1_rule_lexicon` and `safety.fear_selling_corpus` (§14) — **closed-beta blockers**, status read from each file's `review_status` field. Close when the named native safety reviewer signs off per locale.

Report each as its own line in the summary with its spec reference and the stage it blocks. Do not describe the build as ship-ready while any of them is open — say which stage is blocked and by what.
