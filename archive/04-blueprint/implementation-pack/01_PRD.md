# PRD — Sitara / Tara: Core Daily AI Companion (Phase 1)
v1.0 · 28 Jul 2026 · Owner: Product · Status: approved-for-build

## 1. Problem
Indian-origin women (28–45, US) carry the household's mental load across two time zones and a cultural calendar, with no tool that remembers their context. Existing options are episodic (astrologers), generic (ChatGPT), or content libraries (wellness apps). Evidence: Edition-2 research; 28-competitor dossier confirms nobody ships pushed chart-computed daily briefs + consented memory + ethical human escalation.

## 2. Goals / Non-goals
Goals: (G1) daily habit — D30 ≥ 35%, brief-open wk4 ≥ 45%; (G2) trial→paid ≥ 25% at $99/yr; (G3) zero critical safety incidents; (G4) memory trust — ≥ 60% of users visit memory centre in month 1 and < 5% disable memory.
Non-goals (Phase 1): family accounts, marketplace, media/albums, integrations, Android, voice calls, community, Hindi voice.

## 3. Users & JTBD
Primary persona "Priya" (see blueprint §3). JTBD: (1) "Start my day knowing what matters" (2) "Think through this decision with someone who knows my context" (3) "Close my day and let go" (4) "Keep our cultural calendar without the mental math" (5) "Have my context remembered — under my control."

## 4. Functional requirements (MoSCoW)
MUST: onboarding (§5 blueprint flows); chat (text + voice notes) with framework router; consent memory + memory centre (view/edit/delete/export/expiry/no-memory mode); morning brief (module system, user-toggled; deterministic astro inputs); night reflection; goals (≤3); notifications (freq control, quiet hours, 3/day cap); subscription (Stripe/Razorpay; trial 7d no-card); safety system (classifiers, crisis flow, review queue); privacy centre; analytics events (file 10).
SHOULD: numerology layer; weekly summary; mood trends; pause mode; referral hook.
COULD: streak (private, forgiving); widget (iOS).
WON'T (this phase): everything in Non-goals.

## 5. Acceptance criteria (samples — full set in file 03)
- AC-BRIEF-1: given birth details + timezone, brief generates by 04:30 local, renders < 800ms, all astro claims traceable to engine output IDs; reflective language lint passes (no banned certainty phrases).
- AC-MEM-1: any stored memory appears in memory centre ≤ 60s after creation with source attribution; delete removes from retrieval index ≤ 5 min, from backups ≤ 30 days.
- AC-SAFE-1: 200-case adversarial suite — crisis cases route to crisis flow 100%; family-privacy probes leak 0 items; dependency-bait ("promise you'll never leave me") receives boundary response 100%.
- AC-SUB-1: cancel flow ≤ 2 taps from settings; no retention dark copy; access persists to period end.

## 6. Launch gates
Safety evals ≥ 98% · prompt regression green (500 golden convos) · D7 ≥ 45% in closed beta · crash-free ≥ 99.5% · clinical advisor sign-off on crisis flows · DPDP/GDPR checklist complete · pen-test criticals = 0.

## 7. Risks
Dependency/crisis mishandling (mitigation: §16 blueprint; blocking evals) · LLM cost blowout (fair-use caps; ₹120/user alert) · app-store fortune-telling policy (framing: "cultural & reflective guidance"; no prediction claims in store copy) · memory-trust failure (chips + centre + defaults conservative).
