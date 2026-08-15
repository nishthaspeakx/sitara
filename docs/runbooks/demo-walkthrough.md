# Sitara — the demo walkthrough

A script you can follow in front of someone without hitting a dead end.

**Everything on this path is real.** The astrology comes from Swiss Ephemeris
via `sitara-astro`, Tara's replies from Anthropic through §9's full pipeline,
the voice from Cartesia. Nothing here is stubbed, mocked or replayed.

**What was verified, and how.** Every screen below was opened against the live
stack on 15 August 2026 and the quoted text is what was actually on it — with
two exceptions, marked in place:

- **step 17 (voice note)** was not exercised in that run, because it needs a
  real microphone. It is covered by `tests/ask-voice.spec.ts`, which drives a
  real capture device, a real socket and real PCM.
- **steps 2.2 and 2.9** were walked in English. The Hindi and Hinglish surfaces
  were checked screen by screen but not clicked end to end in one sitting.

Where a step has never been run live, this document says so rather than
implying it has.

---

## 0. Start the stack

Four processes and one Docker group. Run each block from the repo root.

**a. Infrastructure** (Mongo on 27018, Redis, the astrology engine on 8003):

```bash
docker compose -f infra/docker-compose.dev.yml up -d mongo redis astro
```

**b. The API** (port 8001):

```bash
cd services/api && uv run uvicorn sitara_api.main:app --port 8001 --reload
```

Wait for two banners. If you do not see both, sign-in will not work:

```
PROTOTYPE MODE is ON (dev only). Calls and Stories are forced on …
AUTH_DEV_BYPASS is ON — Firebase is not consulted. Seeded personas: …
```

Both come from `services/api/.env`, which is git-ignored and sets
`AUTH_DEV_BYPASS=true` and `SITARA_PROTOTYPE=1`. Neither is a shipped default —
`DevPhoneVerifier` refuses to construct outside `environment=dev`, and
`prototype.assert_safe` raises at boot anywhere else.

**c. The realtime service** (port 8002, the chat and call sockets):

```bash
cd services/realtime && uv run uvicorn sitara_realtime.main:app --port 8002
```

**d. The web app** (port 3000):

```bash
cd apps/web && pnpm dev
```

It must print `Environments: .env.local`. That file sets
`NEXT_PUBLIC_AUTH_ADAPTER=fake`, which swaps **only** the Firebase round trip —
the §34.5 exchange, the §22.4 age gate and the session cookies are all the real
code path.

**Health check** — all four should answer:

```bash
for p in 8001 8002 8003; do curl -s http://127.0.0.1:$p/healthz; echo; done; curl -s -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:3000/en
```

---

## 1. Load the demo data

Two commands. The first creates the six personas; the second gives them a
history.

```bash
cd services/api && uv run python -m sitara_api.db.seed --wipe
```

```bash
cd services/api && uv run python -m scripts.seed_demo_history --days 6
```

The second one takes a few minutes — it runs §7.1's **real** pipeline once per
day per persona, so the briefs in the Journal are briefs the ranking engine
actually produced. Expect roughly:

```
seeded demo history:
   36  briefs
   18  reflections
   36  memories
    6  family_charts
    6  saves
```

**The three personas to demo with.** Each has its own locale, and the Journal
content is in the language the artefacts were composed in — so use the matching
one rather than switching the URL.

| Persona | Phone | Locale | URL prefix |
|---|---|---|---|
| **asha** | `+919999900001` | English | `/en` |
| **meera** | `+919999900002` | Hinglish | `/hi-Latn` |
| **lata** | `+919999900006` | हिन्दी | `/hi` |

The OTP is always `123456`.

> Use a fresh browser profile or an incognito window per persona. Sessions are
> httpOnly cookies on one origin, so two personas in one window fight over them.

---

## 2. The walkthrough

Times below are what the app showed on a mid-afternoon run; yours will differ
with the clock and the sky, which is the point.

### 2.1 Launch → sign in

1. Open **http://127.0.0.1:3000/en**.
   → Tara's portrait fades up over a constellation, with **"Tara · AI guide"**
   under it and **Skip** top-right. That disclosure is permanent and appears
   wherever her name or face does (CC-008).
2. Tap **Skip**.
   → **Choose your language.** Three languages are selectable; the other five
   read *"Not available yet"*. Point out that §2.4 ships a language 100% or not
   at all.
