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

    # Stripe - A0-SYSTEM-SPECIFICATION.md tier pricing
    stripe_secret_key: str = Field(default="sk_test_placeholder")
    stripe_webhook_secret: str = Field(default="whsec_placeholder")
    stripe_price_founder: str = Field(default="price_founder_placeholder")  # $29/mo
    stripe_price_founder_pro: str = Field(default="price_founder_pro_placeholder")  # $59/mo
    stripe_price_enterprise: str = Field(default="price_enterprise_placeholder")  # $129+/mo

    # Backend Services
    math_service_url: str = Field(
        default="http://localhost:8001",
        description="URL for mcpworks-math service",
    )
    agent_service_url: str = Field(
        default="http://localhost:8002",
        description="URL for mcpworks-agent service",
    )
    agent_callback_secret: str = Field(
        default="",
        description="Shared secret for agent callback authentication (required in production)",
    )
    service_timeout_seconds: int = Field(default=30, ge=5, le=300)

    # Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    prometheus_enabled: bool = True

    # Security
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Rate Limiting
    rate_limit_auth_failures_per_minute: int = Field(default=5, ge=1, le=60)
    rate_limit_requests_per_hour: int = Field(default=1000, ge=100, le=10000)

    # Admin
    admin_emails: list[str] = Field(default_factory=lambda: ["simon.carr@gmail.com"])

    # Tier Execution Limits (monthly) - per PRICING.md
    tier_executions_free: int = Field(default=100)
    tier_executions_founder: int = Field(default=1_000)
    tier_executions_founder_pro: int = Field(default=10_000)
    # Enterprise: -1 = unlimited (not configurable, hardcoded)

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
