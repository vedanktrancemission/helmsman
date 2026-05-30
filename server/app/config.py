"""Runtime settings loaded from .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    database_url: str = "sqlite:///./helmsman.db"
    bus_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: str = "fake"
    llm_api_key: str = ""
    default_model: str = "fake"
    telegram_bot_token: str = ""
    channel_workflow_id: str = ""
    default_max_tool_steps: int = 4
    default_run_token_ceiling: int = 200_000
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
