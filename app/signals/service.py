from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.errors import DatabaseUnavailableError
from app.signals.schemas import Signal, SignalQuery


class SignalRepository(Protocol):
    def find_signals(self, query: SignalQuery) -> Sequence[Signal]: ...


class TextEncoder(Protocol):
    model_name: str

    def encode(self, document_text: str) -> list[float]: ...


class SignalReader(Protocol):
    def find(self, query: SignalQuery, topic: str | None = None) -> Sequence[Signal]: ...


class EmptySignalReader:
    def find(self, query: SignalQuery, topic: str | None = None) -> Sequence[Signal]:
        return ()


class RepositorySignalReader:
    """Reads the signal feed; a free-text ``topic`` becomes a semantic filter."""

    def __init__(self, encoder: TextEncoder, repository: SignalRepository) -> None:
        self._encoder = encoder
        self._repository = repository

    def find(self, query: SignalQuery, topic: str | None = None) -> Sequence[Signal]:
        if topic is not None and topic.strip():
            query = replace(
                query,
                query_embedding=self._encoder.encode(topic.strip()),
                embedding_model=self._encoder.model_name,
            )
        try:
            return self._repository.find_signals(query)
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("database is unavailable") from error


CSV_COLUMNS = (
    "published_at",
    "source",
    "intent",
    "severity",
    "pain_quote",
    "products_mentioned",
    "title",
    "url",
    "author",
    "confidence",
    "similarity",
)


def signals_to_csv(signals: Iterable[Signal]) -> str:
    """CSV with one row per signal, ready to import into Clay, Sheets or a CRM."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for signal in signals:
        writer.writerow(
            (
                signal.published_at.isoformat(),
                signal.source,
                signal.intent or "",
                "" if signal.severity is None else signal.severity,
                _safe_cell(signal.pain_quote or ""),
                "; ".join(signal.products_mentioned),
                _safe_cell(signal.title),
                signal.url,
                _safe_cell(signal.author or ""),
                f"{signal.confidence:.2f}",
                "" if signal.similarity is None else f"{signal.similarity:.3f}",
            )
        )
    return buffer.getvalue()


def _safe_cell(value: str) -> str:
    """Neutralise spreadsheet formula injection from user-generated text."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value
