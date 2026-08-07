"""Runtime configuration (playbook M1). Secrets stay in .env / .secrets — never here."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8001
    mongodb_uri: str = "mongodb://localhost:27018/sitara"
    mongo_db: str = "sitara"
    redis_url: str = "redis://localhost:6379/0"

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
