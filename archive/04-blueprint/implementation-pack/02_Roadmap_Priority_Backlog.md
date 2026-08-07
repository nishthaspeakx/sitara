# Roadmap · Feature-Priority Matrix · Sprint Backlog

## Phase roadmap (Mermaid)
```mermaid
gantt
  title Sitara/Tara delivery roadmap
  dateFormat  YYYY-MM-DD
  section Discovery
  Interviews+concierge      :2026-08-04, 21d
  section Design
  Flows+system+convo design :2026-08-11, 28d
  section Build
  Auth+profile              :2026-08-25, 14d
  Chat+memory               :2026-09-01, 28d
  Safety system             :2026-09-08, 21d
  Brief+night loop          :2026-09-22, 21d
  Subs+notifications        :2026-10-06, 14d
  Admin+analytics           :2026-10-13, 14d
  section Test
  Safety red-team+load      :2026-10-20, 21d
  section Launch
  Closed beta 100           :milestone, 2026-10-27, 0d
  Paid pilot 500            :milestone, 2026-11-17, 0d
  Public beta US iOS        :milestone, 2026-12-22, 0d
```

## Feature-priority matrix (value × effort, Phase 1)
| Feature | Value | Effort | Priority |
|---|---|---|---|
| Morning brief | Very high | M | P0 |
| Chat + framework router | Very high | L | P0 |
| Consent memory + centre | Very high | L | P0 |
| Safety system | Existential | M | P0 |
| Night reflection | High | S | P0 |
| Subscription + trial | High | M | P0 |
| Notifications + controls | High | S | P0 |
| Astro/numerology layer | High | M | P0 (engine v0 via API) |
| Goals | Med | S | P1 |
| Weekly summary | Med | S | P1 |
| Voice notes | Med | M | P1 |
| Mood trends | Med | S | P2 |
| iOS widget | Med | S | P2 |

## Sprint 1–2 backlog (2-week sprints, 2 eng + 1 AI eng)
S1: repo+CI+infra bootstrap · Firebase auth + user/profile service · onboarding screens (essential ring) · Prokerala engine adapter + chart compute · prompt registry + Tara persona v1 · safety classifier integration (vendor baseline) · PostHog events v0. Exit: signup→chart→first insight E2E on TestFlight.
S2: chat service + streaming + framework router (morning/emotional/decision) · memory write path + chips + centre v0 · brief generator job + brief UI · notification service + quiet hours · golden-convo suite v1 (100 cases). Exit: full day-loop dogfood internally.
S3–7 (headline): night flow; subscription; memory centre full; safety red-team + crisis UX; weekly summary; admin v0; beta hardening.
