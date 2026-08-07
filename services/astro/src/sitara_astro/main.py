"""sitara-astro — the Layer-A astrology engine service (SPEC §5).

Deterministic engine — the LLM NEVER computes astrology (§5.3). Emits typed
FactSnapshots (§34.2); golden-set harness is the release gate (§5.5).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sitara_astro import __version__
from sitara_astro.api.routes import router
from sitara_astro.config import Settings
from sitara_astro.engine.ephemeris import data_revision, init_ephemeris
from sitara_astro.errors import install_error_handlers
from sitara_astro.pii import install_log_scrubbing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    install_log_scrubbing()  # §13 net: no name or birth date reaches a log sink
    app.state.ephe_source = init_ephemeris(settings.resolved_swisseph_data_path)
    app.state.data_revision = data_revision()
    yield


app = FastAPI(title="sitara-astro", version=__version__, lifespan=lifespan)
install_error_handlers(app)
app.include_router(router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "sitara-astro",
        "version": __version__,
        "ephe_source": getattr(app.state, "ephe_source", "uninitialised"),
        "data_revision": getattr(app.state, "data_revision", "uninitialised"),
    }
