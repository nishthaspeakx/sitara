"""Runtime configuration. Secrets stay in .env / Secrets Manager, never here."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "dev"
    port: int = 8002

    #: Where `sitara-api` lives. This service holds no database and no model
    #: client: every turn is the §9 pipeline's, reached over HTTP, because a
    #: second copy of the pipeline is a second set of validators to keep in
    #: step with §9 — and the one that drifts is the one nobody is looking at.
    api_base_url: str = "http://localhost:8001"
    api_timeout_seconds: float = 60.0

    #: The shared secret presented on `/v1/chat/ws/*`. Unset means those calls
    #: are refused at the far end (`require_service_key` fails closed), which
    #: is the correct failure for a misconfigured deployment.
    service_key: str | None = None
