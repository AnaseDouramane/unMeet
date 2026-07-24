from __future__ import annotations

import sys
from dataclasses import dataclass
from time import perf_counter

from app.config import Settings
from app.database.repository import SourceItemRepository
from app.ingestion.factory import build_configured_connectors
from app.services.ingestion_only import IngestionOnlyService, IngestionOnlyStats
from app.services.preprocessing import PreprocessingService


@dataclass(frozen=True)
class IngestionOnlyResult:
    acquired_count: int
    new_count: int
    existing_count: int
    error_count: int
    source_stats: tuple["IngestionOnlySourceResult", ...]


@dataclass(frozen=True)
class IngestionOnlySourceResult:
    source: str
    acquired_count: int
    new_count: int
    existing_count: int
    error_count: int


def run_ingestion(
    service: IngestionOnlyService, connectors, *, fail_fast: bool
) -> IngestionOnlyResult:
    totals = IngestionOnlyStats()
    source_stats: list[IngestionOnlySourceResult] = []
    for connector in connectors:
        source = getattr(connector, "source", connector.__class__.__name__)
        try:
            stats = service.run(connector)
        except Exception as error:
            print(f"Errore ingestion per {source}: {error}", file=sys.stderr)
            totals = IngestionOnlyStats(
                totals.acquired_count, totals.new_count, totals.existing_count, totals.error_count + 1
            )
            source_stats.append(IngestionOnlySourceResult(source, 0, 0, 0, 1))
            if fail_fast:
                break
            continue
        source_stats.append(
            IngestionOnlySourceResult(
                source, stats.acquired_count, stats.new_count, stats.existing_count, stats.error_count
            )
        )
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
        source_stats=tuple(source_stats),
    )


def build_application(settings: Settings) -> tuple[IngestionOnlyService, tuple, bool]:
    return (
        IngestionOnlyService(PreprocessingService(), SourceItemRepository()),
        build_configured_connectors(settings),
        settings.ingestion_fail_fast,
    )


def main() -> int:
    started_at = perf_counter()
    try:
        service, connectors, fail_fast = build_application(Settings())
        result = run_ingestion(service, connectors, fail_fast=fail_fast)
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
                *(
                    f"{item.source} — acquisiti: {item.acquired_count}, nuovi: {item.new_count}, "
                    f"già esistenti: {item.existing_count}, errori: {item.error_count}"
                    for item in result.source_stats
                ),
            ]
        )
    )
    return 0 if result.error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
