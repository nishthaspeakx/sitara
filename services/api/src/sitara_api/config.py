"""Runtime configuration (playbook M1). Secrets stay in .env / .secrets — never here."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # dev | test | staging | production. Gates the §22.12 hygiene rules: the
    # local KMS provider and the synthetic seeder both refuse to run outside
    # dev/test, so production PII can never be created by a dev tool and a
    # dev master key can never protect production data.
    environment: str = "dev"

    port: int = 8001
    mongodb_uri: str = "mongodb://localhost:27018/sitara"
    mongo_db: str = "sitara"
    redis_url: str = "redis://localhost:6379/0"

    # --- §13 / §6.4 client-side field-level encryption -------------------
    # Off by default so a bare `create_app()` still boots without a key; the
    # compose stack and every deployed environment turn it on. Explicit
    # (not automatic) CSFLE — automatic schemaMap encryption is an
    # Enterprise/Atlas-only feature and dev runs Community mongo.
    csfle_enabled: bool = False
    csfle_kms_provider: str = "local"  # local (dev only) | aws
    csfle_key_vault_namespace: str = "__keyvault.datakeys"
    csfle_local_master_key_path: str | None = None
    csfle_aws_kms_key_arn: str | None = None
    csfle_aws_region: str = "ap-south-1"

    # §30.6: Stories are a P1 gated experiment. The collections exist from M4
    # (dark-launched per §25.7); nothing reads or writes them until this flips.
    stories_enabled: bool = False

    # Firebase Admin SDK (§34.5 — server-side ID-token verification only).
    google_application_credentials: str | None = None
    firebase_project_id: str | None = None

    # §26.1 decision log: Apple sign-in deferred to M+2 — slot stays, flag off.
    apple_signin_enabled: bool = False
    # §22.5 step-up verification for account linking — interface live, enforcement M+2.
    step_up_enforced: bool = False

    # Session cookies (§34.5 / §6.2). Secure=False only for local http dev.
    cookie_secure: bool = False
    access_ttl_seconds: int = 900
    refresh_ttl_seconds: int = 30 * 24 * 3600

    # §6.3: sitara-astro is an INTERNAL service; only this API fronts it publicly.
    astro_base_url: str = "http://localhost:8003"
    astro_timeout_seconds: float = 3.0

    # §27: 5 OTP fails → 15-minute lock.
    otp_max_fails: int = 5
    otp_lock_seconds: int = 900

    # --- §34.6 the chat/voice socket -------------------------------------
    # Where the browser opens the socket. SERVED to the client by
    # POST /v1/chat/session rather than compiled into it: `lib/api.ts` records
    # what a public build-time origin costs when it has to agree with a cookie
    # posture, and this one also has to agree with a deployment topology.
    realtime_ws_url: str = "ws://localhost:8002/chat/session"
    # §34.6/§32.11: "reconnect within 5 min resumes via session token".
    chat_resume_window_s: int = 300
    # The shared secret `sitara-realtime` presents on /v1/chat/ws/*. Unset
    # means those endpoints REFUSE — `require_service_key` fails closed,
    # because an unconfigured guard on a service-to-service endpoint that runs
    # the pipeline for an arbitrary user id is an open door that looks shut.
    service_key: str | None = None

    # --- §25.3 the live call (M10) ---------------------------------------
    # Where the browser opens the CALL socket. A separate URL from the chat
    # one and not a path appended to it: §6.1 scales and sticky-routes the two
    # independently, and a call session is minutes of duplex audio while a chat
    # session is bursts of text.
    realtime_call_ws_url: str = "ws://localhost:8002/call/session"
    # **§33.5's conditional release gate, as a switch.** Calls ship only if six
    # measures pass and they do not (`uv run python -m sitara_api.voice.call_gate`
    # prints the table). §33.5's own instruction for that state is that launch
    # proceeds with text, voice notes and Tara audio replies while calls roll
    # out behind a flag — so the default is OFF, and turning it on is a
    # deliberate act by someone who has read the gate.
    #
    # It is a flag over BUILT code, not over a hole: everything behind it is
    # implemented and tested. That distinction is `apps/web/src/lib/features.ts`'s
    # rule and it applies here identically.
    calls_enabled: bool = False

    # --- §5.2 Layer B panchang providers ---------------------------------
    # Keys live in .env / Secrets Manager, never here and never in git.
    # A blank key is not an error: the provider then behaves as "down" and the
    # §8 degradation ladder runs, which is the playbook's kill-the-key
    # acceptance. Base URLs and paths are configurable so a shape correction
    # found at fixture-recording time needs no code change.
    divineapi_base_url: str = "https://astroapi-4.divineapi.com"
    # DIVINE_API_KEY is accepted as an alias: it is what the vendor's own
    # dashboard calls the value, so operators paste it under that name.
    divineapi_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DIVINEAPI_API_KEY", "DIVINE_API_KEY"),
    )
    # Optional: some DivineAPI tiers authenticate with the api_key alone, and a
    # blank token must degrade like an outage rather than crash (§8).
    divineapi_auth_token: str | None = None
    divineapi_timeout_seconds: float = 4.0
    divineapi_path_panchang: str | None = None
    divineapi_path_day_timings: str | None = None
    divineapi_path_muhurat: str | None = None

    prokerala_base_url: str = "https://api.prokerala.com"
    prokerala_client_id: str | None = None
    prokerala_client_secret: str | None = None
    prokerala_timeout_seconds: float = 4.0
    prokerala_path_token: str | None = None
    prokerala_path_panchang: str | None = None
    prokerala_path_day_timings: str | None = None
    prokerala_path_muhurat: str | None = None

    # §8: fail fast after 5 errors/30s, half-open probes.
    panchang_breaker_errors: int = 5
    panchang_breaker_window_seconds: float = 30.0
    panchang_breaker_half_open_seconds: float = 60.0

    # §7.2 cache TTLs.
    panchang_cache_ttl_days: int = 90
    muhurat_cache_ttl_days: int = 30
    transit_cache_ttl_days: int = 400

    # Fixture recording — set to 1 ONLY while recording; CI never sets it.
    sitara_record_fixtures: bool = False

    def divineapi_paths(self) -> dict[str, str]:
        return _present(
            panchang=self.divineapi_path_panchang,
            day_timings=self.divineapi_path_day_timings,
            muhurat=self.divineapi_path_muhurat,
        )

    def prokerala_paths(self) -> dict[str, str]:
        return _present(
            token=self.prokerala_path_token,
            panchang=self.prokerala_path_panchang,
            day_timings=self.prokerala_path_day_timings,
            muhurat=self.prokerala_path_muhurat,
        )


def _present(**values: str | None) -> dict[str, str]:
    return {k: v for k, v in values.items() if v}
