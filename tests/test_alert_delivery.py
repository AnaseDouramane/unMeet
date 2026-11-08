from datetime import UTC, datetime, timedelta

import requests

from app.signals.schemas import Signal, SignalQuery
from app.topics.delivery import AlertDeliveryService
from app.topics.schemas import TopicDefinition
from app.topics.store import InMemoryTopicStore

NOW = datetime(2026, 11, 7, 18, 0, tzinfo=UTC)


def _signal(signal_id: int) -> Signal:
    return Signal(
        id=signal_id,
        source="hackernews",
        external_id=str(signal_id),
        title=f"Signal {signal_id}",
        url=f"https://news.ycombinator.com/item?id={signal_id}",
        author="erin",
        published_at=NOW - timedelta(hours=1),
        intent="solution_search",
        pain_quote=f"looking for a tool {signal_id}",
        products_mentioned=("Clay",),
        severity=2,
        confidence=0.9,
        similarity=0.77,
    )


class PagedReader:
    def __init__(self, total: int) -> None:
        self.signals = [_signal(i) for i in range(1, total + 1)]
        self.calls: list[tuple[SignalQuery, str | None]] = []

    def find(self, query: SignalQuery, topic: str | None = None):
        self.calls.append((query, topic))
        return self.signals[query.offset : query.offset + query.limit]


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeSession:
    def __init__(self, statuses: list[int | Exception]) -> None:
        self.statuses = statuses
        self.posts: list[dict] = []

    def post(self, url, json, timeout, allow_redirects):
        assert allow_redirects is False
        self.posts.append({"url": url, "json": json})
        status = self.statuses.pop(0) if self.statuses else 200
        if isinstance(status, Exception):
            raise status
        return FakeResponse(status)


def _service(store, reader, session, resolver=lambda host: ["93.184.216.34"], **kwargs):
    return AlertDeliveryService(
        store, reader, session=session, clock=lambda: NOW, resolver=resolver, **kwargs
    )


def _store_with_topic(**overrides) -> InMemoryTopicStore:
    store = InMemoryTopicStore()
    values = {
        "name": "Outbound tooling",
        "description": "people shopping for outbound tools",
        "intents": ("solution_search",),
        "webhook_url": "https://hooks.example.com/clay",
    }
    values.update(overrides)
    store.create(TopicDefinition(**values), workspace_id=1)
    return store


def test_delivers_in_batches_and_moves_the_watermark_to_run_start() -> None:
    store = _store_with_topic()
    reader = PagedReader(total=5)
    session = FakeSession([])

    results = _service(store, reader, session, batch_size=2).deliver_all()

    assert results[0].delivered_count == 5 and results[0].error is None
    assert [post["json"]["count"] for post in session.posts] == [2, 2, 1]
    first = session.posts[0]["json"]
    assert first["topic"] == {"id": 1, "name": "Outbound tooling"}
    assert first["signals"][0]["pain_quote"] == "looking for a tool 1"
    assert first["signals"][0]["relevance_reason"] is None
    assert reader.calls[0][0].topic_id == 1
    query, description = reader.calls[0]
    assert description == "people shopping for outbound tools"
    assert query.processed_since == NOW - timedelta(days=7)
    assert store.get(1).last_delivered_at == NOW  # type: ignore[union-attr]


def test_next_run_only_asks_for_items_processed_after_the_last_delivery() -> None:
    store = _store_with_topic()
    store.mark_delivered(1, NOW - timedelta(hours=3))
    reader = PagedReader(total=0)

    _service(store, reader, FakeSession([])).deliver_all()

    assert reader.calls[0][0].processed_since == NOW - timedelta(hours=3)


def test_rejected_webhooks_keep_the_watermark() -> None:
    store = _store_with_topic()
    session = FakeSession([500])

    result = _service(store, PagedReader(total=3), session).deliver_all()[0]

    assert result.error == "webhook returned HTTP 500"
    assert store.get(1).last_delivered_at is None  # type: ignore[union-attr]


def test_network_errors_are_reported_per_topic() -> None:
    store = _store_with_topic()
    session = FakeSession([requests.ConnectionError("refused")])

    result = _service(store, PagedReader(total=1), session).deliver_all()[0]

    assert result.error is not None and "refused" in result.error


def test_hosts_resolving_to_private_addresses_are_never_called() -> None:
    store = _store_with_topic()
    session = FakeSession([])

    result = _service(
        store, PagedReader(total=1), session, resolver=lambda host: ["169.254.169.254"]
    ).deliver_all()[0]

    assert result.error is not None and "non-public" in result.error
    assert session.posts == []


def test_topics_without_webhooks_are_skipped() -> None:
    store = _store_with_topic(webhook_url=None)
    reader = PagedReader(total=1)

    assert _service(store, reader, FakeSession([])).deliver_all() == ()
    assert reader.calls == []
