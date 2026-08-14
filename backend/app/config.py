"""Environment-backed configuration for GoreeCloud Notes."""

from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path

from pydantic import Field, field_validator
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
    revision_min_interval_seconds: int = Field(default=300, ge=30, le=86_400)
    attachment_root: str = Field(default="./data/attachments")
    attachment_max_bytes: int = Field(default=52_428_800, ge=1_048_576, le=1_073_741_824)

    login_rate_window_seconds: int = Field(default=300, ge=30, le=3_600)
    login_rate_account_failures: int = Field(default=5, ge=2, le=100)
    login_rate_source_failures: int = Field(default=20, ge=3, le=500)
    login_rate_cooldown_seconds: int = Field(default=300, ge=1, le=86_400)
    login_rate_state_ttl_seconds: int = Field(default=86_400, ge=300, le=2_592_000)
    trusted_proxy_cidrs: str = Field(default="")

    database_host: str = Field(default="127.0.0.1")
    database_port: int = Field(default=5432)
    database_name: str = Field(default="goreecloud_notes")
    database_user: str = Field(default="goreecloud_notes")
    database_password: str = Field(default="development-only")
    database_password_file: str | None = Field(default=None)

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: str) -> str:
        for raw_cidr in value.split(","):
            cidr = raw_cidr.strip()
            if cidr:
                ip_network(cidr, strict=False)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_networks(self) -> tuple[IPv4Network | IPv6Network, ...]:
        return tuple(
            ip_network(raw_cidr.strip(), strict=False)
            for raw_cidr in self.trusted_proxy_cidrs.split(",")
            if raw_cidr.strip()
        )

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
