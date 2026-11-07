from __future__ import annotations

from datetime import datetime

from app.signals.schemas import SignalQuery
from app.topics.schemas import Topic


def topic_signal_query(
    topic: Topic,
    limit: int = 50,
    offset: int = 0,
    processed_since: datetime | None = None,
) -> tuple[SignalQuery, str | None]:
    """Translate a tracked topic into a signal query plus its semantic description."""
    query = SignalQuery(
        intents=topic.intents,
        sources=topic.sources,
        products=topic.products,
        min_severity=topic.min_severity,
        processed_since=processed_since,
        max_distance=topic.max_distance,
        limit=limit,
        offset=offset,
    )
    return query, topic.description
