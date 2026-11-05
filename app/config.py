"""Application settings loaded from environment variables.

Configuration is read once at startup and cached. Values are sourced from
``DATABASE_URL`` and ``OPENROUTER_API_KEY`` via ``os.getenv`` so the package
works locally and inside the docker-compose ``web`` service without extra
dependencies.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/helpdesk_db"
)


class Settings(BaseModel):
    """Runtime configuration of the helpdesk service."""

    database_url: str = DEFAULT_DATABASE_URL
    openrouter_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the process environment."""
        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached instance of the settings."""
    return Settings.from_env()
