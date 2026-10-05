"""Service configuration, read from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Prefix keeps our variables apart from unrelated ones in the environment.
    model_config = SettingsConfigDict(env_prefix="CACHE_")

    database_url: str = "sqlite+aiosqlite:///./cache.db"
    transformer_latency_seconds: float = Field(default=0.5, ge=0)
    # Upper bound on simultaneous calls, to avoid flooding the external service.
    transformer_max_concurrency: int = Field(default=10, ge=1)
