"""Environment-backed configuration for GoreeCloud Notes."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Runtime settings loaded from the environment.

    Reusable secrets must be supplied by the deployment environment and must not
    be committed to the repository. The Docker development path uses a
    file-backed PostgreSQL password that is shared with the database container.
    """

    model_config = SettingsConfigDict(
        env_prefix="GOREECLOUD_NOTES_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="development")
    api_prefix: str = Field(default="/api/v1")
    allowed_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173")
    session_ttl_seconds: int = Field(default=43_200, ge=900, le=2_592_000)

    database_host: str = Field(default="127.0.0.1")
    database_port: int = Field(default=5432)
    database_name: str = Field(default="goreecloud_notes")
    database_user: str = Field(default="goreecloud_notes")
    database_password: str = Field(default="development-only")
    database_password_file: str | None = Field(default=None)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def secure_cookies(self) -> bool:
        """Require HTTPS-only authentication cookies outside development."""

        return self.environment.strip().casefold() != "development"

    @property
    def resolved_database_password(self) -> str:
        if self.database_password_file:
            return Path(self.database_password_file).read_text(encoding="utf-8").strip()
        return self.database_password

    @property
    def database_url(self) -> str:
        url = URL.create(
            "postgresql+psycopg",
            username=self.database_user,
            password=self.resolved_database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )
        return url.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
