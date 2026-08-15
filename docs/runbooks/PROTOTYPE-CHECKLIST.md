# Prototype verification — the exhaustive checklist

Every user-facing case in the product. Worked top to bottom against the real
stack in a real browser, in `en` / `hi` / `hi-Latn`, light and night.

**Status key:** `PASS` observed working · `FAIL` observed broken (→ fixed, with
the fix named) · `GAP` deliberately unbuilt, listed in the runbook's known gaps
· `N/A` not reachable in this build, with the reason.

> A passing test suite is not evidence for anything in this file. Every status
> here is something that was opened, clicked or measured.

---

## A. Onboarding (S01–S13)

| # | Case | Branches to check |
|---|---|---|
| A1 | S01 launch `/` | animation plays · **Skip** works · "Tara · AI guide" present · already-signed-in redirects to Today |
| A2 | S02 language `/start/language` | 3 selectable · 5 read "Not available yet" and are **not** buttons · pre-auth (no session) must not 401 · tap advances |
| A3 | S03 auth `/start/auth` | phone accepted · bad phone rejected in-locale · Google button state · 18+ hint |
| A4 | S04 verify `/start/verify` | `123456` accepted · wrong code rejected · resend timer · change number |
| A5 | S05 consent | two required, marketing OFF by default · policy links · continue |
| A6 | S06 birth details | date picker · place typeahead → tz resolve · empty place declines |
| A7 | S07 birth time | 4 accuracy options · "I don't know" → Moon-chart mode and says so |
| A8 | S08 current city | typeahead · permission-optional path |
| A9 | S09 interest register | 3 cards → density |
| A10 | S10 name + numerology | name accepted · transliteration confirm · moolank reveal |
| A11 | S11 priorities | ≤3 chips enforced |
| A12 | S12 voice preview | **plays real audio** · fix-pronunciation opens · save + replay · clear · unavailable state honest |
| A13 | S13 first reading | 3 sentences from the chart · confidence chip · memory chip → vault · "Meet your mornings" |
| A14 | Resume mid-flow | refresh at each step returns to the same step, not the start |
| A15 | Back from every step | back always works, never dead-ends |

## B. Today (S14) and its sub-routes (S15–S17, S24)

| # | Case | Branches |
|---|---|---|
| B1 | S14 `/today` happy | date · tithi · Tara's line · cards · confidence chips · exactly one dominant card |
| B2 | S14 brief read-aloud | player renders · plays real audio · unavailable state |
| B3 | S14 first-session variant | no brief yet — designed empty, not a blank screen |
| B4 | S14 degraded variant | provider degraded reads honestly |
| B5 | S14 night takeover | after 20:00 the tab transforms; reflection CTA replaces the core card |
| B6 | S15 `/today/timings` | bar + bands with glyph AND label · place named · empty state |
| B7 | S16 `/today/festival` | festival present → banner + reckoning · **absent → "couldn't check", never a false negative** |
| B8 | S17 `/today/brief/[card]/why` | three distinct layers · no fact IDs visible · unknown card slug |
| B9 | S24 `/today/reflection` | 3 prompts in server order · mood row · keep · persists on reload · **no streak anywhere** |
| B10 | Tab bar | all four tabs reachable from every screen |

## C. Ask Tara (S18) and the call (S19)

| # | Case | Branches |
|---|---|---|
| C1 | S18 `/ask` empty | suggestion chips · no "online"/"last seen" |
| C2 | S18 send a chip | single ✓ · typing · real reply · citations underlined |
| C3 | S18 unanswerable question | declines rather than inventing |
| C4 | S18 socket drop | bubble fails honestly with retry, not stuck "sending" |
| C5 | S18 voice note | hold-to-record → transcript → reply in text and audio |
| C6 | S19 `/ask/call` en | grant · connect · captions · mute · end |
| C7 | S19 call hi/hi-Latn | prototype bridge label visible · honest refusal when no recogniser |
| C8 | S39 `/support/now` | safety takeover renders; exits only to Ask or Help |

## D. Journal (S21–S23)

| # | Case | Branches |
|---|---|---|
| D1 | S21 `/journal` | timeline newest-first · previews present · empty state |
| D2 | S22 `/journal/[date]` | one date wide · bad date slug |
| D3 | S23 `/journal/search` | keyword hit · no hit · filter chips · resolves as search, not a date |

## E. You (S25–S29, S35, S41)

| # | Case | Branches |
|---|---|---|
| E1 | S29 `/you` | rows navigate · no disabled rows · honest sentence for unbuilt |
| E2 | S25 `/you/memories` | list with types and consent stamps · filters · empty |
| E3 | S26 `/you/memories/[id]` | detail · set-aside toggle · forget → §30.5 sheet → journal untouched |
| E4 | S27 `/you/family` | members list · empty |
| E5 | S28 `/you/family/[id]` | **kundli renders** · North/South switch · no-lagna state · memorial sheet |
| E6 | S41 `/you/settings/notifications` | §23.5 matrix · toggles persist |

## F. Money (S30–S34) and gifting (S32/S33)

