from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.exc import SQLAlchemyError

from app.analysis.orchestrator import AnalysisOrchestrator, AnalysisRunResult
from app.clustering.hdbscan_clusterer import HDBSCANClusterer
from app.clustering.matching import ClusterMatchingService
from app.clustering.service import ClusteringService
from app.clustering.topic_labeling import TopicLabelingService
from app.clustering.trend_detection import TrendDetectionService
from app.config import Settings
from app.database.repository import ClusterRepository, SourceItemRepository
from app.database.schemas import ClusterRunMetadata


@dataclass(frozen=True)
class AnalysisApplication:
    source_item_repository: SourceItemRepository
    analysis_orchestrator: AnalysisOrchestrator


def build_application(settings: Settings) -> AnalysisApplication:
    source_item_repository = SourceItemRepository()
    clusterer = HDBSCANClusterer()
    analysis_orchestrator = AnalysisOrchestrator(
        clustering_service=ClusteringService(source_item_repository, clusterer),
        topic_labeling_service=TopicLabelingService(),
        cluster_repository=ClusterRepository(),
        cluster_matching_service=ClusterMatchingService(),
        trend_detection_service=TrendDetectionService(),
        metadata=ClusterRunMetadata(
            embedding_model=settings.embedding_model,
            min_cluster_size=clusterer.min_cluster_size,
            min_samples=clusterer.min_samples,
            metric=clusterer.metric,
        ),
    )
    return AnalysisApplication(
        source_item_repository=source_item_repository,
        analysis_orchestrator=analysis_orchestrator,
    )


def count_available_problems(repository: SourceItemRepository) -> int:
    return sum(count for _, count in repository.count_problems_by_source())


def format_summary(
    problem_count: int,
    analysis_result: AnalysisRunResult,
    duration_seconds: float,
) -> str:
    documents_assigned = sum(cluster.document_count for cluster in analysis_result.clusters)
    noise_documents = analysis_result.document_count - documents_assigned
    trend_counts = Counter(trend.status for trend in analysis_result.trend)
    return "\n".join(
        [
            "unMeet analysis complete",
            f"Problemi disponibili: {problem_count}",
            f"Documenti con embedding: {analysis_result.document_count}",
            f"Run ID: {analysis_result.run_id}",
            f"Cluster creati: {analysis_result.cluster_count}",
            f"Documenti assegnati ai cluster: {documents_assigned}",
            f"Documenti rumore: {noise_documents}",
            f"Trend — new: {trend_counts['new']}, rising: {trend_counts['rising']}, "
            f"stable: {trend_counts['stable']}, falling: {trend_counts['falling']}",
            f"Durata totale: {duration_seconds:.2f}s",
        ]
    )


def main() -> int:
    started_at = perf_counter()
    try:
        application = build_application(Settings())
    except (TypeError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Application setup error: {error}", file=sys.stderr)
        return 1

    try:
        problem_count = count_available_problems(application.source_item_repository)
        analysis_result = application.analysis_orchestrator.run()
    except SQLAlchemyError as error:
        print(f"Database error during analysis: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Analysis error: {error}", file=sys.stderr)
        return 1

    print(format_summary(problem_count, analysis_result, perf_counter() - started_at))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
