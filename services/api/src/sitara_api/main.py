"""sitara-api — FastAPI modular monolith (SPEC §6.3).

M0 walking skeleton: /healthz only. Modules (auth, users, astrology facade,
chat-orchestration, …) land per the milestone plan; every error uses the
canonical §34.4 envelope from sitara_schemas.
"""

from fastapi import FastAPI
from sitara_schemas import ErrorEnvelope  # noqa: F401 — envelope is the ONLY error shape

from sitara_api import __version__

app = FastAPI(title="sitara-api", version=__version__)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "sitara-api", "version": __version__}
