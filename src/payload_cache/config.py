from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration, read from environment variables prefixed with ``CACHE_``."""

    model_config = SettingsConfigDict(env_prefix="CACHE_", env_file=".env", extra="ignore")

    # SQLite keeps local runs and tests dependency-free; docker-compose points this at Postgres.
    database_url: str = "sqlite+aiosqlite:///./payload_cache.db"

    # Simulated latency of the external transformer service. Makes cache hits visible
    # when exercising the service with the CLI.
    transformer_delay_seconds: float = Field(default=0.2, ge=0)

    # Cap on parallel calls to the external service: real providers (LLM APIs especially)
    # rate-limit, and a large request must not fan out into hundreds of simultaneous calls.
    transformer_max_concurrency: int = Field(default=10, gt=0)

    # Upper bounds on request size: a single request must not be able to trigger an
    # unbounded number of (potentially paid) transformer calls or blow up memory.
    max_list_length: int = Field(default=1_000, gt=0)
    max_string_length: int = Field(default=1_000, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
