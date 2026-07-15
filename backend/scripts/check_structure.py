#!/usr/bin/env python3
"""
Script to verify backend structure is correct.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_file_exists(filepath: str) -> bool:
    """Check if file exists."""
    exists = os.path.exists(filepath)
    status = "✓" if exists else "✗"
    print(f"{status} {filepath}")
    return exists


def main():
    """Check backend structure."""
    print("=" * 60)
    print("AI Portfolio Backend - Structure Verification")
    print("=" * 60)

    all_ok = True

    # Core files
    print("\nCore files:")
    all_ok &= check_file_exists("app/__init__.py")
    all_ok &= check_file_exists("app/main.py")
    all_ok &= check_file_exists("app/core/__init__.py")
    all_ok &= check_file_exists("app/core/config.py")
    all_ok &= check_file_exists("app/core/database.py")

    # Models
    print("\nModels:")
    all_ok &= check_file_exists("app/models/__init__.py")
    all_ok &= check_file_exists("app/models/entities.py")

    # Schemas
    print("\nSchemas:")
    all_ok &= check_file_exists("app/schemas/__init__.py")
    all_ok &= check_file_exists("app/schemas/provider.py")
    all_ok &= check_file_exists("app/schemas/chat.py")

    # API
    print("\nAPI:")
    all_ok &= check_file_exists("app/api/__init__.py")
    all_ok &= check_file_exists("app/api/health.py")

    # Services
    print("\nServices:")
    all_ok &= check_file_exists("app/services/__init__.py")
    all_ok &= check_file_exists("app/services/memory/__init__.py")
    all_ok &= check_file_exists("app/services/memory/base.py")
    all_ok &= check_file_exists("app/services/providers/__init__.py")
    all_ok &= check_file_exists("app/services/providers/base.py")
    all_ok &= check_file_exists("app/services/providers/factory.py")
    all_ok &= check_file_exists("app/services/providers/openai_compatible.py")
    all_ok &= check_file_exists("app/services/providers/gigachat_provider.py")
    all_ok &= check_file_exists("app/services/providers/mock_provider.py")

    # Migrations
    print("\nMigrations:")
    all_ok &= check_file_exists("alembic.ini")
    all_ok &= check_file_exists("migrations/env.py")
    all_ok &= check_file_exists("migrations/versions/001_initial.py")

    # Config files
    print("\nConfig files:")
    all_ok &= check_file_exists("requirements.txt")
    all_ok &= check_file_exists(".env.example")
    all_ok &= check_file_exists(".gitignore")
    all_ok &= check_file_exists("Dockerfile")
    all_ok &= check_file_exists("README.md")

    # Summary
    print("\n" + "=" * 60)
    if all_ok:
        print("✓ All files present")
        print("=" * 60)
        return 0
    else:
        print("✗ Some files missing")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())