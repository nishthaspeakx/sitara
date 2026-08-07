"""sitara-astro — the Layer-A astrology engine service (SPEC §5).

M0 walking skeleton: /healthz only. The crown jewel lands in M2:
pyswisseph charts (Lahiri), nakshatra+pada, vimshottari dasha, transits,
typed FactSnapshots (§34.2), golden-set harness as release-blocking CI.
Deterministic engine — the LLM NEVER computes astrology (§5.3).
"""

from fastapi import FastAPI

from sitara_astro import __version__

app = FastAPI(title="sitara-astro", version=__version__)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "sitara-astro", "version": __version__}
