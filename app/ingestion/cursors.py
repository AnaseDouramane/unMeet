"""Per-source cursors for incremental polling.

A cursor is the high-water mark of what a connector has already handed to the pipeline, for
example the newest ``created_utc`` seen in one subreddit. Connectors read their cursors before
fetching and report new ones through :meth:`CursorAwareConnector.pending_cursors`; the caller
commits them only after the pipeline persisted the items, so a crash re-fetches instead of
silently skipping data (ingestion is idempotent, so a re-fetch is safe).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, runtime_checkable

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import SourceCursorModel
from app.database.session import SessionLocal


class CursorStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set_many(self, values: Mapping[str, str]) -> None: ...


@runtime_checkable
class CursorAwareConnector(Protocol):
    def load_cursors(self, store: CursorStore) -> None: ...

    def pending_cursors(self) -> Mapping[str, str]: ...


class InMemoryCursorStore:
    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        self._values: dict[str, str] = dict(initial or {})

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set_many(self, values: Mapping[str, str]) -> None:
        self._values.update(values)


class SourceCursorRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def get(self, key: str) -> str | None:
        with self._session_factory() as session:
            model = session.get(SourceCursorModel, key)
            return None if model is None else model.value

    def set_many(self, values: Mapping[str, str]) -> None:
        if not values:
            return
        with self._session_factory() as session:
            statement = insert(SourceCursorModel).values(
                [{"key": key, "value": value} for key, value in values.items()]
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[SourceCursorModel.key],
                    set_={"value": statement.excluded.value, "updated_at": func.now()},
                )
            )
            session.commit()
