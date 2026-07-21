from datetime import datetime, timezone

import pytest
import requests

from app.config import Settings
from app.ingestion.github import GitHubApiError, GitHubHttpClient, GitHubIssuesConnector


class FakeGitHubClient:
    def __init__(self, issues_by_repository: dict[str, list[dict] | list[list[dict]]]) -> None:
        self.issues_by_repository = issues_by_repository
        self.calls: list[tuple[str, str, str, int, int]] = []
        self.error: Exception | None = None

    def fetch_issue_page(
        self, repository: str, state: str, sort: str, page: int, per_page: int
    ) -> list[dict]:
        self.calls.append((repository, state, sort, page, per_page))
        if self.error is not None:
            raise self.error
        configured = self.issues_by_repository[repository]
        pages = configured if not configured or isinstance(configured[0], list) else [configured]
        return pages[page - 1] if page <= len(pages) else []


def _issue(number: int, **overrides) -> dict:
    issue = {
        "number": number,
        "title": "Feature request: reduce manual work",
        "body": "This currently takes too much time.",
        "html_url": f"https://github.example/org/project/issues/{number}",
        "created_at": "2024-01-02T03:04:05Z",
        "user": {"login": "alice"},
        "comments": 3,
    }
    issue.update(overrides)
    return issue


def test_github_connector_maps_issues_to_utc_source_items() -> None:
    client = FakeGitHubClient({"org/project": [_issue(7)]})

    item = next(GitHubIssuesConnector(["org/project"], client=client).fetch())

    assert client.calls == [("org/project", "open", "updated", 1, 100)]
    assert item.external_id == "org/project#7"
    assert item.source == "github"
    assert item.title == "Feature request: reduce manual work"
    assert item.body == "This currently takes too much time."
    assert item.author == "alice"
    assert item.engagement_score == 3
    assert item.published_at == datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert item.raw_payload["number"] == 7


def test_github_connector_uses_settings_and_global_limit_across_repositories() -> None:
    client = FakeGitHubClient(
        {"org/one": [_issue(1), _issue(2)], "org/two": [_issue(3)]}
    )
    settings = Settings(
        github_repositories=("org/one", "org/two"),
        github_issues_limit=2,
        github_issues_state="closed",
        github_issues_sort="comments",
    )

    items = list(GitHubIssuesConnector.from_settings(settings, client=client).fetch())

    assert [item.external_id for item in items] == ["org/one#1", "org/one#2"]
    assert client.calls == [("org/one", "closed", "comments", 1, 100)]


def test_github_connector_skips_pull_requests_invalid_issues_and_duplicates() -> None:
    client = FakeGitHubClient(
        {
            "org/project": [
                _issue(1, pull_request={"url": "https://api.github.test/pr/1"}),
                _issue(2, title=""),
                _issue(3),
                _issue(3),
                _issue(4, created_at="not-a-date"),
            ]
        }
    )

    items = list(GitHubIssuesConnector(["org/project"], client=client).fetch())

    assert [item.external_id for item in items] == ["org/project#3"]


def test_limit_counts_only_valid_issues_after_a_pull_request() -> None:
    client = FakeGitHubClient(
        {"org/project": [_issue(1, pull_request={}), _issue(2)]}
    )

    items = list(GitHubIssuesConnector(["org/project"], limit=1, client=client).fetch())

    assert [item.external_id for item in items] == ["org/project#2"]


def test_connector_continues_to_next_page_when_a_full_page_has_only_pull_requests() -> None:
    pull_requests = [_issue(number, pull_request={}) for number in range(1, 101)]
    client = FakeGitHubClient({"org/project": [pull_requests, [_issue(101), _issue(102)]]})

    items = list(GitHubIssuesConnector(["org/project"], limit=2, client=client).fetch())

    assert [item.external_id for item in items] == ["org/project#101", "org/project#102"]
    assert client.calls == [
        ("org/project", "open", "updated", 1, 100),
        ("org/project", "open", "updated", 2, 100),
    ]