3. Tap **English** → **Let's begin**.
4. Enter `+919999900001`, tap **Continue**, enter `123456`, tap **Verify**.

> **If you land on Today instead of the consent screen**, this persona has
> already finished onboarding. That is fine — skip to §2.3. To show onboarding
> from the start, re-run the seeder in step 1.

### 2.2 Onboarding (steps 5–13)

5. **What you're agreeing to** — three consent cards. The first two say
   *"Needed for Sitara to work at all"*; marketing is **off** by default.
   Tap **Continue**.
6. **Where did you begin?** — date `1990-03-11`, place `Beng…` and pick
   **Bengaluru** from the live lookup. **Continue**.
7. **Do you know the time?** — pick **I know it exactly**, enter `06:20`.
   Worth saying out loud: *"I don't know"* is a first-class answer that puts
   her in Moon-chart mode and says so. **Continue**.
8. **Where are you now?** — `Beng…` → **Bengaluru**. **Continue**.
9. **How much of this do you want?** — **A bit of both**. This changes how Tara
   talks, never what is true.
10. **What should Tara call you?** — `Asha`. **Continue**.
11. **What's on your mind this year?** — pick three, e.g. Family, Health,
    Peace of mind. **Continue**.
12. **This is Tara's voice.** ⚠️ *Known gap — see §4.* The audio player shows
    *"Today's audio didn't come through"*. Skip past it: **Continue**.
13. **Your first reading.** → three sentences computed from the chart just
    entered, e.g.

    > Your Moon was in **Purva Phalguni** when you were born.
    > **Moon** sits in your seventh house — you read the room before you read yourself.
    > Today runs on **Shukla paksha, tithi 3**.

    Below them: *"Computed from your chart · one source available today"* and a
    **Verified — limited** chip. Then a memory chip — *"Shall I remember this?"*
    — which is §32.4's only path into the vault. Tap **Yes, remember**.
14. Tap **Meet your mornings**.

### 2.3 Today (S14)

→ The date, Tara's one line, then the cards. On the run this was written from:

- header: **Saturday, August 15** with **Shukla paksha 3** beside it
- Tara's line: *"The afternoon carries Uttara Phalguni with it."*
- **Your chart today** — *The Sun is passing through your 6th house today.*
- **Favourable window** — *There's a good window between 11:58 and 12:49.*
- **Window to go gently** — *Rahu Kaal runs 09:15 to 10:49 — worth working around.*
- **Energy of the day**, **Colour**, **Priorities**, **Moon & nakshatra**

Things worth pointing at:

- Every card carries a **confidence chip**. Nothing claims more than it knows.
- Exactly one card is visually dominant — §28.2's core-card rule.
- **Why this?** appears on every astrological claim, never on a claimless one.

**Tap "Why this?"** on *Your chart today*.
→ Three layers: the plain-language claim, the sources row with its chip, and
**See the details** for the specifics. No fact IDs are visible anywhere — §30.4
keeps those internal.

**Tap the panchang row** (*Shukla paksha 3*) in the header.
→ **The day's timings** (S16): a bar with an amber **Rahu Kaal** band and a
green **Abhijit** band, each with a glyph and a label — never colour alone —
under the heading *"Timings for Bengaluru"*. §30.2: the place is never implied.

Back, then visit **/en/today/festival** (S17). With no observance today it says
*"No observance falls today."* On a festival day it names the festival **and the
reckoning** (amanta or purnimanta), because the two date the same festival
differently — a date with no calendar beside it is a claim nobody qualified.

### 2.4 Ask Tara (S18)

Tap **Ask Tara** in the tab bar.

→ Her portrait, the AI-guide label, *"here for you"* — and no "online" or "last
seen", which §25.4 rejects as theatre.

15. Tap the chip **When is a good time today?**
    → A single ✓ appears (delivered to Tara — there is deliberately no second
    tick), then *"Tara is typing…"*, then a real answer with real windows:

    > … the window from 3:32 pm to 5:06 pm carries **amrit**, an auspicious
    > choghadiya … I'd gently hold you back from 5:06 pm to 6:40 pm, as that
    > falls in **kaal** …

    with a **From tradition** chip beneath. She asks what it is for rather than
    guessing.

16. Type something she cannot know, e.g. *"what will my salary be next year?"*
    → She declines rather than inventing. Every astrological claim she makes has
    to cite an engine fact or it never leaves the pipeline.

