from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import requests

from app.config import Settings
from app.ingestion.base import SourceConnector
from app.ingestion.schemas import SourceItem

logger = logging.getLogger(__name__)


class RedditApiError(RuntimeError):
    pass


class RedditClient(Protocol):
    def fetch_posts(self, subreddit: str, sort: str, limit: int) -> list[dict[str, Any]]: ...


class RedditHttpClient:
    """Reddit listing client.

    With ``client_id`` and ``client_secret`` it uses Reddit's OAuth API (application-only
    ``client_credentials`` grant), which has documented rate limits and is required for
    commercial use. Without credentials it falls back to the public ``.json`` endpoints, which
    are heavily rate limited and only suitable for local experiments.
    """

    base_url = "https://www.reddit.com"
    oauth_url = "https://oauth.reddit.com"
    token_url = "https://www.reddit.com/api/v1/access_token"

    def __init__(
        self,
        user_agent: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(user_agent, str) or not user_agent.strip():
            raise ValueError("reddit_user_agent must not be empty")
        self._user_agent = user_agent.strip()
        self._client_id = client_id or None
        self._client_secret = client_secret or None
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        if not self.uses_oauth:
            logger.warning(
                "Reddit credentials are not configured; using the public JSON endpoints"
            )

    @property
    def uses_oauth(self) -> bool:
        return self._client_id is not None and self._client_secret is not None

    def fetch_posts(self, subreddit: str, sort: str, limit: int) -> list[dict[str, Any]]:
        headers = {"User-Agent": self._user_agent}
        if self.uses_oauth:
            url = f"{self.oauth_url}/r/{subreddit}/{sort}"
            headers["Authorization"] = f"Bearer {self._access_token()}"
        else:
            url = f"{self.base_url}/r/{subreddit}/{sort}.json"
        try:
            response = requests.get(
                url,
                params={"limit": limit, "raw_json": 1},
                headers=headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise RedditApiError(f"Reddit API request failed: {error}") from error
        except ValueError as error:
            raise RedditApiError("Reddit API returned invalid JSON") from error

        try:
            children = payload["data"]["children"]
        except (KeyError, TypeError) as error:
            raise RedditApiError("Reddit API returned an unexpected listing payload") from error
        if not isinstance(children, list):
            raise RedditApiError("Reddit API listing children must be a list")
        return [
            child["data"]
            for child in children
            if isinstance(child, dict) and isinstance(child.get("data"), dict)
        ]

    def _access_token(self) -> str:
        """Return a cached application token, refreshing it a minute before expiry."""
        if self._token is not None and self._clock() < self._token_expires_at:
            return self._token
        assert self._client_id is not None and self._client_secret is not None
        try:
            response = requests.post(
                self.token_url,
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            token = payload["access_token"]
            expires_in = float(payload.get("expires_in", 3600))
        except requests.RequestException as error:
            raise RedditApiError(f"Reddit OAuth token request failed: {error}") from error
        except (ValueError, KeyError, TypeError) as error:
            raise RedditApiError("Reddit OAuth returned an unexpected token payload") from error
        if not isinstance(token, str) or not token:
            raise RedditApiError("Reddit OAuth returned an empty token")
        self._token = token
        self._token_expires_at = self._clock() + max(expires_in - 60.0, 0.0)
        return token


class RedditConnector(SourceConnector):
    source = "reddit"
    _SUPPORTED_SORTS = frozenset({"new", "hot"})

    def __init__(
        self,
        subreddits: Sequence[str],
        limit: int = 100,
        sort: str = "new",
        client: RedditClient | None = None,
        user_agent: str = "unMeet/0.1",
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.subreddits = self._normalize_subreddits(subreddits)
        self.limit = self._normalize_limit(limit)
        self.sort = self._normalize_sort(sort)
        self._client = client or RedditHttpClient(
            user_agent=user_agent,
            client_id=client_id,
            client_secret=client_secret,
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, client: RedditClient | None = None
    ) -> RedditConnector:
        return cls(
            subreddits=settings.reddit_subreddits,
            limit=settings.reddit_limit,
            sort=settings.reddit_sort,
            client=client,
            user_agent=settings.reddit_user_agent,
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
        )

    def fetch(self) -> Iterable[SourceItem]:
        yielded = 0
        for subreddit in self.subreddits:
            if yielded >= self.limit:
                return
            posts = self._client.fetch_posts(subreddit, self.sort, self.limit - yielded)
            for post in posts:
                if yielded >= self.limit:
                    return
                source_item = self._to_source_item(post)
                if source_item is None:
                    continue
                yielded += 1
                yield source_item

    @staticmethod
    def _to_source_item(post: dict[str, Any]) -> SourceItem | None:
        if RedditConnector._is_removed_or_deleted(post):
            return None

        external_id = post.get("id")
        title = post.get("title")
        created_utc = post.get("created_utc")
        if not isinstance(external_id, str) or not external_id.strip():
            return None
        if not isinstance(title, str) or not title.strip():
            return None
        if isinstance(created_utc, bool) or not isinstance(created_utc, (int, float)):
            return None

        url = post.get("url")
        if not isinstance(url, str) or not url.strip():
            permalink = post.get("permalink")
            if not isinstance(permalink, str) or not permalink.startswith("/"):
                return None
            url = f"https://www.reddit.com{permalink}"

        author = post.get("author")
        score = post.get("score")
        return SourceItem(
            external_id=external_id,
            source="reddit",
            title=title,
            body=selftext if isinstance(selftext := post.get("selftext"), str) else "",
            url=url,
            author=author if isinstance(author, str) and author.strip() else None,
            published_at=datetime.fromtimestamp(created_utc, tz=UTC),
            engagement_score=(
                score if isinstance(score, int) and not isinstance(score, bool) else None
            ),
            raw_payload=post,
        )

    @staticmethod
    def _is_removed_or_deleted(post: dict[str, Any]) -> bool:
        return (
            post.get("author") == "[deleted]"
            or post.get("selftext") in {"[removed]", "[deleted]"}
            or post.get("removed_by_category") is not None
            or post.get("removed_by") is not None
        )

    @staticmethod
    def _normalize_subreddits(subreddits: Sequence[str]) -> tuple[str, ...]:
        if isinstance(subreddits, (str, bytes)):
            raise TypeError("subreddits must be a sequence of subreddit names")
        normalized = tuple(
            subreddit.strip().removeprefix("r/")
            for subreddit in subreddits
            if isinstance(subreddit, str) and subreddit.strip()
        )
        if not normalized:
            raise ValueError("at least one subreddit must be configured")
        return normalized

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if limit <= 0:
            raise ValueError("limit must be positive")
        return limit

    @classmethod
    def _normalize_sort(cls, sort: str) -> str:
        if not isinstance(sort, str) or sort not in cls._SUPPORTED_SORTS:
            raise ValueError("sort must be 'new' or 'hot'")
        return sort
