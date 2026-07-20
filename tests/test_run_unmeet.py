from datetime import datetime, timezone
from pathlib import Path

from app.analysis.orchestrator import AnalysisRunResult
from app.clustering.schemas import ClusterTrend
from app.services.pipeline import PipelineRunStats
from scripts import run_unmeet


class FakePipeline:
    def __init__(self, events: list[str], error: Exception | None = None) -> None:
        self.events = events
        self.error = error
        self.last_run_stats = PipelineRunStats(10, 4, 6, 4)

    def run(self) -> None:
        self.events.append("ingestion")
        if self.error is not None:
            raise self.error


class FakeAnalysisOrchestrator:
    def __init__(self, events: list[str], error: Exception | None = None) -> None:
        self.events = events
        self.error = error

    def run(self) -> AnalysisRunResult:
        self.events.append("analysis")
        if self.error is not None:
            raise self.error
        return AnalysisRunResult(
            run_id=17,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            cluster_count=3,
            document_count=4,
            clusters=(),
            matching=(),
            trend=(
                _trend(1, "new"),
                _trend(2, "rising"),
                _trend(3, "stable"),
                _trend(4, "falling"),
            ),
        )


def _trend(cluster_id: int, status: str) -> ClusterTrend:
    return ClusterTrend(
        current_cluster_id=cluster_id,
        previous_cluster_id=None,
        label=f"cluster-{cluster_id}",
        current_count=1,
        previous_count=0,
        absolute_change=1,
        growth_rate=None,
        status=status,
        similarity=None,
    )


def _application(events: list[str], pipeline_error=None, analysis_error=None):
    return run_unmeet.UnmeetApplication(
        pipeline=FakePipeline(events, pipeline_error),
        analysis_orchestrator=FakeAnalysisOrchestrator(events, analysis_error),
    )


def test_main_runs_ingestion_before_analysis_and_prints_summary(monkeypatch, capsys) -> None:
    events: list[str] = []
    monkeypatch.setattr(run_unmeet, "Settings", lambda: object())
    monkeypatch.setattr(run_unmeet, "build_application", lambda settings: _application(events))

    assert run_unmeet.main() == 0

    assert events == ["ingestion", "analysis"]
    output = capsys.readouterr().out
    assert "Posts acquired: 10" in output
    assert "Problems identified: 4" in output
    assert "Non-problem posts archived: 6" in output
    assert "Documents with embeddings: 4" in output
    assert "Analysis run ID: 17" in output
    assert "Clusters: 3" in output
    assert "Documents clustered: 4" in output
    assert "new: 1, rising: 1, stable: 1, falling: 1" in output
    assert "Total duration:" in output


def test_build_application_wires_explicit_dependencies_with_factories(monkeypatch) -> None:
    connector = object()
    preprocessing_service = object()
    classifier = object()
    problem_detection_service = object()
    embedding_service = type("EmbeddingService", (), {"model_name": "model-a"})()
    source_item_repository = object()
    pipeline = object()
    clusterer = type(
        "Clusterer",
        (),
        {"min_cluster_size": 5, "min_samples": None, "metric": "euclidean"},
    )()
    clustering_service = object()
    topic_labeling_service = object()
    cluster_repository = object()
    matching_service = object()
    trend_service = object()
    analysis_orchestrator = object()
    pipeline_kwargs = {}
    analysis_kwargs = {}

    monkeypatch.setattr(run_unmeet, "HackerNewsConnector", lambda limit: connector)
    monkeypatch.setattr(run_unmeet, "PreprocessingService", lambda: preprocessing_service)
    monkeypatch.setattr(run_unmeet, "Qwen3ProblemClassifier", lambda: classifier)
    monkeypatch.setattr(
        run_unmeet,
        "ProblemDetectionService",
        lambda received_classifier: problem_detection_service,
    )
    monkeypatch.setattr(
        run_unmeet,
        "EmbeddingService",
        lambda model_name: embedding_service,
    )
    monkeypatch.setattr(run_unmeet, "SourceItemRepository", lambda: source_item_repository)
    monkeypatch.setattr(
        run_unmeet,
        "Pipeline",
        lambda **kwargs: pipeline_kwargs.update(kwargs) or pipeline,
    )
    monkeypatch.setattr(run_unmeet, "HDBSCANClusterer", lambda: clusterer)
    monkeypatch.setattr(
        run_unmeet,
        "ClusteringService",
        lambda repository, received_clusterer: clustering_service,
    )
    monkeypatch.setattr(run_unmeet, "TopicLabelingService", lambda: topic_labeling_service)
    monkeypatch.setattr(run_unmeet, "ClusterRepository", lambda: cluster_repository)
    monkeypatch.setattr(run_unmeet, "ClusterMatchingService", lambda: matching_service)
    monkeypatch.setattr(run_unmeet, "TrendDetectionService", lambda: trend_service)
    monkeypatch.setattr(
        run_unmeet,
        "AnalysisOrchestrator",
        lambda **kwargs: analysis_kwargs.update(kwargs) or analysis_orchestrator,
    )
    settings = type("Settings", (), {"embedding_model": "model-a"})()

    application = run_unmeet.build_application(settings)

    assert application.pipeline is pipeline
    assert application.analysis_orchestrator is analysis_orchestrator
    assert pipeline_kwargs == {
        "settings": settings,
        "connector": connector,
        "preprocessing_service": preprocessing_service,
        "repository": source_item_repository,
        "embedding_service": embedding_service,
        "problem_detection_service": problem_detection_service,
    }
    assert analysis_kwargs["clustering_service"] is clustering_service
    assert analysis_kwargs["topic_labeling_service"] is topic_labeling_service
    assert analysis_kwargs["cluster_repository"] is cluster_repository
    assert analysis_kwargs["cluster_matching_service"] is matching_service
    assert analysis_kwargs["trend_detection_service"] is trend_service
    assert analysis_kwargs["metadata"].embedding_model == "model-a"


def test_main_does_not_start_analysis_when_ingestion_fails(monkeypatch, capsys) -> None:
    events: list[str] = []
    monkeypatch.setattr(run_unmeet, "Settings", lambda: object())
    monkeypatch.setattr(
        run_unmeet,
        "build_application",
        lambda settings: _application(events, pipeline_error=ValueError("ingestion failed")),
    )

    assert run_unmeet.main() == 1

    assert events == ["ingestion"]
    assert "Pipeline error: ingestion failed" in capsys.readouterr().err


def test_main_returns_non_zero_when_analysis_fails(monkeypatch, capsys) -> None:
    events: list[str] = []
    monkeypatch.setattr(run_unmeet, "Settings", lambda: object())
    monkeypatch.setattr(
        run_unmeet,
        "build_application",
        lambda settings: _application(events, analysis_error=ValueError("analysis failed")),
    )

    assert run_unmeet.main() == 1

    assert events == ["ingestion", "analysis"]
    assert "Analysis error: analysis failed" in capsys.readouterr().err


def test_main_returns_non_zero_for_configuration_errors(monkeypatch, capsys) -> None:
    def invalid_settings():
        raise ValueError("bad config")

    monkeypatch.setattr(run_unmeet, "Settings", invalid_settings)

    assert run_unmeet.main() == 1

    assert "Configuration error: bad config" in capsys.readouterr().err


def test_module_has_a_main_guard() -> None:
    source = Path(run_unmeet.__file__).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(main())" in source
