from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.ingestion.base import SourceConnector
from app.services.pipeline import PipelineRunStats


class PipelineRunner(Protocol):
    last_run_stats: PipelineRunStats | None

    def run(self, connector: SourceConnector | None = None) -> object: ...


@dataclass(frozen=True)
class SourceIngestionStats:
    source: str
    acquired_count: int
    problem_count: int
    non_problem_count: int
    embedding_count: int
    classification_error_count: int


@dataclass(frozen=True)
class SourceIngestionError:
    source: str
    message: str


@dataclass(frozen=True)
class MultiSourceIngestionResult:
    acquired_count: int
    problem_count: int
    non_problem_count: int
    embedding_count: int
    classification_error_count: int
    source_stats: tuple[SourceIngestionStats, ...]
    errors: tuple[SourceIngestionError, ...]
    successful_source_count: int
    failed_source_count: int
    is_success: bool


class MultiSourceIngestionService:
    def __init__(
        self,
        pipeline: PipelineRunner,
        connectors: Sequence[SourceConnector],
        fail_fast: bool = True,
    ) -> None:
        if not connectors:
            raise ValueError("at least one ingestion connector must be configured")
        self._pipeline = pipeline
        self._connectors = tuple(connectors)
        self._fail_fast = fail_fast

    def run(self) -> MultiSourceIngestionResult:
        source_stats: list[SourceIngestionStats] = []
        errors: list[SourceIngestionError] = []
        for connector in self._connectors:
            source = self._source_name(connector)
            try:
                self._pipeline.run(connector=connector)
                stats = self._pipeline.last_run_stats
                if stats is None:
                    raise RuntimeError("pipeline completed without run statistics")
                source_stats.append(self._to_source_stats(source, stats))
            except Exception as error:
                errors.append(SourceIngestionError(source=source, message=str(error)))
                if self._fail_fast:
                    break

        return MultiSourceIngestionResult(
            acquired_count=sum(item.acquired_count for item in source_stats),
            problem_count=sum(item.problem_count for item in source_stats),
            non_problem_count=sum(item.non_problem_count for item in source_stats),
            embedding_count=sum(item.embedding_count for item in source_stats),
            classification_error_count=sum(
                item.classification_error_count for item in source_stats
            ),
            source_stats=tuple(source_stats),
            errors=tuple(errors),
            successful_source_count=len(source_stats),
            failed_source_count=len(errors),
            is_success=not errors and bool(source_stats),
        )

    @staticmethod
    def _source_name(connector: SourceConnector) -> str:
        source = getattr(connector, "source", connector.__class__.__name__)
        if not isinstance(source, str) or not source.strip():
            raise ValueError("connector source name must be a non-empty string")
        return source.strip()

    @staticmethod
    def _to_source_stats(source: str, stats: PipelineRunStats) -> SourceIngestionStats:
        return SourceIngestionStats(
            source=source,
            acquired_count=stats.acquired_count,
            problem_count=stats.problem_count,
            non_problem_count=stats.non_problem_count,
            embedding_count=stats.embedding_count,
            classification_error_count=stats.classification_error_count,
        )
