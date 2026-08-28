"""
Configuration for AI Portfolio Backend.
Production configuration only.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    environment: Literal["production"] = "production"

    # Database (REQUIRED - no default)
    database_url: str

    # AI Providers (REQUIRED - no default)
    openai_api_key: str
    gigachat_auth_key: str | None = None

    # Admin Console (REQUIRED - no default)
    admin_api_token: str

    # GitHub (optional, increases rate limits for public repos)
    github_token: str | None = None

    # ChromaDB
    chroma_use_http: bool = False
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection_name: str = "ai_portfolio_knowledge"

    # Rate Limiting
    rate_limit_requests_per_minute: int = 10

    # Logging
    log_level: str = "WARNING"

    # CORS (REQUIRED - must be set)
    cors_origins: str

    # Debug
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()