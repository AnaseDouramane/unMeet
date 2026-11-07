from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.problem_detection.schemas import SIGNAL_INTENTS

MAX_SIGNAL_LIMIT = 500


@dataclass(frozen=True)
class SignalQuery:
    """Filters for the signal feed. Empty filters mean "no restriction".

    ``query_embedding`` restricts results to items within ``max_distance`` (cosine distance,
    0 = identical, 2 = opposite) of a topic description and orders them by similarity;
    otherwise the newest items come first.
    """

    intents: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    min_severity: int | None = None
    published_since: datetime | None = None
    processed_since: datetime | None = None
    query_embedding: Sequence[float] | None = field(default=None, compare=False)
    embedding_model: str | None = None
    max_distance: float = 0.6
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        unknown = set(self.intents) - SIGNAL_INTENTS
        if unknown:
            raise ValueError(f"unknown intents: {sorted(unknown)}")
        if self.min_severity is not None and not 1 <= self.min_severity <= 3:
            raise ValueError("min_severity must be between 1 and 3")
        if not 0 < self.max_distance <= 2:
            raise ValueError("max_distance must be in (0, 2]")
        if not 1 <= self.limit <= MAX_SIGNAL_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_SIGNAL_LIMIT}")
        if self.offset < 0:
            raise ValueError("offset must be non-negative")
        if (self.query_embedding is None) != (self.embedding_model is None):
            raise ValueError("query_embedding and embedding_model must be given together")
        for name in ("published_since", "processed_since"):
            moment = getattr(self, name)
            if moment is not None and moment.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class Signal:
    id: int
    source: str
    external_id: str
    title: str
    url: str
    author: str | None
    published_at: datetime
    intent: str | None
    pain_quote: str | None
    products_mentioned: tuple[str, ...]
    severity: int | None
    confidence: float
    similarity: float | None = None
