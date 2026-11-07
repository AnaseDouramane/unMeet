from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.problem_detection.schemas import TopicContext
from app.topics.schemas import Topic

logger = logging.getLogger(__name__)

GATE_CLASSIFIER_NAME = "topic_gate"


class _Embedder(Protocol):
    def encode(self, document_text: str) -> list[float]: ...

    def encode_batch(self, document_texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class GateDecision:
    """Outcome of the cheap pre-LLM filter for one document."""

    passed: bool
    embedding: list[float]
    matched_topic_ids: tuple[int, ...]
    reason: str


class TopicGate:
    """Decide whether a document is worth an LLM call.

    The document is embedded first (cheap) and compared with every active topic: it passes when
    it is closer than the topic's ``max_distance`` to the topic description, or when it names
    one of the topic's products. Topics that cannot be checked semantically (intent-only) let
    every document through, and so does an empty topic list, so the gate never silently drops
    data when it has nothing to compare against.
    """

    def __init__(
        self,
        topics: Callable[[], Sequence[Topic]],
        embedding_service: _Embedder,
    ) -> None:
        self._topics_provider = topics
        self._embedding_service = embedding_service
        self._topics: tuple[Topic, ...] = ()
        self._known: dict[int, str | None] = {}
        self._topic_vectors: dict[int, list[float]] = {}
        self._product_patterns: dict[int, tuple[re.Pattern[str], ...]] = {}

    @property
    def model_name(self) -> str:
        return str(getattr(self._embedding_service, "model_name", ""))

    def begin_run(self) -> None:
        """Reload the active topics and embed the new or edited descriptions."""
        topics = tuple(self._topics_provider())
        vectors: dict[int, list[float]] = {}
        stale = [
            topic
            for topic in topics
            if topic.description
            and not (
                topic.id in self._topic_vectors
                and self._known.get(topic.id) == topic.description
            )
        ]
        if stale:
            encoded = self._embedding_service.encode_batch(
                [topic.description for topic in stale if topic.description]
            )
            for topic, vector in zip(stale, encoded, strict=True):
                vectors[topic.id] = vector
        for topic in topics:
            if topic.description and topic.id not in vectors:
                vectors[topic.id] = self._topic_vectors[topic.id]
        self._known = {topic.id: topic.description for topic in topics}
        self._topics = topics
        self._topic_vectors = vectors
        self._product_patterns = {
            topic.id: tuple(
                re.compile(rf"(?<!\w){re.escape(product.strip())}(?!\w)", re.IGNORECASE)
                for product in topic.products
                if product.strip()
            )
            for topic in topics
        }
        logger.info("Topic gate loaded %d active topics", len(topics))

    def topic_contexts(self, topic_ids: Sequence[int]) -> tuple[TopicContext, ...]:
        """Describe the given active topics for the classifier prompt."""
        wanted = set(topic_ids)
        return tuple(
            TopicContext(topic.id, topic.name, topic.description)
            for topic in self._topics
            if topic.id in wanted
        )

    def evaluate(self, document_text: str) -> GateDecision:
        embedding = self._embedding_service.encode(document_text)
        if not self._topics:
            return GateDecision(True, embedding, (), "no_active_topics")

        matched: list[int] = []
        for topic in self._topics:
            if self._matches(topic, document_text, embedding):
                matched.append(topic.id)
        if matched:
            return GateDecision(True, embedding, tuple(matched), "topic_match")
        return GateDecision(False, embedding, (), "no_topic_match")

    def _matches(self, topic: Topic, text: str, embedding: list[float]) -> bool:
        if any(pattern.search(text) for pattern in self._product_patterns.get(topic.id, ())):
            return True
        vector = self._topic_vectors.get(topic.id)
        if vector is not None:
            return _cosine_distance(embedding, vector) <= topic.max_distance
        # No description to compare with: only a product mention can match a products-only
        # topic, while an intent-only topic cannot be pre-filtered and accepts everything.
        return not topic.products


def _cosine_distance(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 1.0
    return 1.0 - dot / (left_norm * right_norm)
