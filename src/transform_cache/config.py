"""Service configuration, read from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Prefix keeps our variables apart from unrelated ones in the environment.
    model_config = SettingsConfigDict(env_prefix="CACHE_")

    transformer_latency_seconds: float = Field(default=0.5, ge=0)
