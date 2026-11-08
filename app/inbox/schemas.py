from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

InboxState = Literal["new", "relevant", "not_relevant", "replied"]
SETTABLE_STATES = frozenset({"relevant", "not_relevant", "replied"})
ALL_STATES = frozenset({"new", *SETTABLE_STATES})
MAX_BULK = 200


@dataclass(frozen=True)
class InboxItem:
    signal_id: int
    source: str
    title: str
    url: str
    author: str | None
    published_at: datetime
    intent: str | None
    pain_quote: str | None
    products_mentioned: tuple[str, ...]
    severity: int | None
    topic_id: int
    topic_name: str
    relevance_reason: str
    state: InboxState = "new"
    note: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class FeedbackExample:
    """A past decision of the workspace, usable as a few-shot example for the topic."""

    text: str
    relevant: bool
