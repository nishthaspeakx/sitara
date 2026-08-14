"""App factory (SPEC §6.3 modular monolith).

Modules: auth, numerology, panchang, chat-orchestration.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sitara_api import __version__
from sitara_api.astrology import AstroChartAdapter, AstrologyFacade
from sitara_api.auth.firebase import FirebaseAdminVerifier
from sitara_api.auth.router import router as auth_router
from sitara_api.calls.router import router as call_router
from sitara_api.calls.service import CallTurnService
from sitara_api.chat_orchestration import ChatSettings, build_pipeline
from sitara_api.chat_orchestration.router import router as chat_router
from sitara_api.chat_orchestration.types import LAUNCH_LOCALES
from sitara_api.config import Settings
from sitara_api.daily_guidance.router import router as today_router
from sitara_api.daily_guidance.wiring import build_service as build_daily_guidance
from sitara_api.db import ensure_indexes, make_mongo, make_redis
from sitara_api.db.csfle import build_crypto
from sitara_api.errors import install_error_handlers
from sitara_api.journal.router import router as journal_router
from sitara_api.journal.search import ExactTextSearch
from sitara_api.journal.service import JournalService
from sitara_api.journal.store import JournalStore
from sitara_api.localisation import verify_catalogs
from sitara_api.memory import MemorySettings, build_memory_service
from sitara_api.memory.router import router as memory_router
from sitara_api.numerology.adapter import AstroNumerologyAdapter
from sitara_api.numerology.router import router as numerology_router
from sitara_api.onboarding.router import router as onboarding_router
from sitara_api.panchang.adapter import AstroPanchangAdapter
from sitara_api.panchang.cache import PanchangCache
from sitara_api.panchang.places import default_resolver
from sitara_api.panchang.registry import build_registry
from sitara_api.panchang.router import router as panchang_router
from sitara_api.panchang.service import PanchangService
from sitara_api.voice.call_metrics import CallMetrics, RedisMetricStore
from sitara_api.voice.config import VoiceSettings
from sitara_api.voice.entitlements import MinuteLedger
from sitara_api.voice.providers.registry import build_streaming_tts, build_voice_service
from sitara_api.voice.router import router as voice_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client, db = make_mongo(settings)
        app.state.db = db
        # The CSFLE key vault needs the CLIENT, not the database, and
        # `daily_guidance.wiring.build_service` borrows it rather than opening a
        # second one — an earlier version opened one per call and never closed
        # it, which at Stage-2 volumes is a leaked pool per brief.
        app.state.mongo_client = client
        app.state.redis = make_redis(settings)
        await ensure_indexes(db)
        # §13 CSFLE. Returns None only in dev with encryption switched off;
        # anywhere else a missing key is an error, not a silent plaintext fallback.
        app.state.field_crypto = await build_crypto(client, settings)
        # §13's single door to birth details, built here because it needs both
        # the database and the CSFLE codec above it. Without the codec the
        # facade would read ciphertext and hand the engine nonsense, so it is
        # built AFTER `field_crypto` and given it — never before.
        app.state.astrology = AstrologyFacade(
            db=db,
            adapter=AstroChartAdapter(
                settings.astro_base_url, settings.astro_timeout_seconds
            ),
            crypto=app.state.field_crypto,
        )
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
        # §30.5's Journal (M10). Built after memory because §30.5's
        # journal-entry deletion offers a checkbox that reaches `memories` —
        # a checkbox offered and silently ineffective is worse than one not
        # offered, so the service takes the memory service rather than
        # discovering it later.
        app.state.journal_service = JournalService(
            store=JournalStore(db),
            search=ExactTextSearch(db),
            memory_service=app.state.memory_service,
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
            # Built above, and passed here rather than left to default: the
            # chart fact tools decline without it (see build_pipeline).
            astrology_facade=app.state.astrology,
        )
        # §25.4's voice notes (M9, CC-009). Built after the pipeline because it
        # RUNS that pipeline — voice is not a second orchestration — and after
        # the crypto because §33.1 puts the original recording under its own
        # CSFLE key class. Returns None when no vendor key is configured, which
        # is "provider down" and not a boot failure (§30.1: text always works).
        app.state.voice_notes = build_voice_service(
            settings=app.state.voice_settings,
            db=db,
            crypto=app.state.field_crypto,
            pipeline=app.state.chat_pipeline,
        )
        # §25.3's live call (M9-P10b). Built after the pipeline for the same
        # reason voice notes are: a call RUNS §9 rather than reimplementing it.
        # It is reachable only behind `settings.calls_enabled` (§33.5) and only
        # in a locale `routing` admits (CC-010) — both checked at the door in
        # `calls/router.py`, so this being wired is not the same as this being
        # available.
        app.state.call_turns = CallTurnService(
            pipeline=app.state.chat_pipeline,
            store=(
                app.state.chat_pipeline.message_store if app.state.chat_pipeline else None
            ),
            tts=build_streaming_tts(app.state.voice_settings),
            voice_id=app.state.voice_settings.tara_voice_id,
            environment=settings.environment,
        )
        app.state.minute_ledger = MinuteLedger(db)
        # §33.5's evidence, from the first call (§43.5). Redis and not Mongo
        # because these are counters and a reservoir, and no TTL because a
        # launch gate whose evidence expired would quietly reset the decision.
        app.state.call_metrics = CallMetrics(RedisMetricStore(app.state.redis))
        # §7.1's pipeline, for the on-open path `GET /v1/today` needs (§28.2).
        # Built ONCE here rather than per request: it provisions a CSFLE codec
        # holding a key-vault connection, and Today is the app's busiest screen.
        app.state.daily_guidance, close_daily_guidance = await build_daily_guidance(
            db, client
        )
        yield
        await close_daily_guidance()
        if app.state.field_crypto is not None:
            await app.state.field_crypto.close()
        client.close()
        await app.state.redis.aclose()

    app = FastAPI(title="sitara-api", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.chat_settings = ChatSettings()
    app.state.voice_settings = VoiceSettings()
    app.state.memory_settings = MemorySettings()
    app.state.astrology = None
    app.state.chat_pipeline = None
    app.state.voice_notes = None
    app.state.memory_service = None
    app.state.journal_service = None
    app.state.call_turns = None
    app.state.call_metrics = None
    app.state.minute_ledger = None
    # §2.4: the service renders §9's safety and decline strings itself. A
    # missing catalog must surface here, not when an L4 turn needs the crisis
    # line.
    verify_catalogs(LAUNCH_LOCALES)
    # §6.3's adapter rule, and `firebase.py`'s own "fakeable boundary". The
    # dev verifier RAISES unless environment == "dev", so a mis-set env var in
    # any other environment fails at boot — loudly, and before it can issue a
    # single session.
    if settings.auth_dev_bypass:
        from sitara_api.auth.dev_verifier import DevPhoneVerifier, seeded_phone_book

        app.state.firebase_verifier = DevPhoneVerifier(environment=settings.environment)
        book = ", ".join(f"{phone} ({handle})" for phone, handle in seeded_phone_book())
        logging.getLogger(__name__).warning(
            "AUTH_DEV_BYPASS is ON — Firebase is not consulted. Seeded personas: %s", book
        )
    else:
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
    app.include_router(call_router)
    app.include_router(voice_router)
    app.include_router(memory_router)
    app.include_router(journal_router)
    app.include_router(onboarding_router)
    app.include_router(today_router)
    # §28.2's variant switcher runs the REAL service over fact fixtures, and
    # it exists ONLY in dev — `db.seed` refuses a non-dev host for the same
    # reason: a convenience that can reach production data is not one.
    if settings.environment == "dev":
        from sitara_api.daily_guidance.dev_router import router as today_dev_router

        app.include_router(today_dev_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "sitara-api", "version": __version__}

    return app
