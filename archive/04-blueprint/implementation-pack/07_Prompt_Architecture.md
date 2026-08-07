# AI Prompt Architecture

## Layered assembly (every request)
1 SYSTEM-CORE (persona Tara: identity, values, hard boundaries incl. banned-phrase list; ~600 tokens, versioned)
2 SAFETY OVERLAY (current policy version; crisis rules; jurisdiction helplines by user region)
3 FRAMEWORK PROMPT (router-selected: 1 of 15; encodes the 7-step pattern + framework-specific structure)
4 CULTURAL LAYER (astro_depth setting; today's computed chart facts as STRUCTURED DATA with ids — the model may interpret only listed facts, must cite fact-ids in astro statements)
5 MEMORY BLOCK (retrieved memories with type+source+date; sensitive only if context-matched; hard cap 1,200 tokens, importance-ranked)
6 CONVERSATION WINDOW (last N turns, summarised beyond 20)
7 OUTPUT CONTRACT (JSON: reply, memory_suggestions[{type,content,sensitivity}], framework_exit?, tool_calls[])

## Router
Lightweight classifier (few-shot, small model) → framework selection; crisis labels bypass to crisis framework; ambiguous → general companion.

## The 15 framework prompts
morning_greeting · day_planning · emotional_support · decision_making · family_conflict · parenting_concern · work_stress · celebration_planning · food_suggestion · astro_guidance · numerology_guidance · night_reflection · weekly_review · crisis · professional_referral. Each file: objective, opening move, question bank, memory-usage rules, response structure, boundaries, 3 golden examples + 3 adversarial examples. Stored in packages/prompts, versioned, publish gated on eval suite.

## Non-negotiable output rules (linted post-generation)
- Reflective astro language only; every astro claim cites a fact-id; no predictions of health/death/money/events.
- Banned phrases (dependency/certainty/fear list, ~80 patterns) → auto-rewrite or safe template.
- Advice only after listen+clarify+reflect steps (turn-count + structure check).
- Human-connection nudge required in emotional frameworks ≥1 per 3 sessions.
- "Remember this?" suggestion max 2/session; sensitive always asks.

## Evals (blocking in CI)
500 golden conversations (framework correctness, tone rubric ≥4.3/5 by LLM-judge + weekly human sample) · 200 adversarial safety cases (≥98%) · astro-fact grounding suite (0 uncited claims) · memory-consent suite · privacy-leak suite (family probes) · regression on every prompt/model change; Langfuse traces sampled 10%.
