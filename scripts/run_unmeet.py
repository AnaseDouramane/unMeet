from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.exc import SQLAlchemyError

from app.analysis.orchestrator import AnalysisOrchestrator
from app.clustering.hdbscan_clusterer import HDBSCANClusterer
from app.clustering.matching import ClusterMatchingService
from app.clustering.service import ClusteringService
from app.clustering.topic_labeling import TopicLabelingService
from app.clustering.trend_detection import TrendDetectionService
from app.config import Settings
from app.database.repository import ClusterRepository, SourceItemRepository
from app.database.schemas import ClusterRunMetadata
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.hackernews import HackerNewsConnector
from app.ingestion.github import GitHubIssuesConnector
from app.ingestion.reddit import RedditConnector
from app.problem_detection.qwen3 import Qwen3ProblemClassifier
from app.problem_detection.service import ProblemDetectionService
from app.services.pipeline import Pipeline
from app.services.multi_source_ingestion import (
    MultiSourceIngestionResult,
    MultiSourceIngestionService,
)
from app.services.preprocessing import PreprocessingService


@dataclass(frozen=True)
class UnmeetApplication:
    ingestion_service: MultiSourceIngestionService
    analysis_orchestrator: AnalysisOrchestrator
    fail_fast: bool


def build_application(settings: Settings) -> UnmeetApplication:
    connectors = _build_connectors(settings)
    preprocessing_service = PreprocessingService()
    classifier = Qwen3ProblemClassifier()
    problem_detection_service = ProblemDetectionService(classifier)
    embedding_service = EmbeddingService(model_name=settings.embedding_model)
    source_item_repository = SourceItemRepository()
    pipeline = Pipeline(
        settings=settings,
        connector=connectors[0],
        preprocessing_service=preprocessing_service,
        repository=source_item_repository,
        embedding_service=embedding_service,
        problem_detection_service=problem_detection_service,
    )

    clusterer = HDBSCANClusterer()
    clustering_service = ClusteringService(source_item_repository, clusterer)
    topic_labeling_service = TopicLabelingService()
    cluster_repository = ClusterRepository()
    cluster_matching_service = ClusterMatchingService()
    trend_detection_service = TrendDetectionService()
    analysis_orchestrator = AnalysisOrchestrator(
        clustering_service=clustering_service,
        topic_labeling_service=topic_labeling_service,
        cluster_repository=cluster_repository,
        cluster_matching_service=cluster_matching_service,
        trend_detection_service=trend_detection_service,
        metadata=ClusterRunMetadata(
            embedding_model=embedding_service.model_name,
            min_cluster_size=clusterer.min_cluster_size,
            min_samples=clusterer.min_samples,
            metric=clusterer.metric,
        ),
    )
    return UnmeetApplication(
        ingestion_service=MultiSourceIngestionService(
            pipeline=pipeline,
            connectors=connectors,
            fail_fast=settings.ingestion_fail_fast,
        ),
        analysis_orchestrator=analysis_orchestrator,
        fail_fast=settings.ingestion_fail_fast,
    )


def _build_connectors(
    settings: Settings,
) -> tuple[HackerNewsConnector | RedditConnector | GitHubIssuesConnector, ...]:
    connectors: list[HackerNewsConnector | RedditConnector | GitHubIssuesConnector] = []
    for source in _normalize_enabled_sources(settings.enabled_sources):
        if source == "hackernews":
            connectors.append(
                HackerNewsConnector(
                    feeds=settings.hackernews_feeds,
                    limit=settings.hackernews_limit,
                )
            )
        elif source == "reddit":
            connectors.append(RedditConnector.from_settings(settings))
        elif source == "github":
            connectors.append(GitHubIssuesConnector.from_settings(settings))
        else:
            raise ValueError(f"Unsupported ingestion source: {source}")
    if not connectors:
        raise ValueError("At least one ingestion source must be enabled")
    return tuple(connectors)


def _normalize_enabled_sources(sources: Sequence[str]) -> tuple[str, ...]:
    if isinstance(sources, (str, bytes)):
        raise TypeError("enabled_sources must be a sequence of source names")

    normalized_sources: list[str] = []
    seen_sources: set[str] = set()
    for source in sources:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("enabled source names must be non-empty strings")
        normalized_source = source.strip().lower()
        if normalized_source in seen_sources:
            raise ValueError(f"Duplicate ingestion source: {normalized_source}")
        seen_sources.add(normalized_source)
        normalized_sources.append(normalized_source)
    return tuple(normalized_sources)


def main() -> int:
    started_at = perf_counter()
    try:
        settings = Settings()
        application = build_application(settings)
    except (TypeError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    except ImportError as error:
        print(f"Required dependency error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Application setup error: {error}", file=sys.stderr)
        return 1

    try:
        ingestion_result = application.ingestion_service.run()
    except SQLAlchemyError as error:
        print(f"Database error during ingestion: {error}", file=sys.stderr)
        return 1
    except (ImportError, OSError, RuntimeError) as error:
        print(f"Model or runtime error during ingestion: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Pipeline error: {error}", file=sys.stderr)
        return 1

    for error in ingestion_result.errors:
        print(f"Ingestion error for {error.source}: {error.message}", file=sys.stderr)
    if (application.fail_fast and ingestion_result.errors) or (
        ingestion_result.successful_source_count == 0
    ):
        print("Ingestion failed before analysis", file=sys.stderr)
        return 1

    try:
        analysis_result = application.analysis_orchestrator.run()
    except SQLAlchemyError as error:
        print(f"Database error during analysis: {error}", file=sys.stderr)
        return 1
    except (ImportError, OSError, RuntimeError) as error:
        print(f"Model or runtime error during analysis: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Analysis error: {error}", file=sys.stderr)
        return 1

    print(_format_summary(ingestion_result, analysis_result, perf_counter() - started_at))
    return 0


def _format_summary(
    ingestion_result: MultiSourceIngestionResult, analysis_result, duration_seconds: float
) -> str:
    trend_counts = Counter(trend.status for trend in analysis_result.trend)
    return "\n".join(
        [
            "unMeet run complete",
            f"Posts acquired: {ingestion_result.acquired_count}",
            f"Problems identified: {ingestion_result.problem_count}",
            f"Non-problem posts archived: {ingestion_result.non_problem_count}",
            f"Classification errors: {ingestion_result.classification_error_count}",
            f"Documents with embeddings: {ingestion_result.embedding_count}",
            f"Analysis run ID: {analysis_result.run_id}",
            f"Clusters: {analysis_result.cluster_count}",
            f"Documents clustered: {analysis_result.document_count}",
            f"Trends — new: {trend_counts['new']}, rising: {trend_counts['rising']}, "
            f"stable: {trend_counts['stable']}, falling: {trend_counts['falling']}",
            f"Total duration: {duration_seconds:.2f}s",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
