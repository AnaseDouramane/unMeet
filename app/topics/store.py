from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from typing import Protocol

from app.topics.repository import DuplicateTopicError
from app.topics.schemas import Topic, TopicDefinition


class TopicStore(Protocol):
    """Topics belong to a workspace. ``workspace_id=None`` means "all workspaces" and is for
    internal jobs (the topic gate, alert delivery); API code always passes the caller's."""

    def create(self, definition: TopicDefinition, workspace_id: int) -> Topic: ...

    def list(self, workspace_id: int | None = None) -> tuple[Topic, ...]: ...

    def get(self, topic_id: int, workspace_id: int | None = None) -> Topic | None: ...

    def delete(self, topic_id: int, workspace_id: int | None = None) -> bool: ...

    def count(self, workspace_id: int) -> int: ...

    def mark_delivered(self, topic_id: int, delivered_at: datetime) -> None: ...


class InMemoryTopicStore:
    """Process-local store used by tests and API instances without a database."""

    def __init__(self) -> None:
        self._topics: dict[int, Topic] = {}
        self._next_id = 1

    def create(self, definition: TopicDefinition, workspace_id: int) -> Topic:
        name = definition.name.strip()
        if any(
            t.name == name and t.workspace_id == workspace_id for t in self._topics.values()
        ):
            raise DuplicateTopicError(f"a topic named {definition.name!r} exists")
        values = {f.name: getattr(definition, f.name) for f in fields(TopicDefinition)}
        values["name"] = name
        topic = Topic(
            **values, id=self._next_id, workspace_id=workspace_id, created_at=datetime.now(UTC)
        )
        self._topics[topic.id] = topic
        self._next_id += 1
        return topic

    def list(self, workspace_id: int | None = None) -> tuple[Topic, ...]:
        return tuple(
            self._topics[key]
            for key in sorted(self._topics)
            if workspace_id is None or self._topics[key].workspace_id == workspace_id
        )

    def get(self, topic_id: int, workspace_id: int | None = None) -> Topic | None:
        topic = self._topics.get(topic_id)
        if topic is None or (workspace_id is not None and topic.workspace_id != workspace_id):
            return None
        return topic

    def delete(self, topic_id: int, workspace_id: int | None = None) -> bool:
        if self.get(topic_id, workspace_id) is None:
            return False
        del self._topics[topic_id]
        return True

    def count(self, workspace_id: int) -> int:
        return len(self.list(workspace_id))

    def mark_delivered(self, topic_id: int, delivered_at: datetime) -> None:
        topic = self._topics[topic_id]
        values = {f.name: getattr(topic, f.name) for f in fields(Topic)}
        values["last_delivered_at"] = delivered_at
        self._topics[topic_id] = Topic(**values)
