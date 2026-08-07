# Provider fixtures — recorded once, replayed forever

CI **never** calls a live vendor. `test_no_live_network.py` installs a socket
guard that fails loudly on any real connection attempt during the test session.

Every fixture declares its provenance:

```json
"_recording": {
  "status": "provisional" | "recorded",
  "recorded_at": "2026-08-07T09:14:00Z",
  "note": "..."
}
```

## `provisional` — what we have today

The shapes were written from vendor documentation and have **not** been checked
against a live trial account. They exercise our parse layer, which is what the
contract tests are for, but they are **not evidence that DivineAPI and Prokerala
actually answer this way.**

`test_fixture_provenance.py::test_all_fixtures_recorded_from_live_api` SKIPs
with a loud reason while any fixture is provisional, and turns green the moment
recording replaces them. That skip is the honest marker of the gap — do not
delete it to make the suite look complete.

## Recording (needs trial keys)

```bash
DIVINEAPI_API_KEY=… DIVINEAPI_AUTH_TOKEN=… \
PROKERALA_CLIENT_ID=… PROKERALA_CLIENT_SECRET=… \
SITARA_RECORD_FIXTURES=1 \
uv run python -m sitara_api.panchang.record --all
```

- Exactly **one** real call per endpoint per provider.
- Credentials (`api_key`, `Authorization`, `client_secret`, `access_token`) are
  scrubbed from everything written to disk.
- Fixtures contain a date, a place and public almanac data — no user data ever
  goes near a recording (§13).

After recording, re-run the contract tests. Where a real payload disagrees with
the adapter's assumed field names, fix the adapter (or the configurable path in
`.env`), never the fixture.
