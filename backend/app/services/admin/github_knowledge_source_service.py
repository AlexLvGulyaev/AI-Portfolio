"""
GitHub Knowledge Source service.

Fetches markdown documents from public GitHub repositories and stores them
in PostgreSQL as intermediate cache before ChromaDB indexing.

Reads:
- README.md
- docs/**/*.md

Ignores:
- task_history/
- attachments/
- screenshots/
- node_modules/
- .git/
- non-markdown files
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
import markdown
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import KnowledgeDocument, KnowledgeSource, KnowledgeSyncError


@dataclass
class GitHubFile:
    """Raw file fetched from GitHub."""

    path: str
    title: Optional[str]
    content: str
    raw_url: str
    commit_sha: Optional[str] = None


@dataclass
class GitHubFetchResult:
    """Result of fetching files from a GitHub repository."""

    files: list[GitHubFile] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


class GitHubKnowledgeSourceService:
    """Fetch markdown documents from a GitHub repository."""

    GITHUB_API_BASE = "https://api.github.com"
    RAW_GITHUB_BASE = "https://raw.githubusercontent.com"

    IGNORED_PATHS = {"task_history", "attachments", "screenshots", "node_modules", ".git"}

    def __init__(self, db: Session) -> None:
        self._db = db
        self._token = get_settings().github_token
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Portfolio-KB-Sync",
        }
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        self._client = httpx.Client(headers=headers, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def fetch_source(self, source: KnowledgeSource) -> GitHubFetchResult:
        """Fetch all markdown files from a github_repo source."""
        result = GitHubFetchResult()

        if source.source_type != "github_repo":
            result.errors.append({
                "path": source.identifier,
                "error_type": "invalid_source_type",
                "error_message": f"Expected github_repo, got {source.source_type}",
            })
            return result

        owner, repo = self._parse_identifier(source.identifier)
        if not owner or not repo:
            result.errors.append({
                "path": source.identifier,
                "error_type": "invalid_identifier",
                "error_message": "Identifier must be in format owner/repo",
            })
            return result

        branch = source.branch or "main"
        base_path = (source.base_path or "").strip("/")

        try:
            paths = self._discover_markdown_paths(owner, repo, branch, base_path)
        except Exception as exc:
            result.errors.append({
                "path": source.identifier,
                "error_type": "discovery_failed",
                "error_message": f"{type(exc).__name__}: {exc}",
            })
            return result

        for path in paths:
            try:
                file = self._fetch_file(owner, repo, branch, path)
                result.files.append(file)
            except Exception as exc:
                result.errors.append({
                    "path": path,
                    "error_type": "fetch_failed",
                    "error_message": f"{type(exc).__name__}: {exc}",
                })

        return result

    def save_fetched_files(
        self,
        source_id: UUID,
        files: list[GitHubFile],
        errors: list[dict[str, Any]],
    ) -> None:
        """Persist fetched files and errors to PostgreSQL."""
        # Delete old documents for this source
        self._db.query(KnowledgeDocument).filter(
            KnowledgeDocument.source_id == source_id
        ).delete(synchronize_session=False)

        # Insert new documents
        now = datetime.now(timezone.utc)
        for file in files:
            doc = KnowledgeDocument(
                source_id=source_id,
                path=file.path,
                title=file.title or self._extract_title(file.content, file.path),
                content=file.content,
                raw_url=file.raw_url,
                commit_sha=file.commit_sha,
                fetched_at=now,
                created_at=now,
                updated_at=now,
            )
            self._db.add(doc)

        # Insert errors
        for error in errors:
            err = KnowledgeSyncError(
                source_id=source_id,
                path=error.get("path"),
                error_type=error.get("error_type"),
                error_message=error.get("error_message"),
            )
            self._db.add(err)

        self._db.commit()

    @staticmethod
    def _parse_identifier(identifier: str) -> tuple[Optional[str], Optional[str]]:
        parts = identifier.strip("/").split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, None

    def _api_request(self, url: str) -> dict[str, Any]:
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    def _discover_markdown_paths(
        self,
        owner: str,
        repo: str,
        branch: str,
        base_path: str,
    ) -> list[str]:
        """Recursively discover README.md and docs/**/*.md."""
        paths: list[str] = []

        # Always include README.md at the root
        root_readme = f"{base_path}/README.md" if base_path else "README.md"
        paths.append(root_readme)

        docs_path = f"{base_path}/docs" if base_path else "docs"
        self._collect_tree_paths(owner, repo, branch, docs_path, paths)

        # Deduplicate and sort
        return sorted(set(paths))

    def _collect_tree_paths(
        self,
        owner: str,
        repo: str,
        branch: str,
        path: str,
        paths: list[str],
    ) -> None:
        """Recursively collect markdown file paths from a GitHub tree."""
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={branch}"

        try:
            items = self._api_request(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return  # Directory does not exist
            raise

        if not isinstance(items, list):
            return

        for item in items:
            item_path = item.get("path", "")
            item_type = item.get("type", "")

            if self._is_ignored(item_path):
                continue

            if item_type == "file" and item_path.endswith(".md"):
                paths.append(item_path)
            elif item_type == "dir":
                self._collect_tree_paths(owner, repo, branch, item_path, paths)

    def _fetch_file(
        self,
        owner: str,
        repo: str,
        branch: str,
        path: str,
    ) -> GitHubFile:
        """Fetch a single file from GitHub (raw or via API)."""
        raw_url = f"{self.RAW_GITHUB_BASE}/{owner}/{repo}/{branch}/{path}"
        response = self._client.get(raw_url)
        response.raise_for_status()
        raw_content = response.text
        plain_content = self._markdown_to_plain_text(raw_content)

        return GitHubFile(
            path=path,
            title=None,  # extracted later from content
            content=plain_content,
            raw_url=raw_url,
            commit_sha=None,  # can be enhanced via commits API later
        )

    @staticmethod
    def _markdown_to_plain_text(md_content: str) -> str:
        """Convert markdown to plain text suitable for embeddings."""
        # Convert markdown to HTML
        html = markdown.markdown(md_content)

        # Strip HTML tags
        text = re.sub(r"<[^>]+", "", html)

        # Decode common HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')

        # Normalize whitespace
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _is_ignored(self, path: str) -> bool:
        parts = path.split("/")
        return any(part in self.IGNORED_PATHS for part in parts)

    @staticmethod
    def _extract_title(content: str, fallback: str) -> str:
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return fallback
