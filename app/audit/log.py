"""Append-only audit trail of write operations (who did what, when, to which resource)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AuditLogModel
from app.database.session import SessionLocal


@dataclass(frozen=True)
class AuditEvent:
    actor: str
    action: str
    resource_type: str
    resource_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    id: int = 0
    created_at: datetime | None = None


class AuditLog(Protocol):
    def record(self, event: AuditEvent) -> AuditEvent: ...

    def list(self, limit: int = 100, offset: int = 0) -> tuple[AuditEvent, ...]: ...


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> AuditEvent:
        stored = AuditEvent(
            actor=event.actor,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            details=dict(event.details),
            request_id=event.request_id,
            id=len(self._events) + 1,
            created_at=datetime.now(UTC),
        )
        self._events.append(stored)
        return stored

    def list(self, limit: int = 100, offset: int = 0) -> tuple[AuditEvent, ...]:
        newest_first = list(reversed(self._events))
        return tuple(newest_first[offset : offset + limit])


class AuditLogRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def record(self, event: AuditEvent) -> AuditEvent:
        with self._session_factory() as session:
            model = AuditLogModel(
                actor=event.actor,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                details=dict(event.details),
                request_id=event.request_id,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return _to_event(model)

    def list(self, limit: int = 100, offset: int = 0) -> tuple[AuditEvent, ...]:
        with self._session_factory() as session:
            statement = (
                select(AuditLogModel)
                .order_by(AuditLogModel.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return tuple(_to_event(model) for model in session.scalars(statement))


def _to_event(model: AuditLogModel) -> AuditEvent:
    return AuditEvent(
        id=model.id,
        created_at=model.created_at,
        actor=model.actor,
        action=model.action,
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        details=dict(model.details or {}),
        request_id=model.request_id,
    )
