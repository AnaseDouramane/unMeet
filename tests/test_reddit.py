from datetime import UTC, datetime

import pytest
import requests

from app.config import Settings
from app.ingestion.reddit import RedditApiError, RedditConnector, RedditHttpClient


class FakeRedditClient:
    def __init__(self, posts_by_subreddit: dict[str, list[dict]]) -> None:
        self.posts_by_subreddit = posts_by_subreddit
        self.calls: list[tuple[str, str, int]] = []
        self.error: Exception | None = None

    def fetch_posts(self, subreddit: str, sort: str, limit: int) -> list[dict]:
        self.calls.append((subreddit, sort, limit))
        if self.error is not None:
            raise self.error
        return self.posts_by_subreddit[subreddit]


def _post(post_id: str, **overrides) -> dict:
    post = {
        "id": post_id,
        "title": "Need a better workflow",
        "selftext": "I manually combine reports every week.",
        "url": f"https://reddit.example/{post_id}",
        "author": "alice",
        "created_utc": 1_700_000_000,
        "score": 42,
    }
    post.update(overrides)
    return post


def test_reddit_connector_maps_a_post_to_source_item() -> None:
    client = FakeRedditClient({"startups": [_post("abc")]})

    item = next(RedditConnector(["startups"], client=client).fetch())

    assert client.calls == [("startups", "new", 100)]
    assert item.external_id == "abc"
    assert item.source == "reddit"
    assert item.title == "Need a better workflow"
    assert item.body == "I manually combine reports every week."
    assert item.url == "https://reddit.example/abc"
    assert item.author == "alice"
    assert item.published_at == datetime.fromtimestamp(1_700_000_000, tz=UTC)
    assert item.published_at.tzinfo is UTC
    assert item.engagement_score == 42
    assert item.raw_payload["id"] == "abc"


def test_reddit_connector_reads_multiple_subreddits_and_settings() -> None:
    client = FakeRedditClient({"python": [_post("one")], "startups": [_post("two")]})
    settings = Settings(reddit_subreddits=("python", "startups"), reddit_limit=3, reddit_sort="hot")

    items = list(RedditConnector.from_settings(settings, client=client).fetch())

    assert [item.external_id for item in items] == ["one", "two"]
    assert client.calls == [("python", "hot", 3), ("startups", "hot", 2)]


def test_reddit_connector_ignores_removed_deleted_and_incomplete_posts() -> None:
    client = FakeRedditClient(
        {
            "python": [
                _post("removed", selftext="[removed]"),
                _post("deleted", author="[deleted]"),
                _post("missing-title", title=None),
                _post("valid"),
            ]
        }
    )

    items = list(RedditConnector(["python"], client=client).fetch())

    assert [item.external_id for item in items] == ["valid"]


def test_reddit_connector_applies_a_global_limit() -> None:
    client = FakeRedditClient(
        {
            "python": [_post("one"), _post("two")],
            "startups": [_post("three")],
        }
    )

    items = list(RedditConnector(["python", "startups"], limit=2, client=client).fetch())

    assert [item.external_id for item in items] == ["one", "two"]
    assert client.calls == [("python", "new", 2)]


def test_reddit_connector_propagates_api_errors() -> None:
    client = FakeRedditClient({"python": []})
    client.error = RedditApiError("rate limited")

    with pytest.raises(RedditApiError, match="rate limited"):
        list(RedditConnector(["python"], client=client).fetch())


def test_reddit_http_client_wraps_request_errors(monkeypatch) -> None:
    def failed_get(*args, **kwargs):
        raise requests.RequestException("network unavailable")

    monkeypatch.setattr("app.ingestion.reddit.requests.get", failed_get)

    with pytest.raises(RedditApiError, match="Reddit API request failed"):
        RedditHttpClient("unMeet/test").fetch_posts("python", "new", 10)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_reddit_http_client_uses_oauth_and_caches_the_token(monkeypatch) -> None:
    now = [100.0]
    token_requests: list[dict] = []
    listing_requests: list[dict] = []

    def fake_post(url, auth, data, headers, timeout):
        token_requests.append({"url": url, "auth": auth, "data": data})
        return _Response({"access_token": f"token-{len(token_requests)}", "expires_in": 3600})

    def fake_get(url, params, headers, timeout):
        listing_requests.append({"url": url, "headers": headers, "params": params})
        return _Response({"data": {"children": [{"data": _post("p1")}]}})

    monkeypatch.setattr("app.ingestion.reddit.requests.post", fake_post)
    monkeypatch.setattr("app.ingestion.reddit.requests.get", fake_get)
    client = RedditHttpClient("unMeet/test", "id", "secret", clock=lambda: now[0])

    client.fetch_posts("sales", "new", 25)
    client.fetch_posts("sales", "hot", 25)
    now[0] += 3600
    client.fetch_posts("sales", "new", 25)

    assert [request["auth"] for request in token_requests] == [("id", "secret")] * 2
    assert token_requests[0]["data"] == {"grant_type": "client_credentials"}
    assert listing_requests[0]["url"] == "https://oauth.reddit.com/r/sales/new"
    assert listing_requests[0]["headers"]["Authorization"] == "Bearer token-1"
    assert listing_requests[1]["headers"]["Authorization"] == "Bearer token-1"
    assert listing_requests[2]["headers"]["Authorization"] == "Bearer token-2"
    assert listing_requests[0]["params"]["raw_json"] == 1


def test_reddit_http_client_without_credentials_uses_public_json(monkeypatch) -> None:
    seen: list[str] = []

    def fake_get(url, params, headers, timeout):
        seen.append(url)
        assert "Authorization" not in headers
        return _Response({"data": {"children": []}})

    monkeypatch.setattr("app.ingestion.reddit.requests.get", fake_get)

    client = RedditHttpClient("unMeet/test")
    client.fetch_posts("sales", "new", 5)

    assert client.uses_oauth is False
    assert seen == ["https://www.reddit.com/r/sales/new.json"]


def test_reddit_oauth_errors_are_wrapped(monkeypatch) -> None:
    def failed_post(*args, **kwargs):
        raise requests.ConnectionError("dns")

    monkeypatch.setattr("app.ingestion.reddit.requests.post", failed_post)

    with pytest.raises(RedditApiError, match="OAuth token request failed"):
        RedditHttpClient("unMeet/test", "id", "secret").fetch_posts("sales", "new", 5)
