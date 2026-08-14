"""Environment-backed configuration for GoreeCloud Notes."""

from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Runtime settings loaded from the environment.

    Reusable secrets must be supplied by the deployment environment and must not
    be committed to the repository. The Docker development path uses a
    file-backed PostgreSQL password that is shared with the database container.

    Production mode deliberately fails closed when development placeholders or
    publication assumptions remain unresolved. This is source-level protection;
    target-environment values still require separate operational verification.
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

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test, or production")
        return normalized

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith("/") or cleaned == "/" or cleaned.endswith("/"):
            raise ValueError("api_prefix must be an absolute non-root path without a trailing slash")
        return cleaned

    @field_validator("allowed_origins")
    @classmethod
    def validate_allowed_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("at least one allowed origin is required")

        for origin in origins:
            if "*" in origin:
                raise ValueError("wildcard CORS origins are not allowed with credentialed requests")
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"invalid allowed origin: {origin}")
        return ",".join(origins)

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: str) -> str:
        for raw_cidr in value.split(","):
            cidr = raw_cidr.strip()
            if cidr:
                ip_network(cidr, strict=False)
        return value

    @model_validator(mode="after")
    def validate_production_boundary(self) -> "Settings":
        if not self.is_production:
            return self

        failures: list[str] = []
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "https":
                failures.append("production allowed origins must use https")
                continue

            hostname = parsed.hostname or ""
            if hostname.casefold() == "localhost":
                failures.append("production allowed origins must not use localhost")
                continue
            try:
                if ip_address(hostname).is_loopback:
                    failures.append("production allowed origins must not use loopback addresses")
            except ValueError:
                pass

        if not self.trusted_proxy_networks:
            failures.append("production requires verified trusted proxy CIDRs")

        attachment_root = Path(self.attachment_root).expanduser()
        if not attachment_root.is_absolute():
            failures.append("production attachment_root must be an absolute path")

        if not self.database_password_file:
            failures.append("production requires database_password_file instead of an inline database password")
        else:
            password_path = Path(self.database_password_file).expanduser()
            if not password_path.is_absolute():
                failures.append("production database_password_file must be an absolute path")

        if failures:
            raise ValueError("unsafe production configuration: " + "; ".join(dict.fromkeys(failures)))
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

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

        return self.environment != "development"

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
