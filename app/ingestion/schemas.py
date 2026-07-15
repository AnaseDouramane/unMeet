from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class SourceItem:
    external_id: str
    source: str
    title: str
    body: str
    url: str
    author: str | None
    published_at: datetime
    engagement_score: int | None
    raw_payload: dict[str, Any]
