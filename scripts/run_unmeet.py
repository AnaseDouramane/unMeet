from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.exc import SQLAlchemyError

from app.analysis.orchestrator import AnalysisOrchestrator
from app.clustering.factory import build_cluster_labeler
from app.clustering.hdbscan_clusterer import HDBSCANClusterer
from app.clustering.matching import ClusterMatchingService
from app.clustering.service import ClusteringService
from app.clustering.trend_detection import TrendDetectionService
from app.config import Settings
from app.database.repository import ClusterRepository, SourceItemRepository
from app.database.schemas import ClusterRunMetadata
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.base import SourceConnector
from app.ingestion.factory import build_configured_connectors
from app.problem_detection.factory import build_problem_classifier
from app.problem_detection.service import ProblemDetectionService
from app.services.multi_source_ingestion import (
    MultiSourceIngestionResult,
    MultiSourceIngestionService,
)
from app.services.pipeline import Pipeline
from app.services.preprocessing import PreprocessingService
from app.topics.gate import TopicGate
from app.topics.repository import TopicRepository


@dataclass(frozen=True)
class UnmeetApplication:
    ingestion_service: MultiSourceIngestionService
    analysis_orchestrator: AnalysisOrchestrator
    fail_fast: bool


@dataclass(frozen=True)
class IngestionComponents:
    pipeline: Pipeline
    connectors: tuple[SourceConnector, ...]
    embedding_service: EmbeddingService
    source_item_repository: SourceItemRepository


def build_ingestion(settings: Settings) -> IngestionComponents:
    """Build the ingestion half (connectors, topic gate, classifier, pipeline)."""
    connectors = build_configured_connectors(settings)
    preprocessing_service = PreprocessingService()
    classifier = build_problem_classifier(settings)
    problem_detection_service = ProblemDetectionService(classifier)
    embedding_service = EmbeddingService(model_name=settings.embedding_model)
    source_item_repository = SourceItemRepository()
    topic_gate = (
        TopicGate(TopicRepository().list, embedding_service)
        if getattr(settings, "topic_gate_enabled", False)
        else None
    )
    pipeline = Pipeline(
        settings=settings,
        connector=connectors[0],
        preprocessing_service=preprocessing_service,
        repository=source_item_repository,
        embedding_service=embedding_service,
        problem_detection_service=problem_detection_service,
        classification_workers=getattr(settings, "classification_workers", 1),
        topic_gate=topic_gate,
        classification_batch_size=getattr(settings, "classification_batch_size", 1),
    )
    return IngestionComponents(pipeline, connectors, embedding_service, source_item_repository)


def build_application(settings: Settings) -> UnmeetApplication:
    ingestion = build_ingestion(settings)
    connectors = ingestion.connectors
    pipeline = ingestion.pipeline
    embedding_service = ingestion.embedding_service
    source_item_repository = ingestion.source_item_repository

    clusterer = HDBSCANClusterer.for_text_embeddings()
    clustering_service = ClusteringService(source_item_repository, clusterer)
    topic_labeling_service = build_cluster_labeler(settings)
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
            metric=clusterer.run_metric,
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
            f"Already classified (skipped): {ingestion_result.skipped_count}",
            f"Filtered out before the LLM (no topic match): {ingestion_result.gated_out_count}",
            f"LLM classification calls: {ingestion_result.llm_call_count}",
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
