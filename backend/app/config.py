"""Environment-backed configuration for GoreeCloud Notes."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from the environment.

    Reusable secrets must be supplied by the deployment environment and must not
    be committed to the repository.
    """

    model_config = SettingsConfigDict(
        env_prefix="GOREECLOUD_NOTES_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="development")
    database_url: str = Field(
        default="postgresql+psycopg://goreecloud_notes:development-only@127.0.0.1:5432/goreecloud_notes"
    )
    api_prefix: str = Field(default="/api/v1")
    allowed_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
