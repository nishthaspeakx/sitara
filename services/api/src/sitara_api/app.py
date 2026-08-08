"""App factory (SPEC §6.3 modular monolith). Modules: auth, numerology, panchang."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sitara_api import __version__
from sitara_api.auth.firebase import FirebaseAdminVerifier
from sitara_api.auth.router import router as auth_router
from sitara_api.config import Settings
from sitara_api.db import ensure_indexes, make_mongo, make_redis
from sitara_api.db.csfle import build_crypto
from sitara_api.errors import install_error_handlers
from sitara_api.numerology.adapter import AstroNumerologyAdapter
from sitara_api.numerology.router import router as numerology_router
from sitara_api.panchang.adapter import AstroPanchangAdapter
from sitara_api.panchang.cache import PanchangCache
from sitara_api.panchang.places import default_resolver
from sitara_api.panchang.registry import build_registry
from sitara_api.panchang.router import router as panchang_router
from sitara_api.panchang.service import PanchangService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client, db = make_mongo(settings)
        app.state.db = db
        app.state.redis = make_redis(settings)
        await ensure_indexes(db)
        # §13 CSFLE. Returns None only in dev with encryption switched off;
        # anywhere else a missing key is an error, not a silent plaintext fallback.
        app.state.field_crypto = await build_crypto(client, settings)
        # The §7.2 caches need the database, so the panchang service is built
        # here rather than at import time.
        app.state.panchang_cache = PanchangCache(
            db,
            panchang_ttl_days=settings.panchang_cache_ttl_days,
            muhurat_ttl_days=settings.muhurat_cache_ttl_days,
        )
        app.state.panchang_service = PanchangService(
            cache=app.state.panchang_cache,
            divineapi=app.state.provider_registry.divineapi,
            prokerala=app.state.provider_registry.prokerala,
            astro=app.state.astro_panchang_adapter,
        )
        yield
        if app.state.field_crypto is not None:
            await app.state.field_crypto.close()
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
    app.state.provider_registry = build_registry(settings)
    app.state.astro_panchang_adapter = AstroPanchangAdapter(
        settings.astro_base_url, settings.astro_timeout_seconds
    )
    app.state.place_resolver = default_resolver()

    install_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(numerology_router)
    app.include_router(panchang_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "sitara-api", "version": __version__}

    return app
