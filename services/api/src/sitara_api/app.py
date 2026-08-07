"""App factory (SPEC §6.3 modular monolith). Modules: auth, numerology."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sitara_api import __version__
from sitara_api.auth.firebase import FirebaseAdminVerifier
from sitara_api.auth.router import router as auth_router
from sitara_api.config import Settings
from sitara_api.db import ensure_indexes, make_mongo, make_redis
from sitara_api.errors import install_error_handlers
from sitara_api.numerology.adapter import AstroNumerologyAdapter
from sitara_api.numerology.router import router as numerology_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client, db = make_mongo(settings)
        app.state.db = db
        app.state.redis = make_redis(settings)
        await ensure_indexes(db)
        yield
        client.close()
        await app.state.redis.aclose()

    app = FastAPI(title="sitara-api", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.firebase_verifier = FirebaseAdminVerifier(
        project_id=settings.firebase_project_id,
        credentials_path=settings.google_application_credentials,
    )
    app.state.numerology_adapter = AstroNumerologyAdapter(
        settings.astro_base_url, settings.astro_timeout_seconds
    )

    install_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(numerology_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "sitara-api", "version": __version__}

    return app
