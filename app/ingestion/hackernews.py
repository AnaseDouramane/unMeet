from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

import requests

from app.ingestion.base import SourceConnector
from app.ingestion.schemas import SourceItem


class HackerNewsConnector(SourceConnector):
    source = "hackernews"
    base_url = "https://hacker-news.firebaseio.com/v0"
    supported_feeds = frozenset({"topstories", "newstories", "beststories", "askstories"})
    default_feeds = ("topstories", "newstories", "beststories")

    def __init__(
        self,
        feeds: Sequence[str] = default_feeds,
        limit: int = 500,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.feeds = self.normalize_feeds(feeds)
        self.limit = self._validate_limit(limit)
        self.timeout_seconds = self._validate_timeout(timeout_seconds)

    @classmethod
    def normalize_feeds(cls, feeds: Sequence[str]) -> tuple[str, ...]:
        if isinstance(feeds, (str, bytes)):
            raise TypeError("Hacker News feeds must be a sequence of feed names")

        normalized_feeds: list[str] = []
        seen_feeds: set[str] = set()
        for feed in feeds:
            if not isinstance(feed, str) or not feed.strip():
                raise ValueError("Hacker News feed names must be non-empty strings")
            normalized_feed = feed.strip().lower()
            if normalized_feed not in cls.supported_feeds:
                raise ValueError(f"Unknown Hacker News feed: {normalized_feed}")
            if normalized_feed in seen_feeds:
                raise ValueError(f"Duplicate Hacker News feed: {normalized_feed}")
            seen_feeds.add(normalized_feed)
            normalized_feeds.append(normalized_feed)
        if not normalized_feeds:
            raise ValueError("At least one Hacker News feed must be configured")
        return tuple(normalized_feeds)

    def fetch(self) -> Iterable[SourceItem]:
        produced_count = 0
        seen_story_ids: set[int] = set()

        for feed in self.feeds:
            if produced_count >= self.limit:
                return
            for story_id in self._fetch_feed_ids(feed):
                if story_id in seen_story_ids:
                    continue
                seen_story_ids.add(story_id)
                try:
                    item = self._fetch_item(story_id)
                except requests.RequestException:
                    continue
                if item.get("type") != "story" or item.get("deleted") is True:
                    continue
                source_item = self._to_source_item(item)
                if source_item is None:
                    continue
                yield source_item
                produced_count += 1
                if produced_count >= self.limit:
                    return

    def _fetch_feed_ids(self, feed: str) -> list[int]:
        response = requests.get(
            f"{self.base_url}/{feed}.json",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [
            story_id
            for story_id in payload
            if isinstance(story_id, int) and not isinstance(story_id, bool)
        ]

    def _fetch_item(self, story_id: int) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/item/{story_id}.json",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("Hacker News limit must be a positive integer")
        return limit

    @staticmethod
    def _validate_timeout(timeout_seconds: float) -> float:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise ValueError("Hacker News timeout must be positive")
        return float(timeout_seconds)

    def _to_source_item(self, item: dict[str, Any]) -> SourceItem | None:
        external_id = item.get("id")
        title = item.get("title")
        published_at = item.get("time")
        if (
            isinstance(external_id, bool)
            or not isinstance(external_id, int)
            or not isinstance(title, str)
            or not title
            or isinstance(published_at, bool)
            or not isinstance(published_at, int)
        ):
            return None

        body = item.get("text", "")
        if not isinstance(body, str):
            return None
        return SourceItem(
            external_id=str(external_id),
            source="hackernews",
            title=title,
            body=body,
            url=item.get("url") or f"https://news.ycombinator.com/item?id={external_id}",
            author=item.get("by"),
            published_at=datetime.fromtimestamp(published_at, tz=timezone.utc),
            engagement_score=item.get("score"),
            raw_payload=item,
        )
