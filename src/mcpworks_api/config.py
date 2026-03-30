"""Application configuration using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Domain Configuration (OSS self-hosting)
    base_domain: str = Field(
        default="mcpworks.io",
        description="Root domain for all URL generation, subdomain routing, and access validation",
    )
    base_scheme: str = Field(
        default="https",
        description="URL scheme for generated URLs (https or http)",
    )
    routing_mode: Literal["path", "subdomain", "both"] = Field(
        default="path",
        description="URL routing: path (/mcp/create/ns), subdomain (ns.create.domain), or both",
    )
    allow_registration: bool = Field(
        default=False,
        description="Whether public user registration is enabled",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://mcpworks:mcpworks_dev@localhost:5432/mcpworks",
        description="PostgreSQL connection URL with asyncpg driver",
    )
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=10, ge=0, le=30)

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # JWT - keys can be provided directly or via file paths
    jwt_private_key: str | None = Field(default=None, description="ES256 private key PEM")
    jwt_public_key: str | None = Field(default=None, description="ES256 public key PEM")
    jwt_private_key_path: Path = Field(default=Path("./keys/private.pem"))
    jwt_public_key_path: Path = Field(default=Path("./keys/public.pem"))
    jwt_access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    jwt_refresh_token_expire_days: int = Field(default=7, ge=1, le=30)
    jwt_algorithm: str = "ES256"
    jwt_issuer: str = Field(default="")
    jwt_audience: str = Field(default="")

    @field_validator("jwt_private_key", "jwt_public_key", mode="before")
    @classmethod
    def parse_pem_key(cls, v: str | None) -> str | None:
        """Convert escaped newlines in PEM keys to actual newlines."""
        if v is None:
            return None
        return v.replace("\\n", "\n")

    # Stripe - PRICING.md v7.0.0 Value Ladder
    stripe_secret_key: str = Field(default="sk_test_placeholder")
    stripe_webhook_secret: str = Field(default="whsec_placeholder")
    stripe_price_pro_monthly: str = Field(default="price_pro_monthly_placeholder")
    stripe_price_pro_annual: str = Field(default="price_pro_annual_placeholder")
    stripe_price_enterprise_monthly: str = Field(default="price_enterprise_monthly_placeholder")
    stripe_price_enterprise_annual: str = Field(default="price_enterprise_annual_placeholder")
    stripe_price_dedicated_monthly: str = Field(default="price_dedicated_monthly_placeholder")
    stripe_price_dedicated_annual: str = Field(default="price_dedicated_annual_placeholder")

    # Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    prometheus_enabled: bool = True
    sentry_dsn: str | None = Field(
        default=None, description="ORDER-013: Sentry DSN for error tracking"
    )

    # Security
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
        ]
    )

    # Rate Limiting
    rate_limit_auth_failures_per_minute: int = Field(default=5, ge=1, le=60)
    rate_limit_requests_per_hour: int = Field(default=1000, ge=100, le=10000)

    # Admin
    admin_emails: list[str] = Field(default_factory=lambda: ["admin@mcpworks.io"])
    admin_api_key: str = Field(
        default="",
        description="Static API key for admin endpoints (X-Admin-Key header)",
    )

    # Internal API URL (for intra-container calls like Discord gateway)
    internal_api_url: str = Field(default="http://localhost:8000")

    # OAuth Providers
    oauth_google_client_id: str = Field(default="")
    oauth_google_client_secret: str = Field(default="")
    oauth_github_client_id: str = Field(default="")
    oauth_github_client_secret: str = Field(default="")
    oauth_state_secret: str = Field(default="")

    # Email - Resend
    resend_api_key: str = Field(default="")
    resend_from_email: str = Field(default="noreply@mcpworks.io")
    email_provider: str = Field(default="resend")

    # Email - SMTP (alternative to Resend for self-hosted)
    smtp_host: str = Field(default="", description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_username: str = Field(default="", description="SMTP authentication username")
    smtp_password: str = Field(default="", description="SMTP authentication password")
    smtp_from_email: str = Field(default="", description="SMTP sender address")
    smtp_use_tls: bool = Field(default=True, description="Whether to use STARTTLS")

    # Tier Execution Limits (monthly) - per PRICING.md v7.0.0
    tier_executions_trial: int = Field(default=125_000)
    tier_executions_pro: int = Field(default=250_000)
    tier_executions_enterprise: int = Field(default=1_000_000)
    tier_executions_dedicated: int = Field(default=-1)

    # Envelope Encryption (AES-256-GCM KEK for agent secrets)
    encryption_kek_b64: str = Field(
        default="",
        description="Base64-encoded 32-byte KEK for envelope encryption of agent secrets",
    )

    # Discord Alerts
    discord_alert_webhook_url: str = Field(default="")

    # Scratchpad
    scratchpad_base_path: str = Field(
        default="/opt/mcpworks/scratchpad",
        description="Base directory for agent scratchpad file storage",
    )
    scratchpad_max_files: int = Field(default=100, ge=1, le=1000)

    # Sandbox
    sandbox_dev_mode: bool = Field(
        default=True,
        description="Use subprocess fallback instead of nsjail (dev only)",
    )
    sandbox_config_path: Path = Field(default=Path("/etc/mcpworks/sandbox.cfg"))
    sandbox_spawn_script: Path = Field(default=Path("/opt/mcpworks/bin/spawn-sandbox.sh"))
    sandbox_rootfs_path: Path = Field(default=Path("/opt/mcpworks/rootfs"))

    def model_post_init(self, __context: Any) -> None:
        if not self.jwt_issuer:
            object.__setattr__(self, "jwt_issuer", f"{self.base_scheme}://api.{self.base_domain}")
        if not self.jwt_audience:
            object.__setattr__(self, "jwt_audience", f"{self.base_scheme}://{self.base_domain}")
        if (
            not self.resend_from_email or self.resend_from_email == "noreply@mcpworks.io"
        ) and self.base_domain != "mcpworks.io":
            object.__setattr__(self, "resend_from_email", f"noreply@{self.base_domain}")
        domain_origins = [
            f"{self.base_scheme}://{self.base_domain}",
            f"{self.base_scheme}://www.{self.base_domain}",
            f"{self.base_scheme}://api.{self.base_domain}",
        ]
        merged = list(dict.fromkeys(self.cors_origins + domain_origins))
        object.__setattr__(self, "cors_origins", merged)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            # Handle JSON-like string from env var
            if v.startswith("["):
                import json

                result: list[str] = json.loads(v)
                return result
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def api_domain(self) -> str:
        return f"api.{self.base_domain}"

    @property
    def billing_enabled(self) -> bool:
        return bool(
            self.stripe_secret_key and self.stripe_secret_key != "sk_test_placeholder"
        )  # pragma: allowlist secret


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
