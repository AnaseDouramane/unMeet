from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

import requests

from app.config import Settings
from app.ingestion.base import SourceConnector
from app.ingestion.schemas import SourceItem


class GitHubApiError(RuntimeError):
    pass


class GitHubIssuesClient(Protocol):
    def fetch_issue_page(
        self, repository: str, state: str, sort: str, page: int, per_page: int
    ) -> list[dict[str, Any]]: ...


class GitHubHttpClient:
    base_url = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout_seconds: float = 10.0) -> None:
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise TypeError("timeout_seconds must be numeric")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._token = token.strip() if isinstance(token, str) and token.strip() else None
        self._timeout_seconds = float(timeout_seconds)

    def fetch_issue_page(
        self, repository: str, state: str, sort: str, page: int, per_page: int
    ) -> list[dict[str, Any]]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = requests.get(
                f"{self.base_url}/repos/{repository}/issues",
                params={
                    "state": state,
                    "sort": sort,
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page,
                },
                headers=headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise GitHubApiError("GitHub API returned an unexpected issues payload")
        except requests.RequestException as error:
            raise GitHubApiError(f"GitHub API request failed: {error}") from error
        except ValueError as error:
            raise GitHubApiError("GitHub API returned invalid JSON") from error
        return [item for item in payload if isinstance(item, dict)]


class GitHubIssuesConnector(SourceConnector):
    source = "github"
    _SUPPORTED_STATES = frozenset({"open", "closed", "all"})
    _SUPPORTED_SORTS = frozenset({"created", "updated", "comments"})

    def __init__(
        self,
        repositories: Sequence[str],
        limit: int = 100,
        state: str = "open",
        sort: str = "updated",
        client: GitHubIssuesClient | None = None,
        token: str | None = None,
    ) -> None:
        self.repositories = self._normalize_repositories(repositories)
        self.limit = self._normalize_limit(limit)
        self.state = self._normalize_state(state)
        self.sort = self._normalize_sort(sort)
        self._client = client or GitHubHttpClient(token=token)

    @classmethod
    def from_settings(
        cls, settings: Settings, client: GitHubIssuesClient | None = None
    ) -> "GitHubIssuesConnector":
        return cls(
            repositories=settings.github_repositories,
            limit=settings.github_issues_limit,
            state=settings.github_issues_state,
            sort=settings.github_issues_sort,
            token=settings.github_token,
            client=client,
        )

    def fetch(self) -> Iterable[SourceItem]:
        yielded = 0
        seen_external_ids: set[str] = set()
        for repository in self.repositories:
            if yielded >= self.limit:
                return
            page = 1
            while yielded < self.limit:
                issues = self._client.fetch_issue_page(
                    repository, self.state, self.sort, page=page, per_page=100
                )
                for issue in issues:
                    source_item = self._to_source_item(repository, issue)
                    if source_item is None or source_item.external_id in seen_external_ids:
                        continue
                    seen_external_ids.add(source_item.external_id)
                    yielded += 1
                    yield source_item
                    if yielded >= self.limit:
                        return
                if len(issues) < 100:
                    break
                page += 1

    @classmethod
    def _to_source_item(cls, repository: str, issue: dict[str, Any]) -> SourceItem | None:
        if "pull_request" in issue:
            return None
        number = issue.get("number")
        title = issue.get("title")
        created_at = issue.get("created_at")
        html_url = issue.get("html_url")
        if isinstance(number, bool) or not isinstance(number, int):
            return None
        if not isinstance(title, str) or not title.strip():
            return None
        if not isinstance(html_url, str) or not html_url.strip():
            return None
        published_at = cls._parse_timestamp(created_at)
        if published_at is None:
            return None
        user = issue.get("user")
        author = user.get("login") if isinstance(user, dict) else None
        comments = issue.get("comments")
        return SourceItem(
            external_id=f"{repository}#{number}",
            source=cls.source,
            title=title,
            body=issue.get("body") if isinstance(issue.get("body"), str) else "",
            url=html_url,
            author=author if isinstance(author, str) and author.strip() else None,
            published_at=published_at,
            engagement_score=(comments if isinstance(comments, int) and not isinstance(comments, bool) else None),
            raw_payload=issue,
        )

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _normalize_repositories(repositories: Sequence[str]) -> tuple[str, ...]:
        if isinstance(repositories, (str, bytes)):
            raise TypeError("repositories must be a sequence of owner/repository names")
        normalized: list[str] = []
        seen: set[str] = set()
        for repository in repositories:
            if not isinstance(repository, str) or not repository.strip():
                raise ValueError("repository names must be non-empty strings")
            value = repository.strip().strip("/").lower()
            if value.count("/") != 1 or any(not part for part in value.split("/")):
                raise ValueError("repository names must use owner/repository format")
            if value in seen:
                raise ValueError(f"duplicate GitHub repository: {value}")
            seen.add(value)
            normalized.append(value)
        if not normalized:
            raise ValueError("at least one GitHub repository must be configured")
        return tuple(normalized)

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("GitHub issues limit must be a positive integer")
        return limit

    @classmethod
    def _normalize_state(cls, state: str) -> str:
        if not isinstance(state, str) or state not in cls._SUPPORTED_STATES:
            raise ValueError("GitHub issues state must be 'open', 'closed', or 'all'")
        return state

    @classmethod
    def _normalize_sort(cls, sort: str) -> str:
        if not isinstance(sort, str) or sort not in cls._SUPPORTED_SORTS:
            raise ValueError("GitHub issues sort must be 'created', 'updated', or 'comments'")
        return sort
