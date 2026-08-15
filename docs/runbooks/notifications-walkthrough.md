# §23 notifications — the demo script (M12)

Everything below runs on a laptop with no external account, no signup and no
vendor key. Two of §23.3's three channels are the real protocol; the third is
declared and gated. What each thing is, stated once so nobody has to guess:

| channel | what it actually is | why |
|---|---|---|
| **push** | RFC 8291 + RFC 8292 over the browser's own Push API, against a keypair we generate | web push needs **no account at all** — the push service is whichever one the browser already uses, and VAPID is self-signed |
| **email** | ordinary SMTP to Mailpit, a real mail server in a container | SES speaks the same protocol; swapping the host is three env vars and no code |
| **WhatsApp** | **DECLARED, not implemented** — every method raises | needs a verified Meta Business account and per-locale templates Meta must approve; release gate `notifications.whatsapp_channel` |

---

## 0. Bring the stack up

```bash
docker compose -f infra/docker-compose.dev.yml up -d mongo redis mailpit api worker-notify beat
```

Generate the VAPID keypair once. This is the entire setup web push has:

```bash
cd services/api && uv run python -m sitara_api.notifications.vapid --generate
```

It refuses to overwrite an existing key, deliberately — replacing a VAPID
keypair invalidates every browser subscription already stored, because a
subscription is bound to the `applicationServerKey` it was created with.

Mailpit's inbox is at **http://localhost:8025**. Leave it open; it is where the
demo's messages actually arrive.

Sign in with `AUTH_DEV_BYPASS=true` (see `DEMO.md` §1), then open
**`/en/you/settings/notifications`** — S41, §23.5's matrix.

---

## 1. What §23 would do right now

```bash
curl -s localhost:8001/v1/dev/notifications/state | jq
```

One call, no message sent. It reports her local clock, her quiet-hours window,
whether her brief time falls inside it, which channels can carry anything,
which she is reachable on, and the §23.3 ladder that would be built for each of
§23.5's five categories. Every field is computed by the functions the sender
uses — this is a view of the rules, not a second implementation.

The two rows to point at:

- `channels.whatsapp.support` reads `declared`. That is the release gate, in
  the product, saying what is and is not built.
- `quiet_hours.brief_would_send_now` — §32.6, below.

---

## 2. The morning brief, at her own brief_time

```bash
curl -s -XPOST localhost:8001/v1/dev/notifications/brief | jq
```

Fires the Class-D morning push scheduled for **her** `brief_time` in **her**
zone — not for "now". If push is subscribed it arrives in the notification
centre; otherwise §23.3's ladder carries it to Mailpit and you can read it.

### §32.6, which is the interesting half

Set her brief time to 06:30 on S41 (inside the default 22:30–07:00 quiet
window). S41 immediately shows §32.6's notice — *"your brief arrives inside
your quiet hours — that's fine, just checking"* — **once**. Acknowledge it and
it does not come back; change either setting to make a *different* overlap and
it flags again, because the acknowledgement records that specific overlap
rather than a boolean.

Now fire the brief. It **goes out**, and the response says why:

```json
{ "sent": true, "quiet_hours_exempt": true, "inside_quiet_hours": true }
```

Then fire a night nudge at the same hour and watch it be held:

```bash
curl -s -XPOST localhost:8001/v1/dev/notifications/fire \
  -H 'content-type: application/json' -d '{"category":"night"}' | jq
```

`{"sent": false, "blocked": "quiet_hours"}`. Same user, same clock, same class
— §32.6 exempts the **appointment**, not the class. That distinction is the
whole point: the night nudge is also Class D and §23.4 expires it at 23:30, one
hour inside the default window.

---

## 3. The fallback ladder

Kill the push subscription the way a push service's 410 does:

```bash
curl -s -XPOST localhost:8001/v1/dev/notifications/kill-push | jq
curl -s -XPOST localhost:8001/v1/dev/notifications/brief | jq
```

The second response reads `"channels": ["email"]`, and the message is in
Mailpit. §23.3: *"silent fallback … same message, NOT both"* — one message,
one channel, one row in the ledger. The subscription is now `dead` (§23.6
retires it on the **first** 410, not the third), and S41 shows push as
something to turn back on.

