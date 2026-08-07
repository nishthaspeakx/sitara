# Repository Structure (pnpm + Turborepo monorepo)
```
sitara/
├─ apps/
│  ├─ mobile/            # Expo RN (iOS first). src/{app,components,features,hooks,lib}
│  ├─ web/               # Next.js marketing + web app
│  └─ admin/             # Next.js admin (role-gated)
├─ services/
│  ├─ api/               # NestJS modular monolith
│  │  └─ src/modules/{auth,profile,family,conversation,memory,briefing,
│  │     astrology,numerology,notification,subscription,safety,analytics,admin}
│  ├─ vedic-engine/      # Swiss Ephemeris wrapper (isolated svc; TS/Rust)
│  └─ jobs/              # BullMQ workers: brief, memory-extract, summaries, notif-decide
├─ packages/
│  ├─ shared/            # types, zod schemas, api client, constants
│  ├─ prompts/           # versioned prompt registry + eval fixtures + banned-phrase list
│  └─ ui/                # shared RN/web design tokens + components
├─ evals/                # golden convos, adversarial safety suite, astro-grounding, runners
├─ e2e/                  # Maestro flows, k6 load scripts
├─ infra/                # Terraform (envs/, modules/), GitHub Actions workflows
├─ docs/                 # this pack, ADRs, runbooks
└─ turbo.json · pnpm-workspace.yaml · .github/workflows/{ci,deploy}.yml
```
Conventions: trunk-based; feature flags over long branches; conventional commits; ADRs for irreversible choices; CODEOWNERS (safety/ and prompts/ require safety-specialist review); prompts are code (PR + evals, never hot-edited except via gated admin publish).
