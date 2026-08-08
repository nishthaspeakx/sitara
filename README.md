# Sitara ✦ — build repo

**Tara, the astrology-first AI life guide.** Morning brief · Ask Tara · night reflection — grounded in a deterministic Vedic astrology engine, in the user's own language.

> *"Every morning, Tara helps you understand the energy of your day. Throughout the day, she helps you think through decisions and problems. Every night, she helps you reflect, remember and prepare for tomorrow."*

## Source of truth

| What | Where |
|---|---|
| **The spec (law)** — Canonical Specification, FROZEN **v3.5** | [`docs/spec/SPEC.md`](docs/spec/SPEC.md) + [`docs/spec/diagrams/`](docs/spec/diagrams/) |
| **The build plan (how)** — milestone-by-milestone | [`CLAUDE_CODE_PLAYBOOK.md`](CLAUDE_CODE_PLAYBOOK.md) |
| **Non-negotiables** — carried into every session | [`CLAUDE.md`](CLAUDE.md) |
| **Program decision trail** — research, board pack, competitive, blueprint, superseded specs | [`archive/`](archive/) |

The spec says WHAT; the playbook says HOW. Prompts cite section numbers like statutes (e.g. "per §7.1"). Any change to a frozen decision requires a §31.3 change-control entry — do not change one silently.

## Status

- **Part 1 — repository & memory setup:** ✅ complete (`CLAUDE.md`, five `.claude/commands/`, spec + diagrams, `.env` git-ignored).
- **M0 — monorepo walking skeleton:** ✅ complete — three FastAPI services with `/healthz`, Next.js 15 web in three locales, frozen contracts in `packages/schemas`, §24.2 tokens (both themes), CI.
- **M1 — identity & auth (§33.2/§34.5):** ⏳ next (playbook Prompt P2).

## Run it

Prereqs: Node 22 (+corepack/pnpm), [uv](https://docs.astral.sh/uv/), Docker Desktop (for the compose path only).

```bash
pnpm install
pnpm build          # builds tokens → web (turbo)
```

**Services** (each in its own terminal, or use compose):

```bash
cd services/api && uv sync && uv run uvicorn sitara_api.main:app --port 8001 --reload
```

```bash
cd services/realtime && uv sync && uv run uvicorn sitara_realtime.main:app --port 8002 --reload
```

```bash
cd services/astro && uv sync && uv run uvicorn sitara_astro.main:app --port 8003 --reload
```

**Web:**

```bash
pnpm --filter web dev   # http://localhost:3000/en · /hi-Latn · /hi
```

**Everything at once (needs Docker):**

```bash
docker compose -f infra/docker-compose.dev.yml up
```

**Checks** (what CI runs):

```bash
pnpm lint && pnpm typecheck && pnpm build && pnpm token-lint && pnpm i18n-lint
```

Layout: `apps/web` · `services/{api,realtime,astro}` · `packages/{schemas,tokens,i18n}` · `infra/` · `golden-set/`. Each package carries its own `CLAUDE.md` contract.

---
*Confidential — Ivypods / Sitara founding team & board. Do not distribute.*
