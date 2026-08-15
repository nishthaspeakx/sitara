# Sitara — the demo runbook

**One document. Start the stack, sign in, walk every screen.** This supersedes
`demo-walkthrough.md`, `notifications-walkthrough.md` and
`live-call-verification.md`; where those went deeper on one subsystem, this
says so and points at them.

You should be able to hand someone your laptop and follow this without hitting
a dead end. Where a path is not built, §9 says so **before** they find it.

---

## What is real

Everything on the main path. The astrology is Swiss Ephemeris via
`sitara-astro`; Tara's replies come from Anthropic through §9's full pipeline;
her voice is Cartesia. Nothing on this path is stubbed, mocked or replayed.

Three things are **not** real and the app says so on screen:

| | what it is | where the app admits it |
|---|---|---|
| **Payments** | a simulator — no rail has an account or a key | "Demo mode — no money moves" on every payment screen |
| **The festival calendar** | no vendor is reachable (§9.2) | S17 says it could not check, rather than "no festival today" |
| **WhatsApp** | declared, not implemented | the notification matrix shows it as unavailable |

### Verified on 15–16 August 2026

The 16 August pass drove **96 route-loads — 32 routes × 3 locales — all 200**,
plus every dynamic segment with deliberately bad input. Six defects were found
and fixed; two are recorded as gaps in §9. The full log is
[`PROTOTYPE-CHECKLIST.md`](PROTOTYPE-CHECKLIST.md).

### Verified on 15 August 2026

Walked against the live stack, and the quoted text is what was on screen:
sign-in, S12's voice preview (all three locales, plus the pronunciation-fix
loop), Today with its full panchang and timings in all three locales, S17's
festival state, S30 for all three personas, and gifting end to end including
§10-20's cross-currency case.

**Not exercised in that run, and marked again in place below:** Ask Tara's chat
turn, voice notes (needs a real microphone), the Journal/Vault/Family screens,
night reflection, live calls, and notification delivery. Those have their own
suites and, for calls and notifications, their own runbooks. The Hindi and
Hinglish **screens** were checked through their served payloads rather than
clicked end to end.

---

## 1. Start the stack

Five processes. Run each block from the repo root.

