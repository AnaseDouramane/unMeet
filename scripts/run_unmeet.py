from __future__ import annotations

import sys
from collections import Counter
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
from app.problem_detection.qwen3 import Qwen3ProblemClassifier
from app.problem_detection.service import ProblemDetectionService
from app.services.pipeline import Pipeline, PipelineRunStats
from app.services.preprocessing import PreprocessingService


@dataclass(frozen=True)
class UnmeetApplication:
    pipeline: Pipeline
    analysis_orchestrator: AnalysisOrchestrator


def build_application(settings: Settings) -> UnmeetApplication:
    connector = HackerNewsConnector(limit=10)
    preprocessing_service = PreprocessingService()
    classifier = Qwen3ProblemClassifier()
    problem_detection_service = ProblemDetectionService(classifier)
    embedding_service = EmbeddingService(model_name=settings.embedding_model)
    source_item_repository = SourceItemRepository()
    pipeline = Pipeline(
        settings=settings,
        connector=connector,
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
    return UnmeetApplication(pipeline=pipeline, analysis_orchestrator=analysis_orchestrator)


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
        application.pipeline.run()
    except SQLAlchemyError as error:
        print(f"Database error during ingestion: {error}", file=sys.stderr)
        return 1
    except (ImportError, OSError, RuntimeError) as error:
        print(f"Model or runtime error during ingestion: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Pipeline error: {error}", file=sys.stderr)
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

    stats = application.pipeline.last_run_stats
    if stats is None:
        print("Pipeline error: ingestion completed without run statistics", file=sys.stderr)
        return 1
    print(_format_summary(stats, analysis_result, perf_counter() - started_at))
    return 0


def _format_summary(stats: PipelineRunStats, analysis_result, duration_seconds: float) -> str:
    trend_counts = Counter(trend.status for trend in analysis_result.trend)
    return "\n".join(
        [
            "unMeet run complete",
            f"Posts acquired: {stats.acquired_count}",
            f"Problems identified: {stats.problem_count}",
            f"Non-problem posts archived: {stats.non_problem_count}",
            f"Documents with embeddings: {stats.embedding_count}",
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
