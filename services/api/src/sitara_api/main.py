"""sitara-api — FastAPI modular monolith (SPEC §6.3).

Uvicorn entrypoint: `uvicorn sitara_api.main:app`. The app itself is built by
the factory in app.py; every error uses the canonical §34.4 envelope from
sitara_schemas.
"""

from sitara_api.app import create_app

app = create_app()
