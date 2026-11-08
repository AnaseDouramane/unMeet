"""Landing-page demo: paste a URL, see a few real recent conversations that match your product.

It costs money (one LLM analysis per site) and is open to anyone, so it is built defensively:
disabled unless explicitly enabled, a hit on the cache is free, a global daily cap bounds spend,
and the API layer adds a per-visitor limit. The results never include author names.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from urllib.parse import urlparse

from app.onboarding.service import OnboardingProposal
from app.signals.schemas import Signal, SignalQuery
from app.signals.service import SignalReader

MAX_SIGNALS = 5
MAX_TOPICS = 3
CACHE_ENTRIES = 500


class DemoBusyError(RuntimeError):
    """The daily budget of demo analyses is used up."""


class _Onboarding(Protocol):
    def analyze(self, url: str, workspace_id: int | None = None) -> OnboardingProposal: ...


@dataclass(frozen=True)
class DemoSignal:
    source: str
    title: str
    url: str
    published_at: datetime
    quote: str | None
    intent: str | None
    similarity: float | None


@dataclass(frozen=True)
class DemoResult:
    product_summary: str
    competitors: tuple[str, ...]
    topics: tuple[str, ...]
    signals: tuple[DemoSignal, ...]


def canonical_key(url: str) -> str:
    parsed = urlparse(url.strip())
    return f"{(parsed.hostname or '').lower()}{parsed.path.rstrip('/')}"


class DemoService:
    def __init__(
        self,
        onboarding: _Onboarding,
        signals: SignalReader,
        daily_limit: int = 100,
        cache_ttl_seconds: float = 86400.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._onboarding = onboarding
        self._signals = signals
        self._daily_limit = daily_limit
        self._ttl = cache_ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, tuple[datetime, DemoResult]] = OrderedDict()
        self._day: date | None = None
        self._used_today = 0

    def run(self, url: str) -> DemoResult:
        key = canonical_key(url)
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and (now - cached[0]).total_seconds() < self._ttl:
                self._cache.move_to_end(key)
                return cached[1]
            if self._day != now.date():
                self._day, self._used_today = now.date(), 0
            if self._used_today >= self._daily_limit:
                raise DemoBusyError("the demo is busy, try again tomorrow")
            self._used_today += 1
        proposal = self._onboarding.analyze(url)
        result = DemoResult(
            product_summary=proposal.product_summary,
            competitors=proposal.competitors,
            topics=tuple(t.name for t in proposal.topics[:MAX_TOPICS]),
            signals=self._find_signals(proposal),
        )
        with self._lock:
            self._cache[key] = (now, result)
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return result

    def _find_signals(self, proposal: OnboardingProposal) -> tuple[DemoSignal, ...]:
        best: dict[int, Signal] = {}
        for topic in proposal.topics[:MAX_TOPICS]:
            for signal in self._signals.find(SignalQuery(limit=MAX_SIGNALS), topic.description):
                known = best.get(signal.id)
                if known is None or (signal.similarity or 0) > (known.similarity or 0):
                    best[signal.id] = signal
        ranked = sorted(
            best.values(),
            key=lambda s: (-(s.similarity or 0.0), -s.published_at.timestamp(), s.id),
        )[:MAX_SIGNALS]
        return tuple(
            DemoSignal(
                source=s.source,
                title=s.title,
                url=s.url,
                published_at=s.published_at,
                quote=s.pain_quote,
                intent=s.intent,
                similarity=s.similarity,
            )
            for s in ranked
        )
