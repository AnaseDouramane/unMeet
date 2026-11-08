from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.net.safe_fetch import Resolver, validate_public_url
from app.tenancy.schemas import normalize_email

ChannelKind = Literal["email", "slack"]
Frequency = Literal["daily", "weekly"]
INTERVALS = {"daily": timedelta(hours=23), "weekly": timedelta(days=6, hours=23)}


@dataclass(frozen=True)
class Channel:
    id: int
    workspace_id: int
    kind: ChannelKind
    target: str
    frequency: Frequency
    enabled: bool = True
    last_sent_at: datetime | None = None
    last_error: str | None = None

    def is_due(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        return self.last_sent_at is None or now - self.last_sent_at >= INTERVALS[self.frequency]


def validate_target(kind: str, target: str, resolver: Resolver | None = None) -> str:
    """Normalise a channel target; raises ValueError for anything unsafe or malformed."""
    if kind == "email":
        return normalize_email(target)
    if kind == "slack":
        cleaned = target.strip()
        if not re.match(r"^https://hooks\.slack\.com/(services|workflows|triggers)/", cleaned):
            raise ValueError(
                "a Slack incoming webhook URL (https://hooks.slack.com/...) is required"
            )
        try:
            if resolver is None:
                validate_public_url(cleaned)
            else:
                validate_public_url(cleaned, resolver)
        except ValueError as error:
            raise ValueError(f"invalid Slack webhook URL: {error}") from error
        return cleaned
    raise ValueError("kind must be 'email' or 'slack'")
