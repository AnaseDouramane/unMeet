"""Recent Hacker News posts and comments through the public Algolia search API.

``search_by_date`` returns newest first and accepts ``created_at_i>cursor``, which makes it a
good fit for polling every few minutes: each search asks only for what is new, optionally
narrowed by keywords (``query``) so a topic-first deployment reads the relevant slice of the
site instead of crawling feeds. Items use the same ``source`` and ``external_id`` as
:class:`HackerNewsConnector`, so both connectors can run without creating duplicates.

The API is free and needs no key. Its response shape here follows the public documentation and
is covered by fixtures; it has not been exercised against the live service from CI.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import requests

from app.ingestion.base import SourceConnector
from app.ingestion.cursors import CursorStore
from app.ingestion.schemas import SourceItem

logger = logging.getLogger(__name__)

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
_SUPPORTED_TAGS = frozenset({"comment", "story", "ask_hn", "show_hn"})
_MAX_HITS_PER_PAGE = 100
_EXACT_SEARCH = {
    "advancedSyntax": "true",
    "typoTolerance": "false",
    "queryType": "prefixNone",
    "removeWordsIfNoResults": "none",
}


class HackerNewsSearchError(RuntimeError):
    pass


class _Session(Protocol):
    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> Any: ...


@dataclass(frozen=True)
class SearchSpec:
    """One search: a tag (what kind of item) and an optional keyword query.

    Queries match exact words; wrap several words in double quotes to require the phrase
    (``"looking for a tool"``).
    """

    tag: str = "comment"
    query: str | None = None

    def __post_init__(self) -> None:
        if self.tag not in _SUPPORTED_TAGS:
            raise ValueError(f"tag must be one of {sorted(_SUPPORTED_TAGS)}")
        if self.query is not None and not self.query.strip():
            raise ValueError("query must not be blank")

    @property
    def cursor_key(self) -> str:
        return f"hackernews_search:{self.tag}:{(self.query or '*').strip().lower()}"


class HackerNewsSearchConnector(SourceConnector):
    source = "hackernews"
    name = "hackernews_search"

    def __init__(
        self,
        searches: Sequence[SearchSpec],
        limit: int = 300,
        lookback_seconds: int = 3600,
        session: _Session | None = None,
        timeout_seconds: float = 15.0,
        clock_seconds: Callable[[], float] | None = None,
    ) -> None:
        if not searches:
            raise ValueError("at least one search is required")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if lookback_seconds <= 0 or timeout_seconds <= 0:
            raise ValueError("lookback_seconds and timeout_seconds must be positive")
        self.searches = tuple(searches)
        self.limit = limit
        self.lookback_seconds = lookback_seconds
        self._session: _Session = session or requests.Session()
        self._timeout = timeout_seconds
        self._now = clock_seconds or (lambda: datetime.now(UTC).timestamp())
        self._cursors: dict[str, int] = {}
        self._pending: dict[str, int] = {}

    def load_cursors(self, store: CursorStore) -> None:
        self._cursors, self._pending = {}, {}
        for spec in self.searches:
            raw = store.get(spec.cursor_key)
            try:
                if raw is not None:
                    self._cursors[spec.cursor_key] = int(raw)
            except ValueError:
                logger.warning("Ignoring invalid cursor %r for %s", raw, spec.cursor_key)

    def pending_cursors(self) -> Mapping[str, str]:
        return {key: str(value) for key, value in self._pending.items()}

    def fetch(self) -> Iterable[SourceItem]:
        """Run every search with its own share of the budget.

        A busy search must not starve the others: each one gets an equal share of what is left,
        and whatever a quiet search does not use rolls over to the searches after it.
        """
        remaining = self.limit
        for index, spec in enumerate(self.searches):
            if remaining <= 0:
                return
            searches_left = len(self.searches) - index
            share = max(1, -(-remaining // searches_left))  # ceiling division
            used = 0
            for item in self._fetch_search(spec, share):
                used += 1
                yield item
            remaining -= used

    def _fetch_search(self, spec: SearchSpec, budget: int) -> Iterable[SourceItem]:
        key = spec.cursor_key
        cursor = self._cursors.get(key)
        # First run: look back a bounded window instead of the whole history.
        since = cursor if cursor is not None else int(self._now()) - self.lookback_seconds
        newest = cursor
        yielded = 0
        page = 0
        truncated = False
        while True:
            hits, pages = self._request(spec, since, page)
            for hit in hits:
                item = self._to_source_item(hit)
                if item is None:
                    continue
                if yielded >= budget:
                    truncated = True
                    break
                created = int(item.published_at.timestamp())
                if newest is None or created > newest:
                    newest = created
                yielded += 1
                yield item
            page += 1
            if truncated or page >= pages or not hits:
                break
        if truncated:
            # Newest first: moving the cursor would skip the older hits we did not read.
            logger.warning("%s: limit reached, cursor not advanced", key)
        elif newest is not None and newest != cursor:
            self._pending[key] = newest

    def _request(self, spec: SearchSpec, since: int, page: int) -> tuple[list[dict[str, Any]], int]:
        params: dict[str, Any] = {
            "tags": spec.tag,
            "numericFilters": f"created_at_i>{since}",
            "hitsPerPage": min(self.limit, _MAX_HITS_PER_PAGE),
            "page": page,
        }
        if spec.query:
            params["query"] = spec.query
            # Algolia's default is fuzzy (typos, prefixes, dropped words) and returns mostly
            # unrelated comments. Exact terms and "quoted phrases" are what this source needs.
            params.update(_EXACT_SEARCH)
        try:
            response = self._session.get(ALGOLIA_URL, params=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
            hits = payload["hits"]
            pages = int(payload.get("nbPages", 1))
        except requests.RequestException as error:
            raise HackerNewsSearchError(f"Algolia request failed: {error}") from error
        except (ValueError, KeyError, TypeError) as error:
            raise HackerNewsSearchError("Algolia returned an unexpected payload") from error
        if not isinstance(hits, list):
            raise HackerNewsSearchError("Algolia hits must be a list")
        return [hit for hit in hits if isinstance(hit, dict)], pages

    @staticmethod
    def _to_source_item(hit: dict[str, Any]) -> SourceItem | None:
        object_id = hit.get("objectID")
        created = hit.get("created_at_i")
        if (
            not isinstance(object_id, str)
            or not object_id.isdigit()
            or isinstance(created, bool)
            or not isinstance(created, int)
        ):
            return None
        tags = hit.get("_tags") or []
        link = f"https://news.ycombinator.com/item?id={object_id}"
        if "comment" in tags:
            text = hit.get("comment_text")
            if not isinstance(text, str) or not text.strip():
                return None
            story_title = hit.get("story_title")
            title = (
                f"Re: {story_title}"
                if isinstance(story_title, str) and story_title
                else ("Hacker News comment")
            )
            body, url, score = text, link, None
        else:
            raw_title = hit.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                return None
            title = raw_title
            text = hit.get("story_text")
            body = text if isinstance(text, str) else ""
            external = hit.get("url")
            url = external if isinstance(external, str) and external else link
            points = hit.get("points")
            score = points if isinstance(points, int) and not isinstance(points, bool) else None
        author = hit.get("author")
        return SourceItem(
            external_id=object_id,
            source="hackernews",
            title=title,
            body=body,
            url=url,
            author=author if isinstance(author, str) and author else None,
            published_at=datetime.fromtimestamp(created, tz=UTC),
            engagement_score=score,
            raw_payload=hit,
        )