def test_incomplete_records_and_duplicates_do_not_consume_the_global_limit() -> None:
    client = FakeGitHubClient(
        {"org/project": [_issue(1, title=""), _issue(2), _issue(2), _issue(3)]}
    )

    items = list(GitHubIssuesConnector(["org/project"], limit=2, client=client).fetch())

    assert [item.external_id for item in items] == ["org/project#2", "org/project#3"]


def test_global_limit_is_shared_across_repositories_and_stops_requests_immediately() -> None:
    client = FakeGitHubClient(
        {"org/one": [_issue(1)], "org/two": [_issue(2)], "org/three": [_issue(3)]}
    )

    items = list(GitHubIssuesConnector(["org/one", "org/two", "org/three"], limit=2, client=client).fetch())

    assert [item.external_id for item in items] == ["org/one#1", "org/two#2"]
    assert client.calls == [
        ("org/one", "open", "updated", 1, 100),
        ("org/two", "open", "updated", 1, 100),
    ]


def test_connector_returns_all_valid_issues_when_repositories_are_exhausted() -> None:
    client = FakeGitHubClient({"org/one": [_issue(1)], "org/two": [_issue(2)]})

    items = list(GitHubIssuesConnector(["org/one", "org/two"], limit=5, client=client).fetch())

    assert [item.external_id for item in items] == ["org/one#1", "org/two#2"]


def test_repository_case_is_canonical_for_source_item_identity() -> None:
    upper_client = FakeGitHubClient({"org/repo": [_issue(7)]})
    lower_client = FakeGitHubClient({"org/repo": [_issue(7)]})

    upper = next(GitHubIssuesConnector(["Org/Repo"], client=upper_client).fetch())
    lower = next(GitHubIssuesConnector(["org/repo"], client=lower_client).fetch())

    assert upper.external_id == lower.external_id == "org/repo#7"
    assert upper.source == lower.source == "github"


def test_repository_normalization_preserves_order_and_rejects_case_insensitive_duplicates() -> None:
    connector = GitHubIssuesConnector(["Org/One", "SECOND/Two"], client=FakeGitHubClient({}))

    assert connector.repositories == ("org/one", "second/two")
    with pytest.raises(ValueError, match="duplicate GitHub repository"):
        GitHubIssuesConnector(["Org/Repo", "org/repo"], client=FakeGitHubClient({}))


@pytest.mark.parametrize(
    "repositories, limit, state, sort",
    [
        ([], 1, "open", "updated"),
        (["invalid"], 1, "open", "updated"),
        (["org/project"], 0, "open", "updated"),
        (["org/project"], 1, "invalid", "updated"),
        (["org/project"], 1, "open", "invalid"),
    ],
)
def test_github_connector_validates_configuration(repositories, limit, state, sort) -> None:
    with pytest.raises((TypeError, ValueError)):
        GitHubIssuesConnector(repositories, limit=limit, state=state, sort=sort)


def test_github_connector_propagates_api_errors() -> None:
    client = FakeGitHubClient({"org/project": []})
    client.error = GitHubApiError("rate limited")

    with pytest.raises(GitHubApiError, match="rate limited"):
        list(GitHubIssuesConnector(["org/project"], client=client).fetch())


def test_github_http_client_uses_token_and_wraps_request_errors(monkeypatch) -> None:
    observed = {}

    def failed_get(url, **kwargs):
        observed.update(url=url, **kwargs)
        raise requests.RequestException("network unavailable")

    monkeypatch.setattr("app.ingestion.github.requests.get", failed_get)

    with pytest.raises(GitHubApiError, match="GitHub API request failed"):
        GitHubHttpClient(token="secret").fetch_issue_page(
            "org/project", "open", "updated", page=1, per_page=10
        )

    assert observed["url"] == "https://api.github.com/repos/org/project/issues"
    assert observed["headers"]["Authorization"] == "Bearer secret"
    assert observed["params"] == {
        "state": "open", "sort": "updated", "direction": "desc", "per_page": 10, "page": 1
    }
