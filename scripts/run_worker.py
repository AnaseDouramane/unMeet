"""Near real-time ingestion worker: poll every configured source on an interval.

Run it as a long-lived process (container, systemd, Fly/Railway worker). Sources are polled
every ``POLL_INTERVAL_SECONDS`` with per-source cursors; a failing source backs off on its own
and never blocks the others. SIGTERM/SIGINT finish the current poll and exit cleanly. Clustering
and alert delivery stay separate jobs (``run_analysis``, ``deliver_alerts``).
"""

from __future__ import annotations

import logging
import signal
import sys
import threading

from app.config import Settings
from app.ingestion.cursors import SourceCursorRepository
from app.services.polling import PollingWorker
from app.utils.logging import configure_logging
from scripts.run_unmeet import build_ingestion

logger = logging.getLogger("unmeet.worker")


def main() -> int:
    configure_logging()
    try:
        settings = Settings()
        ingestion = build_ingestion(settings)
    except Exception as error:  # configuration or dependency problem: fail before looping
        print(f"Worker setup error: {error}", file=sys.stderr)
        return 1

    worker = PollingWorker(
        ingestion.pipeline,
        ingestion.connectors,
        SourceCursorRepository(),
        interval_seconds=settings.poll_interval_seconds,
        max_backoff_seconds=settings.poll_max_backoff_seconds,
        stall_after_seconds=settings.poll_stall_after_seconds,
    )
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())

    logger.info(
        "polling %s every %ss",
        ", ".join(sorted(worker.health)),
        settings.poll_interval_seconds,
    )
    cycles = worker.run(stop)
    logger.info("worker stopped after %d cycles", cycles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