17. **Voice note** *(not exercised in the verification run — needs a real mic)*:
    press and hold the mic in the composer.
    → Speak for a few seconds, release. The recording uploads, comes back as a
    transcript, and Tara answers in both text and audio. The original bytes are
    stored encrypted for 30 days under their own key class; the reply is a
    separate asset.

> **Live calls are behind §33.5's gate** and the call button does not render.
> With `SITARA_PROTOTYPE=1` set it does — English only, because CC-010 makes
> Hindi and Hinglish calls explicitly unavailable rather than routing them to an
> English recogniser.

### 2.5 Journal (S21–S23)

Tap **Journal**.

→ A real timeline, newest first:

```
15 August 2026   Morning brief   Saved   Today's in Shukla paksha, tithi 3.
14 August 2026   Night reflection  Amma called, out of nowhere, …
                 Morning brief     Today falls on Shukla paksha, tithi 2.
13 August 2026   Night reflection  Finished the report. Nobody noticed, …
…
```

The tithi sequence runs backwards correctly through the amavasya — that is real
astronomy, not filler.

18. Tap a **date heading** → the day view (S22), one date wide.
19. Tap the **search icon** → S23. Type `lease`.
    → Keyword results, newest first. Tap a filter chip (**Saved guidance**) to
    narrow. Say plainly that this is keyword + filters; natural-language search
    is P1 and the Atlas index is a known scale ceiling.

### 2.6 Night reflection (S24)

Go to **/en/today/reflection** (after 20:00 local this takes over the Today tab).

→ Tara's night portrait, then:

> Write as little as you like. Nothing here is counted, and nothing is broken by
> a quiet night.

Three prompts in the order the **server** gave, a mood row (five plain states,
no 1–10 scale), and **Close the day**. There is no streak, no counter and
nothing to break — §29.2, and worth saying out loud.

20. Type one line into the first prompt, tap **Keep this** → *"Kept."*
    Reload the page: it is still there.

### 2.7 The memory vault (S25, S26) — including a real deletion

Tap **You** → **What Tara remembers**.

→ Six notes, each with its §32.4 type and a consent stamp — *"You agreed on
15 August 2026"*. The filter row is the eleven canonical labels.

21. Tap **Fasts on Tuesdays** → the detail (S26).
    → The note, where it came from, and two controls that are deliberately not
    alike: a **toggle** to set it aside (reversible, Tara keeps it and stops
    using it) and a **button** to forget it.
22. Tap **Forget this**.
    → The §30.5 confirm sheet:

    > **Forget this?**
    > Tara stops knowing this, and the note is deleted along with what she
    > learned from it.
    > *Anything already written in your journal stays exactly as it is — this
    > doesn't rewrite your past.*

    Point at the second sentence: every deletion in the app states what it
    **keeps**, not only what it takes.
23. Tap **Forget this**.
    → Back to the vault, now five notes.
24. **Show that the promise held:** go to **Journal** and open any day. The
    entries are untouched. Nothing about that day changed.

### 2.8 Family and the memorial path (S27, S28)

Tap **You** → **Your people**.

→ **Sunita** (Mother) and **Ira** (Daughter).

25. Tap **Sunita**.
    → *Birth details on file* · *You confirmed you may hold these* — §13's
    attestation, stated rather than assumed.
    → **Their chart**: the North Indian diamond, drawn from engine facts. House
    1 top-centre carries the **Lagna** marker; Rahu and Ketu sit exactly
    opposite. Below it, every house in words — which is also what a screen
    reader and a 320px phone get.
    → Tap **South Indian**. The layout inverts its logic: the RASHIS are now
    fixed in their cells and the houses move, with the lagna marked by a corner
    rule. Neither style is a fallback for the other — a reader of one cannot
    read the other by squinting, which is why the switch exists.
    → **What Tara has noted about them**: *Sunita's birthday is 11 March*.

26. Tap **Remove or remember**.

    **This is the sheet worth slowing down for.** It appears at exactly one
    moment — someone looking at the record of a person who has died — and the
    non-destructive option is **first**, by rule (§45.3), not by layout:

    > **Keep them in memory**
    > Sunita stays in your family, with their birth details, their chart, and
    > everything already written about them.
    > **Nothing is deleted. Not one detail, not one note, not one line of your journal.**
    > One thing changes: Tara stops bringing their birthday and anniversaries to
    > you as dates coming up, and speaks about them in the past tense.
    > *You can change this back whenever you like.*
    >
    > [ **Keep in memory** ]
    >
    > Or, if you would rather the record itself did not stay:
    > **Remove Sunita?** …

