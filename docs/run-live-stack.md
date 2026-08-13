# Running the live stack by hand (S18 Ask Tara)

What the milestone's acceptance run needs: real Mongo, Redis, sitara-astro,
sitara-api, sitara-realtime and the web app, with a real `ANTHROPIC_API_KEY`
and a signed-in account. Every command below is one you can paste.

## 0. Prerequisites, checked

```bash
cd ~/code/sitara-app && for p in 27018 6379 8003; do (nc -z -G 2 127.0.0.1 $p && echo "$p UP") || echo "$p DOWN"; done
```

Mongo on **27018** (not 27017), Redis on 6379, sitara-astro on 8003. If astro is
down, start it with `cd services/astro && uv run uvicorn sitara_astro.main:app --port 8003`.

## 1. The service key (once)

§34.6's `/v1/chat/ws/*` endpoints are service-to-service and `require_service_key`
**fails closed** — unset means refuse, because an unconfigured guard on an
endpoint that runs the pipeline for an arbitrary user id is an open door that
looks shut. Both services need the same value.

```bash
cd ~/code/sitara-app && KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))") && grep -q '^SERVICE_KEY=' services/api/.env || printf '\nSERVICE_KEY=%s\nREALTIME_WS_URL=ws://127.0.0.1:8012/chat/session\n' "$KEY" >> services/api/.env && printf 'PORT=8012\nAPI_BASE_URL=http://127.0.0.1:8001\nSERVICE_KEY=%s\n' "$KEY" > services/realtime/.env && echo "service key configured on both sides"
```

Port 8012 rather than 8002 because a Docker container holds 8002 on this
machine. The client never hard-codes it — `POST /v1/chat/session` **serves**
`ws_url`, so moving the socket is one env var and no rebuild.

## 2. Seed a dev account

```bash
cd ~/code/sitara-app/services/api && uv run python -m sitara_api.db.seed --wipe
```

Synthetic only (§22.12): `@example.invalid` emails, +9199999 phones, and the
seeder refuses a non-dev environment or a non-local host.

## 3. Start the three services

Each in its own terminal.

```bash
cd ~/code/sitara-app/services/api && ENVIRONMENT=dev uv run uvicorn sitara_api.main:app --port 8001 --host 127.0.0.1
```

```bash
cd ~/code/sitara-app/services/realtime && uv run uvicorn sitara_realtime.main:app --port 8012 --host 127.0.0.1
```

```bash
cd ~/code/sitara-app/apps/web && API_PROXY_TARGET=http://127.0.0.1:8001 pnpm exec next dev --port 3000
```

Check all three:

```bash
curl -s localhost:8001/healthz; echo; curl -s localhost:8012/healthz; echo; curl -so /dev/null -w '%{http_code}\n' localhost:3000/en/ask
```

## 4. Sign in

The browser cannot complete a real phone-OTP sign-in without
`apps/web/.env.local` holding the `NEXT_PUBLIC_FIREBASE_*` values from the
Firebase console. Until those are on this machine, mint a session directly —
this exercises the same `SessionService` the cookie flow uses, so everything
after auth travels the real path:

```bash
cd ~/code/sitara-app/services/api && uv run python -c "
import asyncio, sys; sys.path.insert(0, 'src')
from sitara_api.config import Settings
from sitara_api.db import make_mongo, make_redis
from sitara_api.auth.sessions import SessionService
async def m():
    s = Settings(); c, db = make_mongo(s); r = make_redis(s)
    u = await db.users.find_one({'synthetic': True})
    t = await SessionService(db, r, s).create(u['_id'], 'manual')
    print('document.cookie = \"sitara_access=' + t.access_token + '; path=/\"')
    c.close(); await r.aclose()
asyncio.run(m())"
```

Open <http://localhost:3000/en/ask>, paste the printed line into the browser
console, reload. The token lives 15 minutes (`access_ttl_seconds`); re-run when
turns start returning 401.

**Auth itself is therefore NOT covered by this run** — it is M2's, verified
there. Say so rather than implying the whole path was walked.

## 5. What to look at

Ask something chart-shaped — "Which mahadasha am I running right now?" or
`hi-Latn`: "Abhi kaun sa grah mere kaam ko prabhavit kar raha hai?" Then:

- **the underline names the fact it stands on.** Tap a gold-underlined sentence.
  §30.4's layer 1 is the claim; layer 3 is the fact in readable terms. If layer 1
  says Venus and layer 3 says "Saturn · 10th house", that is CL-009's shape and
  the sentence is false. Note that Hindi renders गुरु where the sentence may say
  Jupiter — the same body, not a mismatch.
- **presence tracks real stages.** "Tara is listening…" then "Tara is typing…",
  driven by §9 stage transitions rather than a timer, and **gone** once the turn
  lands.
- **a fabrication attempt is refused.** Ask her to state something confidently
  with no citation. Expect the safe fallback line and a `safety_events` row.

To watch the protocol rather than the screen — handshake, every `presence.state`,
the validated `captions.final`:

```bash
cd ~/code/sitara-app/services/api && uv run python /path/to/live_socket.py "<access-token>" "$(python3 -c 'import secrets;print(secrets.token_hex(12))')" en "Which mahadasha am I running right now?"
```

## 6. Known live-path behaviour, so it is not mistaken for a fault

- **Roughly 1 turn in 9 falls back** (`chat.fallback.safe_line` + a
  `safety_events` row). The cause is nearly always the grounding validator
  refusing a natural closing question that names a house — "shall we look at
  what that 7th-house transit touches?" reads as an uncited claim. §9 spends its
  one regeneration and serves the fallback. That is the validator's stated safe
  direction ("a false positive costs one regeneration, a false negative ships a
  fabrication"), not a defect, but it is a §14 tuning item.
- **A fallback still reports the pre-generation `confidence`** (often
  `verified`) in the payload. It never reaches the screen — `MessageBubble`
  renders the chip only when there are citations, and a fallback has none — but
  the field is misleading to anyone reading the JSON.
