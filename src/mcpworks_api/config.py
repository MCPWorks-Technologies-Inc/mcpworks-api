"""Application configuration using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    jwt_issuer: str = Field(default="https://api.mcpworks.io")
    jwt_audience: str = Field(default="https://mcpworks.io")

    @field_validator("jwt_private_key", "jwt_public_key", mode="before")
    @classmethod
    def parse_pem_key(cls, v: str | None) -> str | None:
        """Convert escaped newlines in PEM keys to actual newlines."""
        if v is None:
            return None
        return v.replace("\\n", "\n")

    # Stripe - PRICING.md v5.0.0 Value Ladder
    stripe_secret_key: str = Field(default="sk_test_placeholder")
    stripe_webhook_secret: str = Field(default="whsec_placeholder")
    stripe_price_builder_monthly: str = Field(default="price_builder_monthly_placeholder")
    stripe_price_builder_annual: str = Field(default="price_builder_annual_placeholder")
    stripe_price_pro_monthly: str = Field(default="price_pro_monthly_placeholder")
    stripe_price_pro_annual: str = Field(default="price_pro_annual_placeholder")
    stripe_price_enterprise_monthly: str = Field(default="price_enterprise_monthly_placeholder")
    stripe_price_enterprise_annual: str = Field(default="price_enterprise_annual_placeholder")

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
            "https://mcpworks.io",
            "https://www.mcpworks.io",
            "https://api.mcpworks.io",
        ]
    )

    # Rate Limiting
    rate_limit_auth_failures_per_minute: int = Field(default=5, ge=1, le=60)
    rate_limit_requests_per_hour: int = Field(default=1000, ge=100, le=10000)

    # Admin
    admin_emails: list[str] = Field(default_factory=lambda: ["simon.carr@mcpworks.io"])
    admin_api_key: str = Field(
        default="",
        description="Static API key for admin endpoints (X-Admin-Key header)",
    )

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

    # Tier Execution Limits (monthly) - per PRICING.md v5.2.0
    tier_executions_free: int = Field(default=1_000)
    tier_executions_builder: int = Field(default=25_000)
    tier_executions_pro: int = Field(default=250_000)
    tier_executions_enterprise: int = Field(default=1_000_000)

    # Envelope Encryption (AES-256-GCM KEK for agent secrets)
    encryption_kek_b64: str = Field(
        default="",
        description="Base64-encoded 32-byte KEK for envelope encryption of agent secrets",
    )

    # Discord Alerts
    discord_alert_webhook_url: str = Field(default="")

    # Sandbox
    sandbox_dev_mode: bool = Field(
        default=True,
        description="Use subprocess fallback instead of nsjail (dev only)",
    )
    sandbox_config_path: Path = Field(default=Path("/etc/mcpworks/sandbox.cfg"))
    sandbox_spawn_script: Path = Field(default=Path("/opt/mcpworks/bin/spawn-sandbox.sh"))
    sandbox_rootfs_path: Path = Field(default=Path("/opt/mcpworks/rootfs"))

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
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