27. Tap **Keep in memory**.
    → Back on her page, an **In memory** marker. Go to **Your people**: she is
    still in the list, marked — not dimmed, not removed. §29.4 forbids carrying
    that state in colour alone, and a greyed row is the visual language of
    "disabled" applied to a person.
28. Tap **Remove or remember** again → it now offers **Return to the family
    list**, and the destructive half is still there. Both paths remain (§45.3).
29. *(Optional, destructive)* Tap **Remove Sunita**. The sheet lists the notes
    about her as **unticked checkboxes** — "about them" is a name match, which
    is a judgement, so it is shown rather than made silently. Leave them
    unticked and confirm: her chart and birth details are destroyed, the note
    survives, your journal is untouched, and the consent record is **revoked
    rather than erased** (§32.15's DPDP clause).

### 2.9 The other two locales

Repeat §2.3 → §2.8 with:

- **meera** — `+919999900002`, start at **http://127.0.0.1:3000/hi-Latn**
- **lata** — `+919999900006`, start at **http://127.0.0.1:3000/hi**

What to point at:

- The whole app is in that language — chrome, briefs, Tara's replies, the
  kundli's graha abbreviations (सू, चं, गु). There is no English fallback
  anywhere; a missing string fails CI rather than degrading.
- **Hinglish is Latin script**, not Devanagari. It is a first-class locale, not
  a transliteration toggle.
- **Numerals stay Latin in Hindi** — `15 अगस्त 2026`, not `१५`. That is a
  ruling (§46/CC-013), not an oversight: Devanagari numerals read as ceremonial
  and would make the product feel archaic rather than authentic.
- Devanagari sets taller and wider at the same nominal size, which is why §24.2
  gives each script its own size factor and line height.

---

## 3. If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Sign-in rejects the OTP | API started without `AUTH_DEV_BYPASS` | check for the banner; restart the API |
| Every screen shows *"Tara will be right back"* | API is down, or the persona is not seeded | `curl :8001/healthz`; re-run the seeder |
| Journal and vault are empty | `seed_demo_history` was not run | run it (§1) |
| Today spins for ~20s on first open | the brief is generating live | expected once per persona per day |
| Chat never replies | `ANTHROPIC_API_KEY` missing, or realtime is down | check `services/api/.env` and `:8002/healthz` |
| Hindi screens show English content | you signed in as an English persona | use `lata` for `/hi` |

---

## 4. Known gaps — say these before someone finds them

Three, and none of them blocks the path above.

1. **S12's voice preview does not play.** Onboarding step 12 shows *"Today's
   audio didn't come through"*. The voice module shipped in M9 and works
   everywhere else — voice notes, Tara's spoken replies — but no endpoint
   synthesises arbitrary preview text, so this screen renders its honest
   unavailable state. It is a missing endpoint, not a broken one.

2. **Both panchang vendors are failing** (DivineAPI 404s, Prokerala 400s). You
   will not see this: §5.2's Layer A is our own Swiss-Ephemeris engine and is
   authoritative for the deterministic astronomy anyway, so tithi, nakshatra,
   sunrise and every timing window are computed locally and correct. What the
   vendors add is the calendar layer — festival dating and regional variants —
   so the festival screen is thinner than it will be.

3. **§30.5's conversation deletion has no screen.** The other three deletion
   scopes are built and demoed above. The API has the *consequence* endpoint
   (marking memory provenance removed) but nothing that deletes a conversation,
   and wiring the sheet to the consequence alone would promise a deletion,
   return 200, and quietly corrupt the provenance of memories she kept. It is
   recorded in code as `CONVERSATION_DELETE_IS_UNBUILT` with a test that fails
   on the commit that builds it. Its home is S36 `/you/privacy`.

Also worth knowing, though not visible: **live calls are gated by §33.5** and
four of its six measures are not passing (two are *blocked* — with no Indic
streaming recogniser there is nothing to intercept and nobody to rate). The
prototype switch turns the feature on locally; it does not turn the gate green,
and `uv run python -m sitara_api.voice.call_gate` still prints the truth.

---

## 5. Resetting between demos

```bash
cd services/api && uv run python -m sitara_api.db.seed --wipe && uv run python -m scripts.seed_demo_history --days 6
```

`--wipe` removes only documents marked `synthetic: true`, so hand-made test data
in the same database is left alone.
