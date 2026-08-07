# apps/web — Next.js 15 PWA (SPEC §6.2)

App Router with `[locale]` segment routing (next-intl; locale in URL, cookie-pinned). Locales: en, hi-Latn, hi (§2.4). Server Components for content surfaces, client islands for chat/voice/Tara presence.

## Rules
- Strings: i18n keys from `@sitara/i18n` ONLY — a hardcoded user-facing string fails `/i18n` and CI.
- Styling: tokens from `@sitara/tokens` ONLY — raw hex/px fails token-lint. Tara = photographic presence, never "avatar".
- RTL: logical CSS properties from day 1. Accessibility: WCAG 2.2 AA. Touch targets ≥ token touch.target-min.
- Auth calls: httpOnly session cookies (§34.5) — never store Firebase tokens client-side beyond the one-time exchange.
- No dark patterns (§29.2): no countdowns, no guilt copy, close always visible.

## Commands
- Dev: `pnpm --filter web dev` (http://localhost:3000/en) · Build: `pnpm --filter web build`
- Lint: `pnpm --filter web lint` · Types: `pnpm --filter web typecheck`
