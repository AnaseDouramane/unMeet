"""Questions from the Stack Exchange network through the public API (v2.3).

Free and keyless (an optional ``key`` raises the daily quota). The connector polls
``/search/advanced`` newest first with ``fromdate`` as cursor, honours the ``backoff`` field the
API sends when it wants clients to slow down, and paginates with ``has_more``. Question ids are
prefixed with the site (``softwarerecs:123``) so sites never collide.

Terms to respect when charging customers: keep attribution to the original question URL (every
item carries its ``link``) and do not exceed the documented request rates. The response shape
follows the public documentation and is covered by fixtures, not by a live call from CI.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import requests

from app.ingestion.base import SourceConnector
from app.ingestion.cursors import CursorStore
from app.ingestion.schemas import SourceItem

logger = logging.getLogger(__name__)

API_URL = "https://api.stackexchange.com/2.3/search/advanced"
_PAGE_SIZE = 100
_MAX_BACKOFF_SLEEP_SECONDS = 60.0


class StackExchangeError(RuntimeError):
    pass


class _Session(Protocol):
    def get(self, url: str, params: dict[str, Any], timeout: float) -> Any: ...


class StackExchangeConnector(SourceConnector):
    source = "stackexchange"

    def __init__(
        self,
        site: str,
        queries: Sequence[str | None] = (None,),
        limit: int = 200,
        lookback_seconds: int = 86400,
        key: str | None = None,
        session: _Session | None = None,
        timeout_seconds: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
        clock_seconds: Callable[[], float] | None = None,
    ) -> None:
        if not isinstance(site, str) or not site.strip():
            raise ValueError("site must not be empty")
        if not queries:
            raise ValueError("at least one query (or None for all questions) is required")
        if any(query is not None and not query.strip() for query in queries):
            raise ValueError("queries must not be blank")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if lookback_seconds <= 0 or timeout_seconds <= 0:
            raise ValueError("lookback_seconds and timeout_seconds must be positive")
        self.site = site.strip().lower()
        self.queries = tuple(query.strip() if query else None for query in queries)
        self.limit = limit
        self.lookback_seconds = lookback_seconds
        self._key = key or None
        self._session: _Session = session or requests.Session()
        self._timeout = timeout_seconds
        self._sleep = sleep
        self._now = clock_seconds or (lambda: datetime.now(UTC).timestamp())
        self._cursors: dict[str, int] = {}
        self._pending: dict[str, int] = {}

    @property
    def name(self) -> str:
        return f"stackexchange:{self.site}"

    def _cursor_key(self, query: str | None) -> str:
        return f"stackexchange:{self.site}:{(query or '*').lower()}"

    def load_cursors(self, store: CursorStore) -> None:
        self._cursors, self._pending = {}, {}
        for query in self.queries:
            key = self._cursor_key(query)
            raw = store.get(key)
            try:
                if raw is not None:
                    self._cursors[key] = int(raw)
            except ValueError:
                logger.warning("Ignoring invalid cursor %r for %s", raw, key)

    def pending_cursors(self) -> Mapping[str, str]:
        return {key: str(value) for key, value in self._pending.items()}

    def fetch(self) -> Iterable[SourceItem]:
        remaining = self.limit
        for query in self.queries:
            if remaining <= 0:
                return
            for item in self._fetch_query(query, remaining):
                remaining -= 1
                yield item

    def _fetch_query(self, query: str | None, budget: int) -> Iterable[SourceItem]:
        key = self._cursor_key(query)
        cursor = self._cursors.get(key)
        since = cursor if cursor is not None else int(self._now()) - self.lookback_seconds
        newest = cursor
        yielded = 0
        page = 1
        truncated = False
        while True:
            items, has_more = self._request(query, since, page)
            for raw in items:
                item = self._to_source_item(raw)
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
            if truncated or not has_more or not items:
                break
        if truncated:
            logger.warning("%s: limit reached, cursor not advanced", key)
        elif newest is not None and newest != cursor:
            self._pending[key] = newest

    def _request(
        self, query: str | None, since: int, page: int
    ) -> tuple[list[dict[str, Any]], bool]:
        params: dict[str, Any] = {
            "site": self.site,
            "order": "desc",
            "sort": "creation",
            "fromdate": since + 1,  # inclusive bound: skip the question the cursor points at
            "pagesize": min(self.limit, _PAGE_SIZE),
            "page": page,
            "filter": "withbody",
        }
        if query:
            params["q"] = query
        if self._key:
            params["key"] = self._key
        try:
            response = self._session.get(API_URL, params=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
            items = payload["items"]
            has_more = bool(payload.get("has_more", False))
            backoff = payload.get("backoff")
        except requests.RequestException as error:
            raise StackExchangeError(f"Stack Exchange request failed: {error}") from error
        except (ValueError, KeyError, TypeError) as error:
            raise StackExchangeError("Stack Exchange returned an unexpected payload") from error
        if not isinstance(items, list):
            raise StackExchangeError("Stack Exchange items must be a list")
        if isinstance(backoff, (int, float)) and not isinstance(backoff, bool) and backoff > 0:
            # The API asks clients to wait before the next call; never ignore it.
            if backoff > _MAX_BACKOFF_SLEEP_SECONDS:
                raise StackExchangeError(f"Stack Exchange asked to back off for {backoff}s")
            self._sleep(float(backoff))
        return [item for item in items if isinstance(item, dict)], has_more

    def _to_source_item(self, raw: dict[str, Any]) -> SourceItem | None:
        question_id = raw.get("question_id")
        title = raw.get("title")
        created = raw.get("creation_date")
        link = raw.get("link")
        if (
            isinstance(question_id, bool)
            or not isinstance(question_id, int)
            or not isinstance(title, str)
            or not title.strip()
            or isinstance(created, bool)
            or not isinstance(created, int)
            or not isinstance(link, str)
            or not link
        ):
            return None
        body = raw.get("body")
        owner = raw.get("owner")
        author = owner.get("display_name") if isinstance(owner, dict) else None
        score = raw.get("score")
        return SourceItem(
            external_id=f"{self.site}:{question_id}",
            source="stackexchange",
            title=title,
            body=body if isinstance(body, str) else "",
            url=link,
            author=author if isinstance(author, str) and author else None,
            published_at=datetime.fromtimestamp(created, tz=UTC),
            engagement_score=score
            if isinstance(score, int) and not isinstance(score, bool)
            else None,
            raw_payload=raw,
        )
