# Swiss Ephemeris data files

Source: https://github.com/aloistr/swisseph (official Astrodienst mirror), `ephe/`.
Coverage: 1800–2399 AD. Licensed under the Swiss Ephemeris commercial licence
(budgeted CHF 750, SPEC §5.1) — the AGPL alternative is not used for Sitara.

| file | sha256 |
|---|---|
| sepl_18.se1 | ca1393ceab3a44fbc895887cf789c68819ae6a1cbc9b22225872dbe4ccd99a66 |
| semo_18.se1 | 1ca07bd67c24374d77226180c20a4f9996cba013697894810518e7eb582ca4f7 |
| seas_18.se1 | a2cd8fc33807c78ca9a700c91c2e042258b12fc4796519e00781440b5ad8b2e2 |

The engine auto-detects these at `SWISSEPH_DATA_PATH` (default `data/swisseph`
relative to the service root) and records `ephe=swiss_files` in every fact's
`data_revision`; if absent it falls back to the built-in Moshier model and
records `ephe=moshier` — a Moshier fact is never claimed as file-grade.
