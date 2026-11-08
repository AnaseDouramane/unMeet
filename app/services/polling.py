"""Near real-time ingestion: poll every source on an interval with per-source cursors.

Each poll runs the pipeline once per connector. A failing source never stops the others: it
backs off exponentially (capped) and is retried later. Cursors are committed only after the
pipeline finished a source successfully, so an interrupted poll re-fetches instead of losing
items. The loop stops cleanly when the ``stop`` event is set.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.ingestion.base import SourceConnector
from app.ingestion.cursors import CursorAwareConnector, CursorStore
from app.services.pipeline import PipelineRunStats

logger = logging.getLogger(__name__)

PollStatus = Literal["ok", "error", "backoff"]


class PipelineRunner(Protocol):
    last_run_stats: PipelineRunStats | None

    def run(self, connector: SourceConnector | None = None) -> object: ...


@dataclass(frozen=True)
class SourcePollResult:
    source: str
    status: PollStatus
    stats: PipelineRunStats | None = None
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class SourceHealth:
    consecutive_failures: int = 0
    last_success_at: float | None = None
    last_error: str | None = None
    next_attempt_at: float = 0.0


class PollingWorker:
    def __init__(
        self,
        pipeline: PipelineRunner,
        connectors: Sequence[SourceConnector],
        cursor_store: CursorStore,
        interval_seconds: float = 600.0,
        max_backoff_seconds: float = 3600.0,
        stall_after_seconds: float = 3 * 3600.0,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        if not connectors:
            raise ValueError("at least one connector is required")
        if interval_seconds <= 0 or max_backoff_seconds <= 0 or stall_after_seconds <= 0:
            raise ValueError("intervals must be positive")
        self._pipeline = pipeline
        self._connectors = tuple(connectors)
        self._cursor_store = cursor_store
        self.interval_seconds = interval_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.stall_after_seconds = stall_after_seconds
        self._clock = clock
        self._jitter = jitter or (lambda interval: interval * random.uniform(0.9, 1.1))
        self._started_at = clock()
        self.health: dict[str, SourceHealth] = {
            self._name(connector): SourceHealth() for connector in self._connectors
        }

    @staticmethod
    def _name(connector: SourceConnector) -> str:
        # ``name`` tells apart several connectors that feed the same ``source``.
        name = getattr(connector, "name", None) or getattr(connector, "source", None)
        return name if isinstance(name, str) and name.strip() else connector.__class__.__name__

    def poll_once(self) -> list[SourcePollResult]:
        results: list[SourcePollResult] = []
        for connector in self._connectors:
            results.append(self._poll_source(connector))
        return results

    def _poll_source(self, connector: SourceConnector) -> SourcePollResult:
        source = self._name(connector)
        health = self.health[source]
        started = self._clock()
        if started < health.next_attempt_at:
            return SourcePollResult(source, "backoff", error=health.last_error)
        try:
            cursor_connector = connector if isinstance(connector, CursorAwareConnector) else None
            if cursor_connector is not None:
                cursor_connector.load_cursors(self._cursor_store)
            self._pipeline.run(connector=connector)
            stats = self._pipeline.last_run_stats
            if stats is None:
                raise RuntimeError("pipeline completed without run statistics")
            if cursor_connector is not None:
                self._cursor_store.set_many(cursor_connector.pending_cursors())
        except Exception as error:
            health.consecutive_failures += 1
            health.last_error = str(error) or error.__class__.__name__
            delay = min(
                self.interval_seconds * 2**health.consecutive_failures, self.max_backoff_seconds
            )
            health.next_attempt_at = self._clock() + delay
            logger.error(
                "poll of %s failed (%d in a row), retrying in %.0fs: %s",
                source,
                health.consecutive_failures,
                delay,
                health.last_error,
            )
            return SourcePollResult(
                source,
                "error",
                error=health.last_error,
                duration_seconds=self._clock() - started,
            )
        health.consecutive_failures = 0
        health.last_error = None
        health.next_attempt_at = 0.0
        health.last_success_at = self._clock()
        logger.info(
            "polled %s: %d new/changed items, %d filtered by topics, %d LLM requests",
            source,
            stats.acquired_count - stats.skipped_count,
            stats.gated_out_count,
            stats.llm_call_count,
        )
        return SourcePollResult(source, "ok", stats=stats, duration_seconds=self._clock() - started)

    def stalled_sources(self) -> list[str]:
        """Sources with no successful poll for ``stall_after_seconds`` (never-polled included)."""
        now = self._clock()
        stalled = []
        for source, health in self.health.items():
            reference = (
                health.last_success_at if health.last_success_at is not None else self._started_at
            )
            if now - reference >= self.stall_after_seconds:
                stalled.append(source)
        return stalled

    def run(
        self,
        stop: threading.Event,
        wait: Callable[[float], bool] | None = None,
        max_cycles: int | None = None,
    ) -> int:
        """Poll until ``stop`` is set (or ``max_cycles`` is reached); return cycles completed."""
        waiter = wait or stop.wait
        cycles = 0
        while not stop.is_set():
            cycle_started = self._clock()
            self.poll_once()
            cycles += 1
            for source in self.stalled_sources():
                logger.error("ingestion stalled: no successful poll of %s recently", source)
            if max_cycles is not None and cycles >= max_cycles:
                break
            elapsed = self._clock() - cycle_started
            if waiter(max(self._jitter(self.interval_seconds) - elapsed, 1.0)):
                break
        return cycles
