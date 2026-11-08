from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import DeliveryChannelModel
from app.database.session import SessionLocal
from app.delivery.schemas import Channel
from app.tenancy.schemas import ConflictError, NotFoundError


class ChannelStore(Protocol):
    def add(self, workspace_id: int, kind: str, target: str, frequency: str) -> Channel: ...

    def list(self, workspace_id: int | None = None) -> tuple[Channel, ...]: ...

    def remove(self, workspace_id: int, channel_id: int) -> None: ...

    def mark_sent(self, channel_id: int, sent_at: datetime) -> None: ...

    def mark_failed(self, channel_id: int, error: str) -> None: ...


class ChannelRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def add(self, workspace_id: int, kind: str, target: str, frequency: str) -> Channel:
        with self._session_factory() as session:
            model = DeliveryChannelModel(
                workspace_id=workspace_id, kind=kind, target=target, frequency=frequency
            )
            session.add(model)
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ConflictError("this destination is already configured") from error
            session.refresh(model)
            return _to_channel(model)

    def list(self, workspace_id: int | None = None) -> tuple[Channel, ...]:
        statement = select(DeliveryChannelModel).order_by(DeliveryChannelModel.id)
        if workspace_id is not None:
            statement = statement.where(DeliveryChannelModel.workspace_id == workspace_id)
        with self._session_factory() as session:
            return tuple(_to_channel(m) for m in session.scalars(statement))

    def remove(self, workspace_id: int, channel_id: int) -> None:
        with self._session_factory() as session:
            model = session.get(DeliveryChannelModel, channel_id)
            if model is None or model.workspace_id != workspace_id:
                raise NotFoundError(f"channel {channel_id} does not exist")
            session.delete(model)
            session.commit()

    def mark_sent(self, channel_id: int, sent_at: datetime) -> None:
        with self._session_factory() as session:
            model = session.get(DeliveryChannelModel, channel_id)
            if model is not None:
                model.last_sent_at = sent_at
                model.last_error = None
                session.commit()

    def mark_failed(self, channel_id: int, error: str) -> None:
        with self._session_factory() as session:
            model = session.get(DeliveryChannelModel, channel_id)
            if model is not None:
                model.last_error = error[:500]
                session.commit()


class InMemoryChannelStore:
    def __init__(self) -> None:
        self._channels: dict[int, Channel] = {}
        self._next = 1

    def add(self, workspace_id: int, kind: str, target: str, frequency: str) -> Channel:
        if any(
            c.workspace_id == workspace_id and c.kind == kind and c.target == target
            for c in self._channels.values()
        ):
            raise ConflictError("this destination is already configured")
        channel = Channel(self._next, workspace_id, kind, target, frequency)  # type: ignore[arg-type]
        self._channels[channel.id] = channel
        self._next += 1
        return channel

    def list(self, workspace_id: int | None = None) -> tuple[Channel, ...]:
        return tuple(
            c
            for c in self._channels.values()
            if workspace_id is None or c.workspace_id == workspace_id
        )

    def remove(self, workspace_id: int, channel_id: int) -> None:
        channel = self._channels.get(channel_id)
        if channel is None or channel.workspace_id != workspace_id:
            raise NotFoundError(f"channel {channel_id} does not exist")
        del self._channels[channel_id]

    def mark_sent(self, channel_id: int, sent_at: datetime) -> None:
        from dataclasses import replace

        if channel_id in self._channels:
            self._channels[channel_id] = replace(
                self._channels[channel_id], last_sent_at=sent_at, last_error=None
            )

    def mark_failed(self, channel_id: int, error: str) -> None:
        from dataclasses import replace

        if channel_id in self._channels:
            self._channels[channel_id] = replace(self._channels[channel_id], last_error=error[:500])


def _to_channel(model: DeliveryChannelModel) -> Channel:
    return Channel(
        id=model.id,
        workspace_id=model.workspace_id,
        kind=model.kind,  # type: ignore[arg-type]
        target=model.target,
        frequency=model.frequency,  # type: ignore[arg-type]
        enabled=model.enabled,
        last_sent_at=model.last_sent_at,
        last_error=model.last_error,
    )
