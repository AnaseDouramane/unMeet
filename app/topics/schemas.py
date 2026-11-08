from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from app.problem_detection.schemas import SIGNAL_INTENTS


@dataclass(frozen=True)
class TopicDefinition:
    """What a user wants to track.

    ``description`` is matched semantically (for example "reps losing deals because CRM data is
    stale"); intents, products and sources narrow the match. At least one criterion is needed.
    """

    name: str
    description: str | None = None
    intents: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    min_severity: int | None = None
    max_distance: float = 0.6
    webhook_url: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name.strip()) > 120:
            raise ValueError("name must be 1-120 characters")
        if self.description is not None and not self.description.strip():
            raise ValueError("description must not be blank")
        if not (self.description or self.intents or self.products):
            raise ValueError("a topic needs a description, intents or products")
        unknown = set(self.intents) - (SIGNAL_INTENTS - {"none"})
        if unknown:
            raise ValueError(f"unknown intents: {sorted(unknown)}")
        if self.min_severity is not None and not 1 <= self.min_severity <= 3:
            raise ValueError("min_severity must be between 1 and 3")
        if not 0 < self.max_distance <= 2:
            raise ValueError("max_distance must be in (0, 2]")
        if self.webhook_url is not None:
            validate_webhook_url(self.webhook_url)


@dataclass(frozen=True)
class Topic(TopicDefinition):
    id: int = 0
    workspace_id: int = 0
    created_at: datetime | None = None
    last_delivered_at: datetime | None = None


def validate_webhook_url(url: str) -> None:
    """Only absolute https URLs to public hostnames are accepted.

    Webhooks are fetched server-side, so plain http and local hostnames are refused to avoid
    leaking data in clear text or reaching internal services.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise ValueError("webhook_url must be an absolute https URL")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("webhook_url must point to a public host")
    if _is_private_ip_literal(host):
        raise ValueError("webhook_url must point to a public host")


def _is_private_ip_literal(host: str) -> bool:
    import ipaddress

    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return not address.is_global
