from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
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
        max_workers: int = 1,
        include_comments: bool = False,
        max_comments_per_story: int = 20,
    ) -> None:
        self.feeds = self.normalize_feeds(feeds)
        self.limit = self._validate_limit(limit)
        self.timeout_seconds = self._validate_timeout(timeout_seconds)
        self.max_workers = self._validate_positive(max_workers, "max_workers")
        self.include_comments = bool(include_comments)
        self.max_comments_per_story = self._validate_positive(
            max_comments_per_story, "max_comments_per_story"
        )

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
        """Yield stories (and optionally their top-level comments) in feed order.

        Item requests run in ordered batches of ``max_workers`` so output stays deterministic
        while network latency overlaps. ``limit`` caps stories; comments are capped per story,
        because pain points are mostly expressed in replies rather than in headlines.
        """
        produced_count = 0
        seen_story_ids: set[int] = set()

        for feed in self.feeds:
            if produced_count >= self.limit:
                return
            pending: list[int] = []
            for story_id in self._fetch_feed_ids(feed):
                if story_id not in seen_story_ids:
                    seen_story_ids.add(story_id)
                    pending.append(story_id)
            while pending and produced_count < self.limit:
                batch_size = min(self.max_workers, self.limit - produced_count)
                batch, pending = pending[:batch_size], pending[batch_size:]
                for item in self._fetch_items(batch):
                    if item.get("type") != "story" or item.get("deleted") is True:
                        continue
                    source_item = self._to_source_item(item)
                    if source_item is None:
                        continue
                    yield source_item
                    if self.include_comments:
                        yield from self._comments_for(item)
                    produced_count += 1
                    if produced_count >= self.limit:
                        return

    def _fetch_items(self, item_ids: Sequence[int]) -> list[dict[str, Any]]:
        """Fetch items preserving input order; failed requests are dropped."""
        if self.max_workers == 1 or len(item_ids) <= 1:
            return [item for item in map(self._fetch_item_or_empty, item_ids) if item]
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(item_ids))) as executor:
            return [item for item in executor.map(self._fetch_item_or_empty, item_ids) if item]

    def _fetch_item_or_empty(self, item_id: int) -> dict[str, Any]:
        try:
            return self._fetch_item(item_id)
        except requests.RequestException:
            return {}

    def _comments_for(self, story: dict[str, Any]) -> Iterator[SourceItem]:
        kids = story.get("kids")
        if not isinstance(kids, list):
            return
        comment_ids = [
            kid for kid in kids if isinstance(kid, int) and not isinstance(kid, bool)
        ][: self.max_comments_per_story]
        for comment in self._fetch_items(comment_ids):
            source_item = self._comment_to_source_item(comment, story)
            if source_item is not None:
                yield source_item

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
    def _validate_positive(value: int, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Hacker News {name} must be a positive integer")
        return value

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
            published_at=datetime.fromtimestamp(published_at, tz=UTC),
            engagement_score=item.get("score"),
            raw_payload=item,
        )

    @staticmethod
    def _comment_to_source_item(
        comment: dict[str, Any], story: dict[str, Any]
    ) -> SourceItem | None:
        comment_id = comment.get("id")
        text = comment.get("text")
        published_at = comment.get("time")
        if (
            comment.get("type") != "comment"
            or comment.get("deleted") is True
            or comment.get("dead") is True
            or isinstance(comment_id, bool)
            or not isinstance(comment_id, int)
            or not isinstance(text, str)
            or not text.strip()
            or isinstance(published_at, bool)
            or not isinstance(published_at, int)
        ):
            return None
        story_title = story.get("title") if isinstance(story.get("title"), str) else ""
        return SourceItem(
            external_id=str(comment_id),
            source="hackernews",
            title=f"Re: {story_title}" if story_title else "Hacker News comment",
            body=text,
            url=f"https://news.ycombinator.com/item?id={comment_id}",
            author=comment.get("by"),
            published_at=datetime.fromtimestamp(published_at, tz=UTC),
            engagement_score=None,
            raw_payload=comment,
        )
