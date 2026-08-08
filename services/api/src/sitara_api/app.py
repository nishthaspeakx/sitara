"""App factory (SPEC §6.3 modular monolith).

Modules: auth, numerology, panchang, chat-orchestration.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sitara_api import __version__
from sitara_api.auth.firebase import FirebaseAdminVerifier
from sitara_api.auth.router import router as auth_router
from sitara_api.chat_orchestration import ChatSettings, build_pipeline
from sitara_api.chat_orchestration.router import router as chat_router
from sitara_api.chat_orchestration.types import LAUNCH_LOCALES
from sitara_api.config import Settings
from sitara_api.db import ensure_indexes, make_mongo, make_redis
from sitara_api.db.csfle import build_crypto
from sitara_api.errors import install_error_handlers
from sitara_api.localisation import verify_catalogs
from sitara_api.memory import MemorySettings, build_memory_service
from sitara_api.memory.router import router as memory_router
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
        # §32.4/§32.5 memory. Built before the pipeline, which retrieves
        # through it.
        app.state.memory_service = await build_memory_service(
            db=db,
            settings=app.state.memory_settings,
            environment=settings.environment,
        )
        # §9 chat-orchestration. Built here because the transcript store, the
        # Trust-Sheet log and the safety queue all need the database.
        app.state.chat_pipeline = build_pipeline(
            chat_settings=app.state.chat_settings,
            environment=settings.environment,
            db=db,
            panchang_service=app.state.panchang_service,
            numerology_adapter=app.state.numerology_adapter,
            place_resolver=app.state.place_resolver,
            memory_retriever=app.state.memory_service,
        )
        yield
        if app.state.field_crypto is not None:
            await app.state.field_crypto.close()
        client.close()
        await app.state.redis.aclose()

    app = FastAPI(title="sitara-api", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.chat_settings = ChatSettings()
    app.state.memory_settings = MemorySettings()
    app.state.chat_pipeline = None
    app.state.memory_service = None
    # §2.4: the service renders §9's safety and decline strings itself. A
    # missing catalog must surface here, not when an L4 turn needs the crisis
    # line.
    verify_catalogs(LAUNCH_LOCALES)
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
    app.include_router(chat_router)
    app.include_router(memory_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "sitara-api", "version": __version__}

    return app
