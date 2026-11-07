from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from typing import Protocol

from app.topics.repository import DuplicateTopicError
from app.topics.schemas import Topic, TopicDefinition


class TopicStore(Protocol):
    def create(self, definition: TopicDefinition) -> Topic: ...

    def list(self) -> tuple[Topic, ...]: ...

    def get(self, topic_id: int) -> Topic | None: ...

    def delete(self, topic_id: int) -> bool: ...

    def mark_delivered(self, topic_id: int, delivered_at: datetime) -> None: ...


class InMemoryTopicStore:
    """Process-local store used by tests and API instances without a database."""

    def __init__(self) -> None:
        self._topics: dict[int, Topic] = {}
        self._next_id = 1

    def create(self, definition: TopicDefinition) -> Topic:
        if any(topic.name == definition.name.strip() for topic in self._topics.values()):
            raise DuplicateTopicError(f"a topic named {definition.name!r} exists")
        values = {f.name: getattr(definition, f.name) for f in fields(TopicDefinition)}
        values["name"] = definition.name.strip()
        topic = Topic(**values, id=self._next_id, created_at=datetime.now(UTC))
        self._topics[topic.id] = topic
        self._next_id += 1
        return topic

    def list(self) -> tuple[Topic, ...]:
        return tuple(self._topics[key] for key in sorted(self._topics))

    def get(self, topic_id: int) -> Topic | None:
        return self._topics.get(topic_id)

    def delete(self, topic_id: int) -> bool:
        return self._topics.pop(topic_id, None) is not None

    def mark_delivered(self, topic_id: int, delivered_at: datetime) -> None:
        topic = self._topics[topic_id]
        values = {f.name: getattr(topic, f.name) for f in fields(Topic)}
        values["last_delivered_at"] = delivered_at
        self._topics[topic_id] = Topic(**values)
