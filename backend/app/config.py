from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-5-5"
    # Effort controls how hard Claude thinks per email; "low" keeps syncs fast and cheap.
    claude_effort: str = "low"

    google_client_secrets_file: Path = Path("credentials.json")
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    frontend_url: str = "http://localhost:3000"

    gmail_query: str = "in:inbox newer_than:7d"
    max_emails_per_sync: int = 25

    data_dir: Path = Path("data")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tracker.db"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "gmail_token.json"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