**a. Infrastructure** — Mongo on 27018, Redis, the astrology engine on 8003,
and Mailpit (the demo's mail server) on 8025:

```bash
docker compose -f infra/docker-compose.dev.yml up -d mongo redis astro mailpit
```

**b. The API** (8001):

```bash
cd services/api && uv run uvicorn sitara_api.main:app --port 8001 --reload
```

Wait for **both** banners. Without them, sign-in will not work:

```
PROTOTYPE MODE is ON (dev only). Calls and Stories are forced on …
AUTH_DEV_BYPASS is ON — Firebase is not consulted. Seeded personas: …
```

Both come from `services/api/.env`, which is git-ignored and sets
`AUTH_DEV_BYPASS=true` and `SITARA_PROTOTYPE=1`. Neither is a shipped default —
`DevPhoneVerifier` refuses to construct outside `environment=dev`, and
`prototype.assert_safe` raises at boot anywhere else.

**c. The realtime service** (8002 — the chat and call sockets):

```bash
cd services/realtime && uv run uvicorn sitara_realtime.main:app --port 8002
```

**d. The web app** (3000):

```bash
cd apps/web && pnpm dev
```

It must print `Environments: .env.local`. That file sets
`NEXT_PUBLIC_AUTH_ADAPTER=fake`, which swaps **only** the Firebase round trip —
the §34.5 exchange, the §22.4 age gate and the session cookies are all the real
code path.

**Health check** — all four should answer:

```bash
for p in 8001 8002 8003; do curl -s http://127.0.0.1:$p/healthz; echo; done; curl -s -o /dev/null -w "web %{http_code}\n" http://localhost:3000/en
```

> Use **`localhost`**, not `127.0.0.1`, for the whole demo. Session cookies are
> first-party to one origin, and mixing the two names signs you out halfway
> through.

---

## 2. Load the data

Two commands. The first creates the six personas; the second gives them a past.

```bash
cd services/api && uv run python -m sitara_api.db.seed --wipe
```

```bash
cd services/api && uv run python -m scripts.seed_demo_history --days 6
```

The second takes a few minutes — it runs §7.1's **real** pipeline once per day
per persona, so the briefs in the Journal are briefs the ranking engine
actually produced. From the 15 August run:

```
seeded demo history:
   36  briefs
   18  reflections
   36  memories
    2  family_charts
    6  saves
```

**Third, give them a conversation with Tara.** This one needs the API already
running, because it posts real turns through §9 — so every citation in the
seeded thread is one the grounding validator actually produced:

```bash
cd services/api && uv run python -m scripts.seed_demo_chat
```

It logs `panchang provider divineapi rejected the request (404)` and
`prokerala … (400)` as it goes. **That is the two dead vendors degrading
exactly as §8 designs** — Layer A carries on and the briefs are complete. See
§9.2.

---

## 3. The three personas

**Use the persona whose own locale matches the URL.** The account's stored
locale is what §7.1 composes in, and signing a Hindi account in at `/en`
rewrites her locale — leaving six days of Hindi history under English chrome.

| Persona | Phone | Locale | Start at | Why her |
|---|---|---|---|---|
| **Ritu** | `+919999900003` | English | `/en` | diaspora (New York), **no birth time** → Moon-chart mode, annual USD |
| **Meera** | `+919999900002` | Hinglish | `/hi-Latn` | Mumbai, **day 5 of trial** → §28.2's trial pill |
| **Lata** | `+919999900006` | हिन्दी | `/hi` | Lucknow, monthly ₹ — the Devanagari surface |

The OTP is always `123456`.

Three more exist for edge states: **Asha** (`…01`, hi, Jaipur, exact birth time,
a family with a mother and daughter), **Kavita** (`…04`, en, London, trialing),
**Divya** (`…05`, hi-Latn, Dubai, **expired** → §28.2's free variant).

> A fresh browser profile or incognito window **per persona**. Sessions are
> httpOnly cookies on one origin, so two personas in one window fight over them.

---

## 4. Onboarding — the first three minutes (S01–S13)

Seeded personas still walk onboarding, so this path is live. Open
**http://localhost:3000/en**.

1. **S01 Launch.** Tara's portrait over a constellation, **"Tara · AI guide"**
   beneath it, **Skip** top-right. That disclosure is permanent and appears
   wherever her name or face does (CC-008).
2. **S02 Language.** Three languages are selectable; the other five read
   *"Not available yet"* and are **not buttons** — §2.4 ships a language 100% or
   not at all. Tap **English**.
3. **S03/S04 Sign in.** `+919999900003`, **Continue**, `123456`, **Verify**.
4. **S05 Consent.** Three cards. The first two say *"Needed for Sitara to work
   at all"*; marketing is **off** by default.
5. **S06–S08** birth date and place, time accuracy (*"I don't know"* is a
   first-class answer that puts her in Moon-chart mode and says so), current city.
6. **S09–S11** interest level, name, up to three priorities.

### 4.1 S12 — Tara says your name ✦ *this is the ceremony*

Tap **"Hear her say it."**

→ Tara speaks, in the account's own language, using the name on the account.
The line is a catalog string resolved server-side; the only thing that varies
is the name. There is **no way for this screen to send text to the
synthesiser** — the endpoint takes no text parameter at all, which is the same
guarantee §25.3's holding phrase is built on, so a model draft can never reach
the vendor unvalidated.

Then tap **"That's not how it sounds."**

→ A field opens: *"Write it the way it's said, not the way it's spelt. Only
Tara's voice uses this — your name stays as you wrote it everywhere else."*
Type something like `Ree-too` and tap **Try it**. She says it back the new way.

**Point at the second half of that sentence.** §2.4-6 stores a phonetic
override on the profile; §3.4 sends it to the synthesiser and **nowhere else**.
Her thread, her brief and her journal keep the name she actually wrote — a
respelling that leaked into a transcript would put a stranger's spelling of
someone's own name into their own history.

**"Say it as written"** clears it. That is its own control rather than an empty
save, because *"say it as written"* is a decision, and a user who has to erase a
field to express one cannot tell whether it took.

7. **S13 First reading.** Three sentences computed from the chart just entered,
   then *"Computed from your chart · one source available today"* and a
   **Verified — limited** chip, then a memory chip — *"Shall I remember this?"* —
   which is §32.4's only path into the vault. Tap **Yes, remember**, then
   **Meet your mornings**.

---

## 5. Today (S14) and its three sub-screens

→ The date, Tara's one line, then the cards. From the 15 August run, as Ritu:

- header **Saturday, August 15** with **Shukla paksha 3**
- Tara's line: *"The afternoon carries Uttara Phalguni with it."*
- **Energy of the day** — *Today runs on Shukla paksha, tithi 3.*
- **Moon & nakshatra** — *The Moon sits in Uttara Phalguni today.*
- **Favourable window** — *There's a good window between 12:32 and 13:27.*
- **Window to go gently** — *Rahu Kaal runs 09:33 to 11:16 — worth stepping around.*
- **Colour**, **Priorities**, **What to avoid**

Worth pointing at:

- Every card carries a **confidence chip**. Nothing claims more than it knows.
- Exactly one card is visually dominant — §28.2's core-card rule.
- **Why this?** appears on every astrological claim and never on a claimless one.
- Ritu has **no** *Your chart today* card, because she has no birth time. Meera
  and Lata do. That is §5.4 choosing honesty over a fuller screen.
- Those Rahu Kaal times are **New York's**. Meera's are Mumbai's, Lata's are
  Lucknow's. §30.2: the place is never implied.

**Tap "Why this?"** on any claim → §30.4's three layers: the plain claim, the
sources row with its chip, and **See the details**. No fact IDs are visible
anywhere; §30.4 keeps those internal.

**Tap the panchang row** → **S16 The day's timings**: a bar with an amber
**Rahu Kaal** band and a green auspicious band, each with a glyph *and* a label
— never colour alone — under *"Timings for New York"*.

**S17 — `/today/festival`.** This is worth slowing down for:

> Sitara couldn't reach the festival calendar today, so she won't say either way.
> The day's timings and your reading are computed here, and are unaffected.

**It does not say "no festival today", and that is the point.** Both almanac
vendors are down (§9.2). Layer A — our own engine — is authoritative for the
astronomy and knows nothing about the calendar: a tithi does not tell you
whether it is Raksha Bandhan. §5.3 forbids fabricating a festival date, and
asserting that *no* festival falls today is the same calendar claim inverted.
So the screen says which of the two absences it is looking at.

**S24 — `/today/reflection`** *(not exercised in the 15 Aug run)*. After 20:00
local this takes over the Today tab. Three prompts in the order the **server**
gave, a mood row of five plain states — no 1–10 scale — and **Close the day**.
There is no streak, no counter and nothing to break (§29.2, §10-17), and that
absence is enforced structurally: the dataclass, the service surface and the
stored document have no field a streak could live in.

---

## 6. Ask Tara (S18)

Tap **Ask Tara**. Her portrait, the AI-guide label, *"here for you"* — and no
"online" or "last seen", which §25.4 rejects as theatre.

*(Chat turns were not exercised in the 15 Aug run — the socket path has its own
suite, `apps/web/tests/ask-socket.spec.ts`, against a real WebSocket server.)*

1. Tap a suggestion chip. → A single ✓ (delivered to Tara — there is
   deliberately no second tick), *"Tara is typing…"*, then a real answer with
   real windows and a **From tradition** chip.
2. Ask something she cannot know — *"what will my salary be next year?"* → she
   declines rather than inventing. Every astrological claim has to cite an
   engine fact or it never leaves the pipeline.
3. **Voice note** *(needs a real microphone)*: press and hold the mic. The
   original bytes are stored encrypted for 30 days under their own key class;
   the reply is a separate asset; replay plays **your** bytes, never a
   re-synthesis.

> **Live calls** are behind §33.5's gate. `SITARA_PROTOTYPE=1` makes the button
> render — English only, because CC-010 makes Hindi and Hinglish calls
> explicitly unavailable rather than routing them to an English recogniser.
> The full call script is `live-call-verification.md`.

---

## 7. Journal, Vault, Family

*(Not exercised in the 15 Aug run; covered by `apps/web/tests/journal-*.spec.ts`
and `you-*.spec.ts`, and by the M10 section of `apps/web/CLAUDE.md`.)*

- **Journal (S21–S23)** — a real timeline, newest first. The tithi sequence runs
  backwards correctly through the amavasya; that is real astronomy, not filler.
  Search is keyword + filters; natural-language search is P1 and the Atlas index
  is a known scale ceiling (`journal.atlas_search`).
- **Vault (S25/S26)** — each note with its §32.4 type and a consent stamp. Two
  deliberately unlike controls: a **toggle** to set a note aside (reversible),
  and a **button** to forget it. The confirm sheet states what it **keeps**:
  *"Anything already written in your journal stays exactly as it is."* Then go
  and show the journal is untouched.
- **Family (S27/S28)** — the North Indian diamond drawn from engine facts, with
  every house also in words (which is what a screen reader and a 320px phone
  get). Tap **South Indian**: the rashis become fixed and the houses move.
  Neither style is a fallback for the other.
- **The memorial sheet (§45.3)** — appears at exactly one moment, and the
  non-destructive option is **first, by rule**: *"Nothing is deleted. Not one
  detail, not one note, not one line of your journal."* One thing changes —
  Tara stops bringing their birthdays as dates coming up. It is reversible.

---

## 8. Money — subscription and gifting

**Nothing here moves money.** Every screen says so.

### 8.1 The states (S30)

`/you/subscription`. Ritu is annual USD, Lata monthly ₹, Meera on day 5 of a
trial, Divya expired. The dev surface drives the rest through the **real** state
machine:

```bash
# where you are
curl -s -b cookies.txt localhost:8001/v1/dev/payments/state | jq
```

- **Fail the next renewal** → §22.13's grace begins, and the point of the screen
  is what does *not* change: *"Nothing has changed — you have everything until
  20 August, and one tap fixes it."* Full access, seven days.
- **Advance 8 days** → read-only. *"Your memories are safe."* Her journal, vault
  and past guidance stay readable; new guidance pauses.
- **Recover** → active, and **the renewal date does not move**, because the
  billing anchor is the original period end rather than the day the retry landed.

`advance` shifts the row's own timestamps, never the process clock, so §7.1's
scheduler and §32.13's date binding are untouched.

### 8.2 Gifting (S32/S33) — including §10-20's NRI case

`/you/gift` → pick a term → **Buy this gift**.

→ A code: `SITARA-XXXX-XXXX`, with *"Send it to them however you like — Sitara
doesn't message anyone on your behalf."*

**There is no recipient field, and that is the design.** A gift is a bearer
instrument. An email or phone box here would make this a flow that messages a
third party who has no account and agreed to nothing.

Now open **`/gift/<code>`** — the code prefills from the URL, and the field
stays editable for someone who was read it down a phone line.

**The branch worth demoing:** buy as **Ritu** (international, USD) and redeem as
**Lata** (active, ₹). From the 15 August run:

> Added to your subscription.
> The giver paid **$99**.
> Your subscription now runs to 15 July 2028.

Her currency stays **INR**, her plan stays **monthly**, her region stays
**india** — and her period moves out by a year. §30.3 forbids mid-cycle
conversion in four separate sentences, and the way both stay true at once is
that what crosses between them is **time**, which has no currency. There is no
exchange rate anywhere in the package; a test greps for one.

Try a used code and a made-up one: both give the **same** warm refusal. A
response that distinguished them would be an oracle for enumerating bearer
instruments.

---

## 9. Known gaps — say these before someone finds them

Seven. None of them blocks the path above.

### 9.1 No payment rail is wired

§30.3 specifies Razorpay for India (₹, GST-invoiced) and Stripe India for the
diaspora (USD, zero-rated export under LUT). Neither has an account, a key or an
adapter; everything above runs against `payments.providers.simulator`. What is
missing is mostly **not code**: KYC'd accounts for the Indian entity, keys in
Secrets Manager, price catalogues, the UPI Autopay cap against RBI limits, SCA
on the Stripe side. The code is one capability-matrix cell per rail plus an
adapter — `payments/service.py` does not change, because it has never known
which rail answered. Release gate `payments.live_rails`.

The GST invoice **split** also needs a rate finance has not supplied
(`payments.gst_invoice_rate`). Prices display correctly without one: §22.1 makes
international billing zero-rated and the ₹ prices are declared tax-inclusive.

### 9.2 Both panchang vendors are down — diagnosed 15 Aug 2026

Neither is a code fault and neither is fixable from this repo:

- **Prokerala** — credentials are **alive**. `POST /token` returns 200 and a
  January 2026 query returns real data. The account is on the **sandbox tier**,
  which answers `1004 — "In sandbox mode, only January 1st is allowed"` for
  every other date. It can never serve today. **Needs a paid plan.**
- **DivineAPI** — every documented path, every plausible alternate, and every
  `astroapi-N` host returns a Laravel HTML **404**. A deliberately invalid key
  returns the *identical* 404, so the request never reaches an auth check: the
  routes do not exist for this account. **Needs the vendor's dashboard** to
  confirm the account's real base URL and provisioning.

**What you lose:** only the calendar layer — festival dating and regional
variants. §5.2's Layer A is our own Swiss-Ephemeris engine and is authoritative
for the deterministic astronomy anyway, so tithi, nakshatra, sunrise, Rahu Kaal
and every timing window are computed locally and are correct. The one visible
consequence is S17, and it now says so honestly rather than claiming no
festival falls today.

`muhurat` has no internal rung by design (§5.2 does not reimplement a muhurat
finder), so a typed muhurat query declines rather than guessing.

### 9.3 Conversation deletion has no screen

The other three §30.5 deletion scopes are built and demoed above. The API has
the **consequence** endpoint (marking memory provenance removed) but nothing
that deletes a conversation, and wiring the sheet to the consequence alone would
promise a deletion, return 200, and quietly corrupt the provenance of memories
she kept. Recorded in code as `CONVERSATION_DELETE_IS_UNBUILT`, with a test that
fails on the commit that builds it. Its home is S36 `/you/privacy`.

**Nothing in the UI offers it** — audited 15 Aug 2026. No chat overflow entry,
no menu item, no disabled control.

### 9.4 Stories are dark

§30.6 makes Stories a P1 flag with the ring hidden in P0. Prototype mode flips
`stories_enabled`, but **the ring still does not render** and there is nothing to
tap: `StoryRing` requires a story *state* that no payload field can supply, and
`TodayState` carries no such field. So the flag moves and the surface stays
dark. **No dead affordance** — audited 15 Aug 2026.

Likewise `/you` names privacy as a **sentence** rather than a greyed row, and the
paywall's restore-purchase control is not rendered at all rather than shown
disabled: where an action cannot happen, no control for it exists.

### 9.5 Ask Tara opens on an empty thread every browser session

S18 mints a fresh `conversation_id` into `sessionStorage` and never asks the
server which conversation the account has, so **a returning user sees none of
their history** — and the seeded thread is invisible. §28.3 gives an account
ONE history; this is the client not reading it.

Two parts, and only one is small. The id is a short fix. Rendering historical
turns **with citations** is not: `present_citations` needs `cited_sentences`,
which §6.4 does not persist, and re-deriving which sentences are claims at read
time would be a second implementation of "what is a claim" — the thing
`apps/web/CLAUDE.md` forbids the client from doing, for exactly the reason it
would disagree where it matters. Persisting `cited_sentences` is a §6.4 change
and a §31.3 decision.

**In the demo:** ask Tara a question live rather than pointing at history. The
reply takes ~17 s (see §11) and is masked by the typing indicator.

### 9.6 Hinglish grounding is flakier than English or Hindi

Seeding the same Hinglish question twice produced a cited answer once and §9's
safe fallback the other time — *"I'm not confident enough in that answer, so I
won't guess."* That is the validator working, not failing: she declines rather
than inventing. But it is more frequent in `hi-Latn` than in `en` or `hi`, and
a demo that asks a Hinglish question may get the decline.

Ask **"Aaj kaunsa nakshatra chal raha hai?"** in Hinglish — it grounds
reliably. Timing questions are the flaky ones.

### 9.7 Live calls are gated

§33.5 ships calls **only if** six measures pass. Two are **blocked** — with no
Indic streaming recogniser there is nothing to intercept and nobody to rate —
and four are **unmeasured**. The prototype switch turns the feature on locally;
it does not turn the gate green:

```bash
cd services/api && uv run python -m sitara_api.voice.call_gate   # prints: DOES NOT PASS
```

**14 release gates are open overall.** Four of them wait on the one §14 named
native reviewer. Run the truth rather than quoting this line:

```bash
cd services/api && uv run python -m sitara_api.release_gates
```

---

## 10. Notifications (§23)

Full script: **`notifications-walkthrough.md`**. In one paragraph: push is the
real RFC 8291/8292 protocol against a keypair we generate (web push needs no
vendor account — the push service is the browser's own), email is real SMTP to
**Mailpit at http://localhost:8025**, and WhatsApp is declared and gated.

Once, before the first run:

```bash
cd services/api && uv run python -m sitara_api.notifications.vapid --generate
```

Then bring up the delivery worker and open **`/en/you/settings/notifications`**
(S41 — §23.5's matrix):

```bash
docker compose -f infra/docker-compose.dev.yml up -d worker-notify beat
```

The one thing to point at: **no notification interpolates an astrological
claim**. §5.3's cite-or-die does not run on a push payload, so a claim on a lock
screen would be the one uncited sentence in the product. A push says the brief
is ready; the claim lives behind the deep link, where the validator runs.

---

## 11. How fast it actually is

Measured on the live stack, 16 Aug 2026. Say the third line out loud before
anybody waits in silence.

| Interaction | Observed | What covers the wait |
|---|---|---|
| Sign in | **0.01 s** | — |
| Today, first open of the day | **6.4 s** | the S14 skeleton |
| Today, thereafter | **0.01 s** | — |
| **A chat reply** | **~17 s** | "Tara is typing…" |
| S12 voice preview | **0.95 s** | button spinner |
| Brief read-aloud (≈25 s of speech) | **2.9 s** | player spinner |

**Seventeen seconds is normal, not a hang.** §9 runs several model round-trips
in series — intent, generation, then the grounding pass, with one corrective
regeneration available. That is the cost of cite-or-die, and it is the reason
§25.3's holding phrase exists on the call path. Tell people what she is doing
and the wait reads as care rather than as a stall.

---

## 12. If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Sign-in rejects the OTP | API started without `AUTH_DEV_BYPASS` | check for the banner; restart the API |
| Signed out halfway through | you mixed `localhost` and `127.0.0.1` | pick one origin and stay on it |
| Every screen shows *"Tara will be right back"* | API down, or persona not seeded | `curl :8001/healthz`; re-run the seeder |
| Today has no panchang and only two cards | the profile has no `brief_place` | re-run `db.seed --wipe` (this was a real seeder defect, fixed 15 Aug) |
| Subscription screen errors | seeded rows predate M11's vocabulary | re-run `db.seed --wipe` (same fix) |
| Journal and vault are empty | `seed_demo_history` was not run | run it (§2) |
| Today spins ~20s on first open | the brief is generating live | expected, once per persona per day |
| Chat never replies | `ANTHROPIC_API_KEY` missing, or realtime down | check `services/api/.env` and `:8002/healthz` |
| Hindi screens show English content | you signed a Hindi persona in at `/en` | use the table in §3 |
| S12 says the voice is unavailable | `CARTESIA_API_KEY` missing, or the persona has no name | check `.env`; re-seed |

---

## 13. Reset between demos

```bash
cd services/api && uv run python -m sitara_api.db.seed --wipe \
  && uv run python -m scripts.seed_demo_history --days 6 \
  && uv run python -m scripts.seed_demo_chat
```

(The chat seeder needs the API up — it posts real §9 turns.)

`--wipe` removes only documents marked `synthetic: true`, so hand-made test data
in the same database is left alone. Clear cached briefs too if you want a fresh
generation on open:

```bash
docker exec sitara-dev-mongo-1 mongosh --quiet sitara --eval 'db.daily_briefings.deleteMany({})'
```
