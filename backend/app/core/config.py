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
    # Registry-only KB policy, condition 3 (owner decision 29.08.2026, model A,
    # variant В2): only repositories of this namespace are admissible as
    # knowledge sources. REQUIRED per-deployment configuration — no personal
    # values in code; the fail-closed guard refuses to run without it just
    # like ADMIN_API_TOKEN. Together with the live existence probe this
    # closes the "foreign repository" admission hole.
    kb_repo_owner: str

    # ChromaDB
    chroma_use_http: bool = False
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection_name: str = "ai_portfolio_knowledge"

    # Retrieval console (env bootstrap; PG platform_settings overrides, AF P6.12 pattern)
    # Runtime: applies to queries without rebuild
    rag_top_k: int = 6
    rag_max_distance: float = 10.0  # 0.1..10.0; 10.0 practically disables distance filtering
    retrieval_recall_margin: int = 3  # HNSW recall oversample (RECALL_MARGIN live finding 29.08.2026)
    # AF-parity runtime keys (owner decision 29.08.2026, WH-2):
    rag_answer_max_tokens: int = 800  # generation cap (AF: max_tokens of the chat completion)
    rag_retrieval_timeout: int = 30  # hard timeout of the retrieval step, sec (AF: per-step worker timeout)
    rag_embedding_request_timeout: float = 30.0  # OpenAI embeddings client timeout, sec
    # Retrieval cache (WH-1, AF caching_retrieval_backend pattern; owner decision 29.08.2026):
    enable_retrieval_cache: bool = False  # default OFF — the console toggle turns it on
    retrieval_cache_ttl_seconds: int = 86400  # env TTL; PG platform_settings may override in v2
    rag_retrieval_generation: int = 1  # env bootstrap; PG counter wins, auto-increment on successful sync
    # Backend build-time: used when creating a chroma collection (clear/recreate/reindex)
    chroma_ef_search: int = 100
    chroma_ef_construction: int = 100
    # Indexing: chunking (full reindex required after change)
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50

    # Weaviate (secondary retrieval backend, BYOV vectors)
    rag_backend: str = "chroma"  # chroma | weaviate (PG platform_settings wins when valid)
    weaviate_host: str = "ai-portfolio-weaviate"
    weaviate_http_port: int = 8080
    weaviate_grpc_port: int = 50051
    weaviate_class_name: str = "AiPortfolioChunk"

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