from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[1]


class StubSettings(BaseSettings):
    """Stub service settings loaded from the repo root .env file."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    demucs_api_url: str = ""
    request_timeout_seconds: float = 600.0


settings = StubSettings()
UPSTREAM_DEMUCS_API_URL = settings.demucs_api_url.strip().rstrip("/")
REQUEST_TIMEOUT_SECONDS = settings.request_timeout_seconds
