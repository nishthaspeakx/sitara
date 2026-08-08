# Provider fixtures — recorded once, replayed forever

CI **never** calls a live vendor. `test_no_live_network.py` blocks DNS *and*
connect for any non-loopback host, so a call that escapes MockTransport fails
loudly instead of silently spending trial-account requests.

Every fixture declares its provenance in a `_recording` block
(`status`, `recorded_at`, `note`, `request`).

## Current state

| Provider | Status | Notes |
|---|---|---|
| **prokerala** | ✅ `recorded` | Live sandbox, 2026-01-01, Mumbai/Jaipur. All four endpoints 200. |
| **divineapi** | ⚠️ `provisional` | Endpoint paths unknown — see below. |

`test_all_fixtures_recorded_from_live_api` SKIPs while anything is provisional
and turns green by itself once it is not. That skip is the honest marker of the
gap — **do not delete it to make the suite look complete.**

## What recording taught us (Prokerala)

Three vendor quirks that documentation did not give us, each now pinned by a
test and commented at its call site:

1. **`datetime` must carry a UTC offset.** A naive local value is rejected with
   error 1003. We attach it from the IANA tzdb, which §5.2 requires anyway.
2. **Tithis are numbered krishna-first** (1–15 krishna, 16–30 shukla) where our
   contract is shukla-first — a 15-place rotation. Their `index` field is `0` on
   every entry and must not be used; `id` is the real number. The parse
   re-derives the paksha and compares it to theirs, so a renumbering surfaces as
   an outage rather than a wrong tithi.
3. **There is no typed muhurat finder.** `/auspicious-period` ignores `type` and
   returns generic periods (Abhijit, Amrit Kaal, Brahma Muhurat), confirming
   §5.2's provider table. A typed query is declined, never answered with a
   generic window wearing the wrong label (§5.3).

The recorded choghadiya sequence also **independently corroborated our own rule
tables** — and exposed a real bug in them: the night sequence walks the
seven-name ring by −2, not +1. Fixed in `services/astro`.

**Sandbox limit:** the trial account rejects every date but January 1st (error
1004), which is why the fixtures sit there. They pin the *shape*, which is what
they are for. `--date` overrides it once production keys land.

## DivineAPI — still outstanding

Every guessed path under `https://astroapi-4.divineapi.com` returned a generic
404 page, so the real endpoints must come from the DivineAPI dashboard. No code
change is needed once they are known — set them in `.env`:

```
DIVINEAPI_PATH_PANCHANG=…
DIVINEAPI_PATH_DAY_TIMINGS=…
DIVINEAPI_PATH_MUHURAT=…
```

The provisional DivineAPI fixtures are aligned to the same day and place as the
recorded Prokerala ones, so the cross-vendor agreement tests represent a normal
day rather than an artificial one.

## Recording

```bash
SITARA_RECORD_FIXTURES=1 uv run python -m sitara_api.panchang.record --all
```

- Exactly **one** real call per endpoint per provider.
- Credentials are scrubbed by key name *and* by a bearer-token sweep over string
  values; a test greps the raw files for anything credential-shaped.
- Fixtures hold a date, a place and public almanac data — no user data.

Where a real payload disagrees with an adapter, fix the **adapter** (or its
configurable path in `.env`) — never the fixture.
