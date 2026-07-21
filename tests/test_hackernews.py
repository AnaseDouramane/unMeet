from datetime import datetime, timezone

import pytest
import requests

from app.ingestion.hackernews import HackerNewsConnector


class FakeResponse:
    def __init__(self, payload: object, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> object:
        return self.payload


def _story(story_id: int, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": story_id,
        "type": "story",
        "by": "alice",
        "time": 1_700_000_000 + story_id,
        "title": f"Story {story_id}",
        "text": f"Body {story_id}",
        "url": f"https://example.test/{story_id}",
        "score": story_id,
    }
    item.update(overrides)
    return item


def _install_fake_hackernews(
    monkeypatch: pytest.MonkeyPatch,
    feed_ids: dict[str, list[int]],
    items: dict[int, dict[str, object]],
    failing_item_ids: set[int] | None = None,
) -> list[str]:
    requests_seen: list[str] = []
    failing_item_ids = failing_item_ids or set()

    def fake_get(url: str, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        requests_seen.append(url)
        for feed, ids in feed_ids.items():
            if url.endswith(f"/{feed}.json"):
                return FakeResponse(ids)
        for story_id, item in items.items():
            if url.endswith(f"/item/{story_id}.json"):
                error = (
                    requests.HTTPError("item unavailable") if story_id in failing_item_ids else None
                )
                return FakeResponse(item, error)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("app.ingestion.hackernews.requests.get", fake_get)
    return requests_seen


def test_hackernews_connector_returns_raw_source_item_with_utc_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests_seen = _install_fake_hackernews(
        monkeypatch,
        {"askstories": [123]},
        {123: _story(123, title="Hello <b>HN</b>", text="<p>Body <i>content</i></p>")},
    )

    items = list(HackerNewsConnector(feeds=("askstories",), limit=1).fetch())

    assert requests_seen == [
        "https://hacker-news.firebaseio.com/v0/askstories.json",
        "https://hacker-news.firebaseio.com/v0/item/123.json",
    ]
    assert len(items) == 1
    item = items[0]
    assert item.external_id == "123"
    assert item.source == "hackernews"
    assert item.title == "Hello <b>HN</b>"
    assert item.body == "<p>Body <i>content</i></p>"
    assert item.published_at == datetime.fromtimestamp(1_700_000_123, tz=timezone.utc)
    assert item.raw_payload["id"] == 123


def test_limit_is_global_and_stops_after_500_valid_unique_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    top_ids = list(range(1, 601))
    requests_seen = _install_fake_hackernews(
        monkeypatch,
        {"topstories": top_ids, "newstories": [601], "beststories": [602]},
        {story_id: _story(story_id) for story_id in range(1, 603)},
    )

    items = list(HackerNewsConnector(limit=500).fetch())

    assert [item.external_id for item in items] == [str(story_id) for story_id in range(1, 501)]
    assert requests_seen[0].endswith("/topstories.json")
    assert not any(url.endswith("/newstories.json") for url in requests_seen)
    assert not any(url.endswith("/beststories.json") for url in requests_seen)
    assert len(requests_seen) == 501


def test_feeds_are_processed_in_order_and_deduplicated_before_item_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests_seen = _install_fake_hackernews(
        monkeypatch,
        {
            "topstories": [1, 2],
            "newstories": [2, 3],
            "beststories": [3, 4],
        },
        {story_id: _story(story_id) for story_id in range(1, 5)},
    )

    items = list(
        HackerNewsConnector(
            feeds=(" TOPSTORIES ", "newstories", "beststories"),
            limit=4,
        ).fetch()
    )

    assert [item.external_id for item in items] == ["1", "2", "3", "4"]
    assert requests_seen == [
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        "https://hacker-news.firebaseio.com/v0/item/1.json",
        "https://hacker-news.firebaseio.com/v0/item/2.json",
        "https://hacker-news.firebaseio.com/v0/newstories.json",
        "https://hacker-news.firebaseio.com/v0/item/3.json",
        "https://hacker-news.firebaseio.com/v0/beststories.json",
        "https://hacker-news.firebaseio.com/v0/item/4.json",
    ]


@pytest.mark.parametrize(
    ("feeds", "message"),
    [
        (("topstories", "TOPSTORIES"), "Duplicate Hacker News feed: topstories"),
        (("unknown",), "Unknown Hacker News feed: unknown"),
    ],
)
def test_invalid_feeds_are_rejected(feeds: tuple[str, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        HackerNewsConnector(feeds=feeds)


@pytest.mark.parametrize("limit", [0, -1])
def test_non_positive_limit_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        HackerNewsConnector(limit=limit)


def test_invalid_deleted_and_failed_items_do_not_count_towards_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests_seen = _install_fake_hackernews(
        monkeypatch,
        {"topstories": [1, 2, 3, 4, 5, 6]},
        {
            1: _story(1, type="job"),
            2: _story(2, deleted=True),
            3: _story(3, title=None),
            4: _story(4),
            5: _story(5),
            6: _story(6),
        },
        failing_item_ids={4},
    )

    items = list(HackerNewsConnector(feeds=("topstories",), limit=2).fetch())

    assert [item.external_id for item in items] == ["5", "6"]
    assert [url for url in requests_seen if "/item/" in url] == [
        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json" for story_id in range(1, 7)
    ]


def test_returns_all_valid_posts_when_fewer_than_limit_are_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_hackernews(
        monkeypatch,
        {"topstories": [10, 11], "newstories": [], "beststories": []},
        {10: _story(10), 11: _story(11)},
    )

    items = list(HackerNewsConnector(limit=500).fetch())

    assert [item.external_id for item in items] == ["10", "11"]
