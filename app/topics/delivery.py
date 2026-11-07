"""Deliver new signals for tracked topics to their webhooks (Clay, Zapier, Make, Slack relays).

Each run sends the signals processed since the topic's last successful delivery (or the last
``initial_lookback`` for a new topic) as JSON batches. The delivery watermark only moves after
every batch was accepted, and it is set to the run's start time so items processed while the
run was in progress are picked up next time.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests

from app.signals.schemas import MAX_SIGNAL_LIMIT, Signal
from app.signals.service import SignalReader
from app.topics.matching import topic_signal_query
from app.topics.schemas import Topic
from app.topics.store import TopicStore

logger = logging.getLogger(__name__)

Resolver = Callable[[str], Sequence[str]]


@dataclass(frozen=True)
class TopicDeliveryResult:
    topic_id: int
    topic_name: str
    delivered_count: int
    error: str | None = None


def _resolve(hostname: str) -> Sequence[str]:
    return [
        str(info[4][0]) for info in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    ]


class AlertDeliveryService:
    def __init__(
        self,
        topic_store: TopicStore,
        signal_reader: SignalReader,
        session: requests.Session | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        resolver: Resolver = _resolve,
        batch_size: int = 100,
        initial_lookback: timedelta = timedelta(days=7),
        timeout_seconds: float = 15.0,
    ) -> None:
        if not 1 <= batch_size <= MAX_SIGNAL_LIMIT:
            raise ValueError(f"batch_size must be between 1 and {MAX_SIGNAL_LIMIT}")
        self._topics = topic_store
        self._signals = signal_reader
        self._session = session or requests.Session()
        self._clock = clock
        self._resolver = resolver
        self.batch_size = batch_size
        self.initial_lookback = initial_lookback
        self.timeout_seconds = timeout_seconds

    def deliver_all(self) -> tuple[TopicDeliveryResult, ...]:
        return tuple(
            self.deliver(topic) for topic in self._topics.list() if topic.webhook_url is not None
        )

    def deliver(self, topic: Topic) -> TopicDeliveryResult:
        started_at = self._clock()
        since = topic.last_delivered_at or (started_at - self.initial_lookback)
        try:
            self._ensure_public_destination(topic)
            delivered = 0
            offset = 0
            while True:
                query, description = topic_signal_query(
                    topic, limit=self.batch_size, offset=offset, processed_since=since
                )
                batch = tuple(self._signals.find(query, description))
                if not batch:
                    break
                self._post(topic, batch)
                delivered += len(batch)
                if len(batch) < self.batch_size:
                    break
                offset += self.batch_size
            self._topics.mark_delivered(topic.id, started_at)
            return TopicDeliveryResult(topic.id, topic.name, delivered)
        except (requests.RequestException, WebhookRejectedError, UnsafeWebhookError) as error:
            logger.warning("Delivery failed for topic %s: %s", topic.id, error)
            return TopicDeliveryResult(topic.id, topic.name, 0, str(error))

    def _ensure_public_destination(self, topic: Topic) -> None:
        """Re-check the resolved addresses at send time (defends against DNS rebinding)."""
        assert topic.webhook_url is not None
        hostname = urlparse(topic.webhook_url).hostname or ""
        try:
            addresses = self._resolver(hostname)
        except OSError as error:
            raise UnsafeWebhookError(f"cannot resolve {hostname}: {error}") from error
        if not addresses:
            raise UnsafeWebhookError(f"{hostname} does not resolve")
        for address in addresses:
            if not ipaddress.ip_address(address.split("%")[0]).is_global:
                raise UnsafeWebhookError(f"{hostname} resolves to a non-public address")

    def _post(self, topic: Topic, batch: Sequence[Signal]) -> None:
        assert topic.webhook_url is not None
        response = self._session.post(
            topic.webhook_url,
            json=webhook_payload(topic, batch),
            timeout=self.timeout_seconds,
            allow_redirects=False,
        )
        if not 200 <= response.status_code < 300:
            raise WebhookRejectedError(f"webhook returned HTTP {response.status_code}")


class WebhookRejectedError(RuntimeError):
    pass


class UnsafeWebhookError(RuntimeError):
    pass


def webhook_payload(topic: Topic, signals: Sequence[Signal]) -> dict[str, Any]:
    return {
        "topic": {"id": topic.id, "name": topic.name},
        "count": len(signals),
        "signals": [
            {
                "id": signal.id,
                "source": signal.source,
                "url": signal.url,
                "title": signal.title,
                "author": signal.author,
                "published_at": signal.published_at.isoformat(),
                "intent": signal.intent,
                "pain_quote": signal.pain_quote,
                "products_mentioned": list(signal.products_mentioned),
                "severity": signal.severity,
                "confidence": signal.confidence,
                "similarity": signal.similarity,
            }
            for signal in signals
        ],
    }
