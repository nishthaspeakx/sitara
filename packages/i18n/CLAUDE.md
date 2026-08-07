# packages/i18n — ICU message catalogs (SPEC §2.4)

Locales `en`, `hi-Latn` (Hinglish), `hi` — the launch three; a language ships 100% complete or not at all. All strings ICU MessageFormat. `glossary.json` holds canonical terms (Tara never translated, never "avatar").

## Rules
- Every user-facing string in ANY app/service lives here as a key — never hardcoded in components (root CLAUDE.md non-negotiable).
- Key parity across all catalogs is CI-enforced (`scripts/i18n-lint.mjs`) — no silent English fallback, ever.
- Plurals/dates/numbers: ICU format only; locale-unsafe formatting fails `/i18n`.
- New locales join only via the §12 admin locale gate (signed checklist) — never by dropping a file here.

## Commands
- Lint: `pnpm i18n-lint` (root) or `node scripts/i18n-lint.mjs`