| # | Case | Branches |
|---|---|---|
| F1 | S30 `/you/subscription` | status · dates · simulator disclosure |
| F2 | S31 `/you/subscription/checkout` | price cards · total incl. tax · no countdown · close always visible |
| F3 | S34 `/you/subscription/result` | success · pending · failed |
| F4 | S32 `/you/gift` | plan select · buy · code · copy · expiry |
| F5 | S33 `/gift/[code]` | prefill from URL · activated · credit-converted · refusal (used/expired/unknown identical) |
| F6 | §22.13 ladder | grace · read-only · downgrade · recover |

## G. Cross-cutting — the ones nobody remembers

| # | Case | What must be true |
|---|---|---|
| G1 | Browser refresh mid-flow | every route survives F5 |
| G2 | Back navigation | from every screen, never a dead end |
| G3 | Session expiry | recovers transparently; **no 401 wall** |
| G4 | Second device / second tab | both work; no session fight |
| G5 | Language switch mid-session | chrome AND content follow; no mixed-language screen |
| G6 | Theme switch | light and night both legible everywhere |
| G7 | Reduced motion | animations collapse |
| G8 | Offline | cached brief + honest banner |
| G9 | Brand-new account | onboarding from S01 |
| G10 | Returning account with history | lands on Today with content |
| G11 | Console | no errors, no unhandled rejections, on every screen |
| G12 | Deep link while signed out | goes to sign-in, then returns to the target |

---

# Results — run of 16 August 2026

Driven against the live stack in a real browser. Every line is something that
was opened, clicked or timed.

## Route sweep

**96 route-loads — 32 routes × 3 locales — all HTTP 200.** No 404, no 500, no
blank screen at the server-render level.

Dynamic segments and bad input, tested by hand:

| Input | Before | After |
|---|---|---|
| `/en/journal/2026-08-14` | 200 | 200 |
| `/en/journal/not-a-date` | **500** | 200, honest message |
| `/en/journal/2026-02-31` | 500 | 200, honest message |
| `/en/today/brief/nonsense_module/why` | 200 | 200 |
| `/en/you/memories/garbage` | 200 | 200 |
| `/en/you/family/garbage` | 200 | 200 |
| `/en/gift/SITARA-AAAA-BBBB` | 200 | 200 |
| `/en/nonexistent-route` | 404 | 404 (correct) |

## FAILs found and fixed

| # | What | Root cause | Fix |
|---|---|---|---|
| 1 | `/journal/not-a-date` → **500 in the browser** | `Intl.DateTimeFormat.format(new Date(NaN))` throws `RangeError`, inside render. A path segment is user input. | `dates.ts` formatters are now TOTAL (unformattable input returns unchanged); the route also checks `isLocalDate` first. Covers the Journal, vault consent stamps, family and every subscription date — all call these. |
| 2 | Invalid date showed the **reflection's** message | Reused `errors.reflection.bad_date` on a Journal screen — the wrong-sentence class this repo already records for `EmptyState id="saved_guidance"`. | Added `errors.journal.bad_date` in all three locales. |
| 3 | Demo personas had **no family → no kundli** | `seed.py` gave family only to asha and kavita; the three demo personas had none. | ritu, meera and lata now each have two members, one with birth details, so S28's kundli renders. Names in each persona's own script (§32.15's name match is script-sensitive). |
| 4 | Every persona had **no chat history** | Nothing seeded `messages`; the 489 rows in the collection were orphans pointing at a fixture conversation id. | New `scripts/seed_demo_chat.py` posts real turns through `POST /v1/chat/turn`, so every citation is one the grounding validator actually produced. 12 turns seeded, 9 with citations. |
| 5 | Session could expire mid-demo | 15-minute access cookie (correct default). | `prototype.access_ttl_seconds` widens to 12h in dev+prototype only. Shipped default still 900, asserted by test; refresh TTL untouched. |
| 6 | Demo-bridge label unreadable on the call screen | Laid straight onto Tara's portrait — contrast depends on the image. | Carries its own scrim, like the caption block. |

## FAIL found, NOT fixed — recorded as a gap

| # | What | Why not fixed here |
|---|---|---|
| 7 | **S18 always opens on an empty thread.** The client mints a random `conversation_id` into `sessionStorage` and never asks the server, so a returning user sees none of their history and the seeded thread is invisible. Contradicts §28.3's "one history per account". | Two parts. The id is a small fix. **Rendering historical turns with citations is not** — `present_citations` needs `cited_sentences`, which §6.4 does not persist, and re-deriving which sentences are claims at read time would be a second implementation of "what is a claim" (the thing `apps/web/CLAUDE.md` forbids the client from doing, for the same reason). Persisting `cited_sentences` is a §6.4 change and a §31.3 decision, not a demo-prep edit. |

## Timings (live, warm stack)

| Interaction | Observed | Masked by |
|---|---|---|
| `POST /auth/session` | **0.012 s** | — |
| `GET /v1/today` — first, cold | **6.39 s** | S14 skeleton |
| `GET /v1/today` — cached | **0.011 s** | — |
| `POST /v1/chat/turn` — real §9 | **16.9 s** | "Tara is typing…" |
| `POST /v1/voice/preview` | **0.95 s** | button spinner |
| `POST /v1/today/audio` (≈25 s of speech) | **2.89 s** | player spinner |

The chat turn is the one worth knowing about: §9 runs several model round-trips
in series, so **17 seconds is normal, not a hang**. It is masked by the typing
indicator, and §25.3's holding phrase exists for the same reason on the call
path. Say so before someone waits in silence.
