"""GDPR support: retention windows and erasure on request.

- **Erasure**: deletes every stored item of an author on a source (cascading to cluster
  membership and topic matches) and remembers only a hash of the username so later polls do not
  bring the posts back.
- **Retention**: items that never became a signal (not problems, or filtered out by the topic
  gate) are not needed by the product and are deleted after a short window; signals follow a
  longer one. Both windows are configuration.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import ErasureRequestModel, SourceItemModel
from app.database.session import SessionLocal


def _rowcount(result: Any) -> int:
    return int(cast("CursorResult[Any]", result).rowcount or 0)


def author_key(author: str) -> str:
    return hashlib.sha256(author.strip().lower().encode()).hexdigest()


@dataclass(frozen=True)
class RetentionResult:
    non_signals_deleted: int
    signals_deleted: int


class PrivacyRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def erase_author(self, source: str, author: str) -> int:
        """Delete all items of ``author`` on ``source`` and suppress future ingestion."""
        if not source.strip() or not author.strip():
            raise ValueError("source and author must not be empty")
        source = source.strip().lower()
        with self._session_factory() as session:
            deleted = _rowcount(
                session.execute(
                    delete(SourceItemModel).where(
                        SourceItemModel.source == source,
                        func.lower(SourceItemModel.author) == author.strip().lower(),
                    )
                )
            )
            session.execute(
                insert(ErasureRequestModel)
                .values(source=source, author_key=author_key(author))
                .on_conflict_do_nothing()
            )
            session.commit()
            return deleted

    def suppressed_authors(self, source: str) -> frozenset[str]:
        """Hashes of the authors on ``source`` who asked to be forgotten."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(ErasureRequestModel.author_key).where(
                    ErasureRequestModel.source == source.strip().lower()
                )
            )
            return frozenset(rows)

    def enforce_retention(
        self,
        non_signal_days: int,
        signal_days: int,
        now: datetime | None = None,
    ) -> RetentionResult:
        if non_signal_days <= 0 or signal_days <= 0:
            raise ValueError("retention windows must be positive")
        moment = now or datetime.now(UTC)
        non_signal_cutoff = moment - timedelta(days=non_signal_days)
        signal_cutoff = moment - timedelta(days=signal_days)
        with self._session_factory() as session:
            # Age is measured from when we processed the item, not from when it was posted.
            non_signals = _rowcount(
                session.execute(
                    delete(SourceItemModel).where(
                        or_(
                            SourceItemModel.is_problem.is_(None),
                            SourceItemModel.is_problem.is_(False),
                        ),
                        SourceItemModel.processed_at < non_signal_cutoff,
                    )
                )
            )
            signals = _rowcount(
                session.execute(
                    delete(SourceItemModel).where(
                        SourceItemModel.is_problem.is_(True),
                        SourceItemModel.processed_at < signal_cutoff,
                    )
                )
            )
            session.commit()
        return RetentionResult(non_signals, signals)


class ErasureFilter:
    """Tells the pipeline which authors must never be stored (loaded once per source)."""

    def __init__(self, repository: PrivacyRepository) -> None:
        self._repository = repository
        self._cache: dict[str, frozenset[str]] = {}

    def refresh(self) -> None:
        self._cache = {}

    def is_suppressed(self, source: str, author: str | None) -> bool:
        if not author:
            return False
        key = source.strip().lower()
        if key not in self._cache:
            self._cache[key] = self._repository.suppressed_authors(key)
        return author_key(author) in self._cache[key]
