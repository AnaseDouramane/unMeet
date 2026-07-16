from datetime import datetime, timezone

import pytest

from app.ingestion.hackernews import HackerNewsConnector


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def test_hackernews_connector_returns_raw_source_item(monkeypatch: pytest.MonkeyPatch) -> None:
    requests_seen: list[str] = []

    def fake_get(url: str, timeout: float) -> FakeResponse:
        requests_seen.append(url)
        if url.endswith("/askstories.json"):
            return FakeResponse([123, 456])
        if url.endswith("/item/123.json"):
            return FakeResponse(
                {
                    "id": 123,
                    "type": "story",
                    "by": "alice",
                    "time": 1_700_000_000,
                    "title": "Hello <b>HN</b>",
                    "text": "<p>Body <i>content</i></p>",
                    "url": "https://example.com/article",
                    "score": 42,
                }
            )
        if url.endswith("/item/456.json"):
            return FakeResponse(
                {
                    "id": 456,
                    "type": "job",
                    "by": "bob",
                    "time": 1_700_000_100,
                    "title": "Job posting",
                    "text": "Ignored",
                    "score": 1,
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("app.ingestion.hackernews.requests.get", fake_get)

    connector = HackerNewsConnector(limit=10)
    items = list(connector.fetch())

    assert requests_seen == [
        "https://hacker-news.firebaseio.com/v0/askstories.json",
        "https://hacker-news.firebaseio.com/v0/item/123.json",
        "https://hacker-news.firebaseio.com/v0/item/456.json",
    ]
    assert len(items) == 1

    item = items[0]
    assert item.external_id == "123"
    assert item.source == "hackernews"
    assert item.title == "Hello <b>HN</b>"
    assert item.body == "<p>Body <i>content</i></p>"
    assert item.url == "https://example.com/article"
    assert item.author == "alice"
    assert item.published_at == datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
    assert item.engagement_score == 42
    assert item.raw_payload["id"] == 123
    assert item.raw_payload["type"] == "story"
