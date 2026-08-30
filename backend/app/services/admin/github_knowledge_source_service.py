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

Admission gate: files are additionally filtered by the shared kb_admission
selection (source admission_status + include/exclude path patterns) before
any download; excluded files never reach chunking/embeddings/ChromaDB.
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
from app.services.admin import kb_admission


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
    # Structured admission-gate skips: files excluded before download.
    skipped: list[dict[str, Any]] = field(default_factory=list)


# Error types emitted when the file listing itself could not be produced
# (repo discovery failed, or the source identifier/branch is unusable).
# In these cases the fetch never saw a valid file set, so existing
# documents for the source must be preserved, not replaced.
DISCOVERY_FAILURE_TYPES = frozenset({
    "discovery_failed",
    "invalid_identifier",
    "invalid_source_type",
})


def has_discovery_failure(errors: list[dict[str, Any]]) -> bool:
    """True when discovery did not complete, so existing documents must be kept."""
    return any(e.get("error_type") in DISCOVERY_FAILURE_TYPES for e in errors)


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

    def discover_paths(self, source: KnowledgeSource) -> list[str]:
        """Return markdown file paths of a github_repo source without downloading content."""
        if source.source_type != "github_repo":
            raise ValueError(f"Expected github_repo, got {source.source_type}")

        owner, repo = self._parse_identifier(source.identifier)
        if not owner or not repo:
            raise ValueError("Identifier must be in format owner/repo")

        branch = source.branch or "main"
        base_path = (source.base_path or "").strip("/")
        return self._discover_markdown_paths(owner, repo, branch, base_path)

    def probe_repo(self, owner: str, repo: str) -> Optional[bool]:
        """Cheap existence probe for the source-creation guard (owner decision
        29.08.2026, model "A", variant В2).

        Returns:
            True  - repository exists (GET /repos/{owner}/{repo} → 200);
            False - GitHub confirms the repository is missing (404);
            None  - GitHub unreachable or unexpected status; the caller
                    (KB source admission) fails closed on None.
        """
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}"
        try:
            response = self._client.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        return None

    def list_owner_repos(self, owner: str) -> Optional[list[dict[str, Any]]]:
        """List public repositories of the KB registry owner (owner decision
        29.08.2026: after the namespace guard the add-source select is fed
        straight from GitHub instead of free-text input).

        Returns:
            list of dicts on success (identifier/name/description/updated_at),
            None on unreachable GitHub or unexpected status — the caller
            (KB admission UI endpoint) fails closed with 503.
        """
        url = f"{self.GITHUB_API_BASE}/users/{owner}/repos"
        params = {"type": "owner", "sort": "updated", "per_page": 100}
        try:
            response = self._client.get(url, params=params)
        except httpx.HTTPError:
            return None
        if response.status_code != 200 or not isinstance(response.json(), list):
            return None
        repos: list[dict[str, Any]] = []
        for item in response.json():
            name = item.get("name", "")
            if not name:
                continue
            repos.append({
                "identifier": f"{owner}/{name}",
                "name": name,
                "description": item.get("description"),
                "updated_at": item.get("updated_at"),
                "archived": bool(item.get("archived", False)),
            })
        return repos

    def fetch_head_commit(self, owner: str, repo: str, branch: str) -> Optional[str]:
        """Return the current head commit SHA of a branch via the GitHub API.

        Used by the Admission Console for stale-preview protection
        (§4.5а): a preview built at commit X must not be approved after the
        branch advanced. Raises on HTTP/network errors; callers decide how
        to treat unreachability.
        """
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{branch}"
        payload = self._api_request(url)
        sha = payload.get("sha") if isinstance(payload, dict) else None
        return sha or None

    def fetch_source(self, source: KnowledgeSource) -> GitHubFetchResult:
        """Fetch all admitted markdown files from a github_repo source.

        Admission gate enforcement: only files admitted by the shared
        kb_admission selection are downloaded and ingested. Excluded files
        are recorded as structured skips and never reach chunking,
        embeddings, or ChromaDB.
        """
        result = GitHubFetchResult()

        try:
            paths = self.discover_paths(source)
        except ValueError as exc:
            error_type = (
                "invalid_source_type"
                if str(exc).startswith("Expected github_repo")
                else "invalid_identifier"
            )
            result.errors.append({
                "path": source.identifier,
                "error_type": error_type,
                "error_message": str(exc),
            })
            return result
        except Exception as exc:
            result.errors.append({
                "path": source.identifier,
                "error_type": "discovery_failed",
                "error_message": f"{type(exc).__name__}: {exc}",
            })
            return result

        owner, repo = self._parse_identifier(source.identifier)
        branch = source.branch or "main"

        decisions = kb_admission.select_files(
            paths,
            source.admission_status,
            source.include_patterns,
            source.exclude_patterns,
        )

        for decision in decisions:
            if not decision.included:
                result.skipped.append({
                    "path": decision.path,
                    "skip_type": "admission_excluded",
                    "reason": decision.reason,
                })
                continue
            try:
                file = self._fetch_file(owner, repo, branch, decision.path)
                result.files.append(file)
            except Exception as exc:
                result.errors.append({
                    "path": decision.path,
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
        # Fail-closed: if discovery itself failed we cannot know the current
        # file set, so existing documents must be kept. Deleting first and
        # failing later would lose PostgreSQL data while ChromaDB chunks
        # (removed only incrementally during re-indexing) survive.
        if has_discovery_failure(errors):
            for error in errors:
                err = KnowledgeSyncError(
                    source_id=source_id,
                    path=error.get("path"),
                    error_type=error.get("error_type"),
                    error_message=error.get("error_message"),
                )
                self._db.add(err)
            self._db.commit()
            return

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
        """Recursively discover all markdown files in the repository.

        Discovery covers the whole repository tree (not only docs/);
        the admission gate selects from this universe by include/exclude
        patterns. Internal directories (task_history, attachments,
        screenshots, ...) are filtered by IGNORED_PATHS.
        """
        paths: list[str] = []

        # Always include README.md at the root
        root_readme = f"{base_path}/README.md" if base_path else "README.md"
        paths.append(root_readme)

        root = base_path if base_path else ""
        self._collect_tree_paths(owner, repo, branch, root, paths)

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
        clean_path = path.strip("/")
        suffix = f"/{clean_path}" if clean_path else ""
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents{suffix}?ref={branch}"

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
