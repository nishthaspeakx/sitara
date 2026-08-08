"""Service settings. SWISSEPH_DATA_PATH resolves relative to the service root
so dev checkouts and the container (which sets an absolute path) both work."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    swisseph_data_path: Path = Path("data/swisseph")
    port: int = 8003

    @property
    def resolved_swisseph_data_path(self) -> Path:
        path = self.swisseph_data_path
        return path if path.is_absolute() else SERVICE_ROOT / path
