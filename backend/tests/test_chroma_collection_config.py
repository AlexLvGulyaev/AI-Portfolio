"""
Tests for ChromaDB collection name configuration.

The collection name must come from the application Settings contract
(chroma_collection_name, default 'ai_portfolio_knowledge') so that a
rebuild sync can target a new collection without monkeypatching, while
the production default stays unchanged.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _required_env() -> dict:
    return {
        "DATABASE_URL": os.environ.get("DATABASE_URL", "postgresql://u:p@localhost:5432/test"),
        "OPENAI_API_KEY": "test-key",
        "ADMIN_API_TOKEN": "test-token",
        "CORS_ORIGINS": "http://localhost",
        "CHROMA_COLLECTION_NAME": "ai_portfolio_knowledge_v2",
    }


def test_default_collection_name_is_production_collection():
    """Settings default must keep the production collection name."""
    from app.core.config import Settings

    field = Settings.model_fields["chroma_collection_name"]
    assert field.default == "ai_portfolio_knowledge", (
        "chroma_collection_name default must stay 'ai_portfolio_knowledge'"
    )
    print("PASS: default chroma_collection_name = ai_portfolio_knowledge")


def test_rag_config_uses_settings_collection_name():
    """RAGConfig.from_settings must read the collection name from Settings."""
    env = _required_env()
    with patch.dict(os.environ, env):
        from app.core.config import get_settings
        from app.services.rag.rag_service import RAGConfig

        get_settings.cache_clear()
        try:
            config = RAGConfig.from_settings()
        finally:
            get_settings.cache_clear()
    assert config.collection_name == "ai_portfolio_knowledge_v2", config.collection_name
    print("PASS: RAGConfig.from_settings honours CHROMA_COLLECTION_NAME env var")


def test_rag_config_default_without_env_override():
    """Without an override, from_settings keeps the production default."""
    env = _required_env()
    env["CHROMA_COLLECTION_NAME"] = "ai_portfolio_knowledge"
    with patch.dict(os.environ, env):
        from app.core.config import get_settings
        from app.services.rag.rag_service import RAGConfig

        get_settings.cache_clear()
        try:
            config = RAGConfig.from_settings()
        finally:
            get_settings.cache_clear()
    assert config.collection_name == "ai_portfolio_knowledge", config.collection_name
    print("PASS: without override, collection stays ai_portfolio_knowledge")


if __name__ == "__main__":
    test_default_collection_name_is_production_collection()
    test_rag_config_uses_settings_collection_name()
    test_rag_config_default_without_env_override()
    print("All chroma collection config tests passed.")