---

## 4. The caps

```bash
curl -s -XPOST localhost:8001/v1/dev/notifications/cap | jq
```

Sends five real Class-C messages through the real service and then one Class-T
reminder. Nothing is written by hand — the point is the cap, and writing rows
directly would demonstrate the query instead.

Expect **one** contextual message (§23.1 caps Class C at 1/day) and then the
reminder arriving anyway, because §23.2(1) makes a user-requested reminder
Class T: it always wins, it does not consume the contextual slot, and quiet
hours do not hold it.

---

## 5. Pause, and the sentence that has to be there

Tap **"Pause everything for a week"** on S41. Under it, always visible:

> Security messages still come through. Stated plainly, because they do.

That is §23.5's *"Class T exempt, stated plainly"*. Demonstrate it:

```bash
curl -s -XPOST localhost:8001/v1/dev/notifications/fire -H 'content-type: application/json' \
  -d '{"category":"morning"}' | jq        # blocked: paused
curl -s -XPOST localhost:8001/v1/dev/notifications/fire -H 'content-type: application/json' \
  -d '{"trigger":"user_reminder"}' | jq   # sent: true
```

Un-pausing is one tap with no confirmation and no minimum (§29.2).

---

## 6. The emergency stop (§23.7, §12)

```bash
curl -s -XPOST localhost:8001/v1/dev/notifications/halt \
  -H 'content-type: application/json' -d '{"channel":"push"}' | jq
curl -s -XPOST localhost:8001/v1/dev/notifications/halt \
  -H 'content-type: application/json' -d '{"locale":"hi"}' | jq
```

Three axes — class, channel, locale — and they compose by OR, so an operator
who halts `push` and separately halts `marketing` has stopped both. A blocked
send names the halt that held it (`"halt_token": "channel:push"`), which during
an incident is the difference between "12,000 messages held" and something
actionable. Resume with `/resume` and the same body.

---

## 7. The proof: the brief lands at the local brief_time

The claim is measured, not asserted:

```bash
cd services/api && uv run pytest tests/notifications/test_acceptance_brief_time.py -v
```

§23.9's timezone matrix — IST, Nepal's +05:45, EST, GMT, AEDT, Auckland, and
**both DST transition days** — each seeded as a real user, enqueued through
§7.1's own `local_instant`, then the real delivery worker ticked **minute by
minute** across the window. The assertion is §23.8's SLO: delivered within 5
minutes of the local target. The last case runs the whole way to Mailpit, so
"the brief arrives at 07:00 in Mumbai" is something you can open and read.

> **This harness earned its place on the first run.** It found that §32.6's
> exemption compared against the `brief_time` *string*. On a spring-forward
> morning §7.1 schedules an 02:30 brief for 03:00 — because 02:30 does not
> happen — so the comparison failed, the brief was held by quiet hours, and it
> expired at noon. Once a year, silently, only for users whose brief time sits
> inside their quiet hours. No unit test would have shown it: every one of them
> passes a brief time that exists.

---

## 8. Reset

```bash
curl -s -XPOST localhost:8001/v1/dev/notifications/reset | jq
```

Scoped to the signed-in user, never a collection drop. **Push subscriptions
survive on purpose** — they belong to a browser rather than to a demo run, and
deleting them means granting the notification permission by hand again, which
is the one step of this nobody can script.

---

## What is not demonstrable, and why

- **WhatsApp.** Declared, no adapter, gated at `notifications.whatsapp_channel`.
  The gate reads the capability matrix, so it closes itself the day the cell
  flips. Its column still renders on S41 and still stores her choice — hiding it
  would discard the preference of everyone who set it early.
- **A real push service round trip without internet.** The adapter POSTs to
  whatever endpoint the browser handed over; with egress it is a real vendor
  push service and the notification appears in the OS notification centre.
  Without it, the POST fails and §23.3's ladder moves to email — which is the
  ladder working rather than a workaround, and is worth showing either way.
- **§23.8's dashboards.** The counters are written on every row; the admin
  surface that reads them is §12's workstream.

Gates: `uv run python -m sitara_api.release_gates` — three of them are M12's.
