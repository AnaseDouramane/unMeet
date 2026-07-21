from __future__ import annotations

import sys
from dataclasses import dataclass
from time import perf_counter

from app.config import Settings
from app.database.repository import SourceItemRepository
from app.services.ingestion_only import IngestionOnlyService, IngestionOnlyStats
from app.services.preprocessing import PreprocessingService
from scripts.run_unmeet import _build_connectors


@dataclass(frozen=True)
class IngestionOnlyResult:
    acquired_count: int
    new_count: int
    existing_count: int
    error_count: int


def run_ingestion(service: IngestionOnlyService, connectors) -> IngestionOnlyResult:
    totals = IngestionOnlyStats()
    for connector in connectors:
        try:
            stats = service.run(connector)
        except Exception as error:
            print(f"Errore ingestion per {getattr(connector, 'source', connector.__class__.__name__)}: {error}", file=sys.stderr)
            totals = IngestionOnlyStats(
                totals.acquired_count, totals.new_count, totals.existing_count, totals.error_count + 1
            )
            continue
        totals = IngestionOnlyStats(
            totals.acquired_count + stats.acquired_count,
            totals.new_count + stats.new_count,
            totals.existing_count + stats.existing_count,
            totals.error_count + stats.error_count,
        )
    return IngestionOnlyResult(
        acquired_count=totals.acquired_count,
        new_count=totals.new_count,
        existing_count=totals.existing_count,
        error_count=totals.error_count,
    )


def build_application(settings: Settings) -> tuple[IngestionOnlyService, tuple]:
    return (
        IngestionOnlyService(PreprocessingService(), SourceItemRepository()),
        _build_connectors(settings),
    )


def main() -> int:
    started_at = perf_counter()
    try:
        service, connectors = build_application(Settings())
        result = run_ingestion(service, connectors)
    except Exception as error:
        print(f"Errore ingestion: {error}", file=sys.stderr)
        return 1
    print(
        "\n".join(
            [
                "unMeet ingestion complete",
                f"Acquisiti: {result.acquired_count}",
                f"Nuovi: {result.new_count}",
                f"Già esistenti: {result.existing_count}",
                f"Errori: {result.error_count}",
                f"Durata totale: {perf_counter() - started_at:.2f}s",
            ]
        )
    )
    return 0 if result.error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
