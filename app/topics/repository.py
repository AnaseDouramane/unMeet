from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import TrackedTopicModel
from app.database.session import SessionLocal
from app.topics.schemas import Topic, TopicDefinition


class DuplicateTopicError(ValueError):
    pass


class TopicRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def create(self, definition: TopicDefinition, workspace_id: int) -> Topic:
        with self._session_factory() as session:
            model = TrackedTopicModel(
                workspace_id=workspace_id,
                name=definition.name.strip(),
                description=definition.description.strip() if definition.description else None,
                intents=list(definition.intents),
                products=list(definition.products),
                sources=list(definition.sources),
                min_severity=definition.min_severity,
                max_distance=definition.max_distance,
                webhook_url=definition.webhook_url,
            )
            session.add(model)
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise DuplicateTopicError(f"a topic named {model.name!r} exists") from error
            session.refresh(model)
            return _to_topic(model)

    def list(self, workspace_id: int | None = None) -> tuple[Topic, ...]:
        statement = select(TrackedTopicModel).order_by(TrackedTopicModel.id)
        if workspace_id is not None:
            statement = statement.where(TrackedTopicModel.workspace_id == workspace_id)
        with self._session_factory() as session:
            return tuple(_to_topic(model) for model in session.scalars(statement))

    def get(self, topic_id: int, workspace_id: int | None = None) -> Topic | None:
        with self._session_factory() as session:
            model = session.get(TrackedTopicModel, topic_id)
            if model is None or (workspace_id is not None and model.workspace_id != workspace_id):
                return None
            return _to_topic(model)

    def delete(self, topic_id: int, workspace_id: int | None = None) -> bool:
        with self._session_factory() as session:
            model = session.get(TrackedTopicModel, topic_id)
            if model is None or (workspace_id is not None and model.workspace_id != workspace_id):
                return False
            session.delete(model)
            session.commit()
            return True

    def count(self, workspace_id: int) -> int:
        with self._session_factory() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(TrackedTopicModel)
                    .where(TrackedTopicModel.workspace_id == workspace_id)
                )
                or 0
            )

    def mark_delivered(self, topic_id: int, delivered_at: datetime) -> None:
        if delivered_at.tzinfo is None:
            raise ValueError("delivered_at must be timezone-aware")
        with self._session_factory() as session:
            model = session.get(TrackedTopicModel, topic_id)
            if model is None:
                raise LookupError(f"topic {topic_id} does not exist")
            model.last_delivered_at = delivered_at
            session.commit()


def _to_topic(model: TrackedTopicModel) -> Topic:
    return Topic(
        id=model.id,
        workspace_id=model.workspace_id,
        name=model.name,
        description=model.description,
        intents=tuple(model.intents or ()),
        products=tuple(model.products or ()),
        sources=tuple(model.sources or ()),
        min_severity=model.min_severity,
        max_distance=model.max_distance,
        webhook_url=model.webhook_url,
        created_at=model.created_at,
        last_delivered_at=model.last_delivered_at,
    )
