"""Hacker News searches built from the tracked topics.

Every active topic contributes its keywords and the products it names as exact phrases, so
what the product watches follows what customers asked to track (and what onboarding proposed),
with nothing to configure by hand. New or edited topics are picked up on the next poll.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.ingestion.hackernews_search import HackerNewsSearchConnector, SearchSpec
from app.topics.schemas import Topic

MAX_PHRASES = 40


def phrases_for(topics: Sequence[Topic]) -> tuple[str, ...]:
    """Distinct exact phrases, capped: keywords, then "<product> alternative" and
    "alternative to <product>", then the bare product names.

    The alternative phrases are how people ask for a replacement, and they are found far more
    often than descriptive phrases: on Hacker News over a year, "google analytics alternative"
    returned 10 posts and "alternative to google analytics" 8, while a phrase like "google
    analytics too complicated" returned none.
    """
    seen: dict[str, str] = {}

    def add(phrase: str) -> None:
        phrase = phrase.strip()
        if phrase:
            seen.setdefault(phrase.lower(), phrase)

    for topic in topics:
        for phrase in topic.keywords:
            add(phrase)
    products = [p.strip() for topic in topics for p in topic.products if p.strip()]
    for product in products:
        add(f"{product} alternative")
        add(f"alternative to {product}")
    for product in products:
        add(product)
    return tuple(seen.values())[:MAX_PHRASES]


def searches_for(topics: Sequence[Topic]) -> tuple[SearchSpec, ...]:
    return tuple(SearchSpec("any", f'"{phrase}"') for phrase in phrases_for(topics) if phrase)


class TopicSearchConnector(HackerNewsSearchConnector):
    """Searches Hacker News for the phrases of the active topics."""

    name = "hackernews_topics"

    def __init__(self, topics: Callable[[], Sequence[Topic]], **kwargs) -> None:
        super().__init__(lambda: searches_for(topics()), **kwargs)

    def fetch(self):
        if not self.searches:
            return iter(())  # no topic has phrases yet: nothing to look for
        return super().fetch()
