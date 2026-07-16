from datetime import datetime, timezone
from typing import Any, Iterable

import requests

from app.ingestion.base import SourceConnector
from app.ingestion.schemas import SourceItem


class HackerNewsConnector(SourceConnector):
    base_url = "https://hacker-news.firebaseio.com/v0"

    def __init__(
        self,
        story_list_endpoint: str = "askstories",
        limit: int | None = 100,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.story_list_endpoint = story_list_endpoint
        self.limit = limit
        self.timeout_seconds = timeout_seconds

    def fetch(self) -> Iterable[SourceItem]:
        story_ids = self._fetch_story_ids()
        if self.limit is not None:
            story_ids = story_ids[: self.limit]

        for story_id in story_ids:
            item = self._fetch_item(story_id)
            if item.get("type") != "story":
                continue
            source_item = self._to_source_item(item)
            if source_item is not None:
                yield source_item

    def _fetch_story_ids(self) -> list[int]:
        response = requests.get(
            f"{self.base_url}/{self.story_list_endpoint}.json",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [story_id for story_id in payload if isinstance(story_id, int)]

    def _fetch_item(self, story_id: int) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/item/{story_id}.json",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _to_source_item(self, item: dict[str, Any]) -> SourceItem | None:
        external_id = item.get("id")
        title = item.get("title")
        published_at = item.get("time")
        if external_id is None or title is None or published_at is None:
            return None

        return SourceItem(
            external_id=str(external_id),
            source="hackernews",
            title=title,
            body=item.get("text", ""),
            url=item.get("url") or f"https://news.ycombinator.com/item?id={external_id}",
            author=item.get("by"),
            published_at=datetime.fromtimestamp(published_at, tz=timezone.utc),
            engagement_score=item.get("score"),
            raw_payload=item,
        )
