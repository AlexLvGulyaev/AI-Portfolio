"""
Smoke tests for AI Portfolio services.

Validates that all services can be imported and instantiated.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uuid import uuid4
from datetime import datetime


def test_imports():
    """Test that all services can be imported."""
    print("Testing imports...")

    from app.services.memory.base import ConversationMemoryRecord, MemoryBudgetPolicy
    from app.services.conversation_memory_service import ConversationMemoryService
    from app.services.chat_session_service import ChatSessionService
    from app.services.operational_log_service import OperationalLogService
    from app.services.ai_provider_settings_service import AIProviderSettingsService
    from app.repositories.session_repository import SessionRepository

    print("✓ All imports successful")
    return True


def test_memory_contracts():
    """Test memory contracts from Assistant Flow."""
    print("\nTesting memory contracts...")

    from app.services.memory.base import ConversationMemoryRecord, MemoryBudgetPolicy

    # Test ConversationMemoryRecord
    record = ConversationMemoryRecord(
        message_id=str(uuid4()),
        session_id=str(uuid4()),
        user_id=str(uuid4()),
        role="user",
        content="Test message",
        created_at=datetime.now(),
    )
    print(f"✓ ConversationMemoryRecord created: {record.message_id}")

    # Test MemoryBudgetPolicy
    policy = MemoryBudgetPolicy()
    print(f"✓ MemoryBudgetPolicy created: max_recent={policy.max_recent_messages}, max_chars={policy.max_message_chars}")

    return True


def test_database_connection():
    """Test database connection."""
    print("\nTesting database connection...")

    from app.core.database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # Simple query to test connection
        result = db.execute(text("SELECT 1")).scalar()
        print(f"✓ Database connection successful: {result}")
        return True
    finally:
        db.close()


def test_chat_session_service():
    """Test Chat Session Service."""
    print("\nTesting Chat Session Service...")

    from app.core.database import SessionLocal
    from app.services.chat_session_service import ChatSessionService
    from uuid import uuid4

    db = SessionLocal()
    try:
        service = ChatSessionService(db)

        # Test 1: Create session
        visitor_id = str(uuid4())
        session_id = service.create_session(visitor_id, mode="text")
        print(f"✓ Created session: {session_id}")

        # Test 2: Get or create active session
        session_id2 = service.get_or_create_active_session(visitor_id, mode="text")
        print(f"✓ Got or created session: {session_id2}")
        assert session_id == session_id2, "Should return same session"

        # Test 3: Record message
        message_id = service.record_message(
            session_id=session_id,
            visitor_id=visitor_id,
            role="user",
            content="Hello, this is a test message"
        )
        print(f"✓ Recorded message: {message_id}")

        # Test 4: List messages
        messages = service.list_recent_messages_raw(session_id, limit=10)
        print(f"✓ Listed {len(messages)} messages")
        assert len(messages) == 1, "Should have 1 message"

        # Test 5: Close session
        service.close_session(session_id)
        print(f"✓ Closed session: {session_id}")

        return True
    finally:
        db.close()


def test_conversation_memory_service():
    """Test Conversation Memory Service."""
    print("\nTesting Conversation Memory Service...")

    from app.core.database import SessionLocal
    from app.services.conversation_memory_service import ConversationMemoryService
    from app.services.chat_session_service import ChatSessionService
    from uuid import uuid4

    db = SessionLocal()
    try:
        # First create a session
        session_service = ChatSessionService(db)
        visitor_id = str(uuid4())
        session_id = session_service.create_session(visitor_id, mode="text")

        # Now test conversation memory
        memory_service = ConversationMemoryService(db=db)

        # Test 1: Add message
        message_id = memory_service.add_message(
            session_id=str(session_id),
            user_id=visitor_id,
            role="user",
            content="What services do you offer?",
        )
        print(f"✓ Added message to memory: {message_id}")

        # Test 2: Add another message
        message_id2 = memory_service.add_message(
            session_id=str(session_id),
            user_id=visitor_id,
            role="assistant",
            content="I offer AI automation services...",
        )
        print(f"✓ Added response to memory: {message_id2}")

        # Test 3: Get recent messages
        messages = memory_service.get_recent_messages(str(session_id), limit=10)
        print(f"✓ Retrieved {len(messages)} messages from memory")
        assert len(messages) == 2, "Should have 2 messages"

        return True
    finally:
        db.close()


def test_operational_log_service():
    """Test Operational Log Service."""
    print("\nTesting Operational Log Service...")

    from app.core.database import SessionLocal
    from app.services.operational_log_service import OperationalLogService
    from uuid import uuid4

    db = SessionLocal()
    try:
        service = OperationalLogService(db)

        # Test 1: Log chat request
        log_id = service.log_chat_request(
            session_id=str(uuid4()),
            user_id=str(uuid4()),
            query="What services do you offer?",
            response="I offer AI automation services...",
            model_name="gpt-4.1-mini",
            provider_key="openai",
            from_cache=False,
            response_time_ms=150,
            status="ok",
        )
        print(f"✓ Logged chat request: {log_id}")

        # Test 2: Log provider switch
        log_id2 = service.log_provider_switch(
            provider_key="gigachat",
            model_name="GigaChat-Max",
            status="ok",
        )
        print(f"✓ Logged provider switch: {log_id2}")

        # Test 3: Log RAG query
        log_id3 = service.log_rag_query(
            query="search query",
            response="search result",
            from_cache=True,
            response_time_ms=50,
            status="ok",
        )
        print(f"✓ Logged RAG query: {log_id3}")

        return True
    finally:
        db.close()


def test_ai_provider_settings_service():
    """Test AI Provider Settings Service."""
    print("\nTesting AI Provider Settings Service...")

    from app.core.database import SessionLocal
    from app.services.ai_provider_settings_service import AIProviderSettingsService

    db = SessionLocal()
    try:
        service = AIProviderSettingsService(db)

        # Test 1: List all settings
        settings = service.list_settings()
        print(f"✓ Listed {len(settings)} provider settings")
        assert len(settings) == 2, "Should have 2 providers (OpenAI, GigaChat)"

        # Test 2: Get active provider
        active = service.get_active()
        print(f"✓ Active provider: {active.provider_key if active else 'None'}")
        assert active is not None, "Should have active provider"
        assert active.provider_key == "openai", "Active provider should be OpenAI"

        # Test 3: Get fallback provider
        fallback = service.get_fallback()
        print(f"✓ Fallback provider: {fallback.provider_key if fallback else 'None'}")
        assert fallback is not None, "Should have fallback provider"
        assert fallback.provider_key == "gigachat", "Fallback provider should be GigaChat"

        # Test 4: Get by key
        openai = service.get_by_key("openai")
        print(f"✓ Got provider by key: {openai.provider_key}")
        assert openai.provider_key == "openai"

        # Test 5: Get effective provider
        effective, warnings = service.get_effective_provider()
        print(f"✓ Effective provider: {effective.provider_key if effective else 'None'}")
        print(f"  Warnings: {warnings if warnings else 'None'}")
        assert effective is not None, "Should have effective provider"

        return True
    finally:
        db.close()


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("AI Portfolio Services - Smoke Tests")
    print("=" * 60)

    tests = [
        test_imports,
        test_memory_contracts,
        test_database_connection,
        test_ai_provider_settings_service,
        test_chat_session_service,
        test_conversation_memory_service,
        test_operational_log_service,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
                print(f"✓ {test.__name__} PASSED\n")
            else:
                failed += 1
                print(f"✗ {test.__name__} FAILED\n")
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} FAILED: {e}\n")

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)