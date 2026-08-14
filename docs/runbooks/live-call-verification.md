# Live-call verification — the run the suites cannot do (M10, §25.3, §33.5)

**Purpose: make one real call, against real Cartesia, and find out whether the
streaming adapters are right.**

Everything in `services/api/src/sitara_api/voice/providers/cartesia.py`'s
streaming half was written from vendor documentation. **No live streaming call
has ever been made.** `tests/voice/test_streaming_provenance.py` skips to say
so. The batch endpoints were verified live on 13 Aug 2026, and that says nothing
about these: §33.5's gate turns on p95 first-response audio and barge-in success,
both of which are properties of the streaming path alone.

The whole test suite can be green with every frame name in this adapter wrong.

---

## 0. What you need before you start

| Secret | Why | Without it |
|---|---|---|
| `CARTESIA_API_KEY` | Ink STT websocket + Sonic TTS websocket | The call is refused at the grant — "provider down" (§30.1) |
| `VOICE_TARA_VOICE_ID` | §3.2's anchor voice | TTS declines rather than picking a stock voice — a stranger's voice on her name |
| `ANTHROPIC_API_KEY` | §9's pipeline | Her turn fails; you would be testing the degrade ladder, not the call |
| `SITARA_SERVICE_KEY` | realtime → api service auth | `require_service_key` fails closed and the media socket is refused |

Put them in `services/api/.env` and `services/realtime/.env` (never committed).
The service key must be **the same string in both files**.

A seeded dev account with birth details, or she will correctly decline every
chart question and you will learn nothing about the audio path:

```bash
uv run --directory services/api python -m sitara_api.db.seed --wipe
```

---

## 1. Start the stack, in this order

Order matters once: `sitara-realtime` opens its media socket to `sitara-api` on
the first call, so the API must be listening by then. The rest is independent.

**Infrastructure first** (Mongo on 27018, Redis, astro):

```bash
./infra/dev-up.sh
```

That rebuilds any container image that is behind HEAD — a stale `astro` image
once cost an hour during M5, which is why the check is the script's job. **It
will also warn you that uncommitted work in `services/` is not in the images.**
That warning matters here: run `api` and `realtime` from source, below, not from
containers, or you will be calling last commit's adapter.

**The API** (terminal 2):

```bash
CALLS_ENABLED=true uv run --directory services/api uvicorn sitara_api.main:app --port 8001 --reload
```

`CALLS_ENABLED=true` **only in this shell.** §33.5's gate does not pass, so the
committed default is `false` and stays `false`. Exporting it in a shared profile
or committing it is how a conditional release stops being conditional.

**The realtime service** (terminal 3):

```bash
uv run --directory services/realtime uvicorn sitara_realtime.main:app --port 8002 --reload
```

**The web app** (terminal 4):

```bash
pnpm --filter web dev
```

Confirm all four are up before touching the browser:

```bash
curl -s localhost:8001/healthz; curl -s localhost:8002/healthz; curl -s localhost:8003/healthz
```

---

## 2. Make the call

Open **`http://localhost:3000/en/ask/call`** directly.

Do not look for the call button in the Ask header — `CALLS_ENABLED` in
`apps/web/src/lib/features.ts` is `false`, so it does not render. That flag gates
what the app *offers*; the server's `calls_enabled` gates what it *permits*, and
only the second one matters for this run. Navigating straight to the route is the
intended way to reach a flagged-off screen.

`en` deliberately. CC-010 means `hi` and `hi-Latn` are refused at the grant, and
that refusal is itself worth seeing once (§4 below).

Grant the microphone when asked. Then **say something with a chart question in
it**, e.g. *"what is Saturn doing for me today?"*

---

## 3. What to watch, in the order it should happen

Keep terminal 2 (API) and terminal 3 (realtime) visible. The browser console is
the third surface worth having open.

| # | What should happen | Where you see it | If it does not |
|---|---|---|---|
| 1 | Grant succeeds | Network tab: `POST /v1/call/session` → 200 with `entitlement` + `captions_default_on` | 503 `calls_not_enabled` = the env var did not reach uvicorn. 402 = the seeded account has no active subscription |
| 2 | Socket upgrades | Network tab: `/call/session` switches to 101 | A failed upgrade is usually `realtime_call_ws_url` pointing somewhere else |
| 3 | Ink connects | API log, no `cartesia stt websocket refused` | **This is finding #1.** A refused upgrade means the URL, the header auth or `Cartesia-Version` is wrong |
| 4 | **Live captions appear as you speak** | On screen, greyed while partial | **Finding #2 and the big one.** Captions never appearing means the frame shape is wrong — the adapter branches on `type == "transcript"` and `is_final`. Log the raw frames if so |
| 5 | Your finished sentence turns solid | Caption goes full opacity | A partial that never finalises = `is_final` is named something else |
| 6 | She thinks, then speaks | State chip: Listening → Thinking → Tara is speaking | Thinking for more than ~2s without a holding phrase is a §25.3 miss worth noting |
| 7 | **You hear her** | Audio | **Finding #3.** Silence with a `tts.start` on the wire means Sonic's chunk frames are not named `chunk`/`data` |
| 8 | **Interrupt her mid-sentence** | She stops within a beat | This is §33.5's barge-in measure. If she talks over you, the cancel is not reaching the vendor |
| 9 | The transcript is in the thread | Navigate to `/en/ask` | Everything you both said should be there. **If it is not, stop — that is the milestone's central claim failing** |

---

## 4. The two runs worth doing after the happy path

**The chaos path, for real.** With the call live, kill Sonic's reachability —
easiest is to block it at the firewall or change `CARTESIA_API_KEY` to a bad
value and start a fresh call, then speak. Expected: her words appear on screen as
text, the audio stops, and the screen offers "Let's carry on in messages" with
the whole call in the thread. `services/realtime/tests/test_call_degrade.py`
asserts exactly this against the real service; this is the same thing against a
real vendor.

**The CC-010 refusal.** Open `http://localhost:3000/hi/ask/call`. Expected: the
Hindi refusal, no portrait, no retry control. This is the ruling that matters
most — an English recogniser fed Hindi audio does not fail, it produces fluent
nonsense that reaches §9 as the user's question.

---

## 5. Recording what you found

If the frames matched the adapter, record the fixtures so the provenance test
stops skipping:

```bash
CARTESIA_API_KEY=... uv run --directory services/api python -m tests.voice.record_streaming
```

If they did **not** match — which is the likely outcome for at least one of the
three findings above — the fix is in `cartesia.py`'s two `_events`/`stream`
loops, and the docstring's "UNVERIFIED" line becomes a dated "VERIFIED" only
once a recording exists.

Either way, the §33.5 numbers this run produces are real and worth reading:

```bash
uv run --directory services/api python -m sitara_api.voice.call_gate
```

`first_audio_p95_s`, `barge_in_success` and `network_recovery_success` will have
values after a few calls. `cost_per_call_user` and `call_naturalness` will not,
and cannot — the first needs a contracted rate card, the second a human panel.
**The gate will still say DOES NOT PASS, and that is correct.**

---

## 6. Afterwards

```bash
docker compose -f infra/docker-compose.dev.yml down
```

`CALLS_ENABLED` lived only in terminal 2's environment. Nothing to unset, and
nothing committed — which is the point.
