from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.analysis.orchestrator import AnalysisRunResult
from app.clustering.schemas import ClusterTrend
from app.services.multi_source_ingestion import MultiSourceIngestionResult, SourceIngestionError
from scripts import run_unmeet


class FakeIngestionService:
    def __init__(
        self,
        events: list[str],
        result: MultiSourceIngestionResult,
        error: Exception | None = None,
    ) -> None:
        self.events = events
        self.result = result
        self.error = error

    def run(self) -> MultiSourceIngestionResult:
        self.events.append("ingestion")
        if self.error is not None:
            raise self.error
        return self.result


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
    return ClusterTrend(cluster_id, None, f"cluster-{cluster_id}", 1, 0, 1, None, status, None)


def _ingestion_result(
    errors: tuple[SourceIngestionError, ...] = (), successful_source_count: int = 1
) -> MultiSourceIngestionResult:
    return MultiSourceIngestionResult(
        acquired_count=10,
        problem_count=4,
        non_problem_count=6,
        embedding_count=4,
        source_stats=(),
        errors=errors,
        successful_source_count=successful_source_count,
        failed_source_count=len(errors),
        is_success=not errors,
    )


def _application(
    events: list[str],
    ingestion_result: MultiSourceIngestionResult | None = None,
    ingestion_error: Exception | None = None,
    analysis_error: Exception | None = None,
    fail_fast: bool = True,
) -> run_unmeet.UnmeetApplication:
    return run_unmeet.UnmeetApplication(
        ingestion_service=FakeIngestionService(
            events,
            ingestion_result or _ingestion_result(),
            ingestion_error,
        ),
        analysis_orchestrator=FakeAnalysisOrchestrator(events, analysis_error),
        fail_fast=fail_fast,
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
    assert "new: 1, rising: 1, stable: 1, falling: 1" in output


def test_main_skips_analysis_after_fail_fast_source_error(monkeypatch, capsys) -> None:
    events: list[str] = []
    result = _ingestion_result((SourceIngestionError("reddit", "unavailable"),))
    monkeypatch.setattr(run_unmeet, "Settings", lambda: object())
    monkeypatch.setattr(
        run_unmeet,
        "build_application",
        lambda settings: _application(events, ingestion_result=result, fail_fast=True),
    )

    assert run_unmeet.main() == 1

    assert events == ["ingestion"]
    assert "Ingestion error for reddit: unavailable" in capsys.readouterr().err


def test_main_runs_analysis_once_after_partial_ingestion_when_policy_allows(monkeypatch) -> None:
    events: list[str] = []
    result = _ingestion_result(
        (SourceIngestionError("reddit", "unavailable"),), successful_source_count=1
    )
    monkeypatch.setattr(run_unmeet, "Settings", lambda: object())
    monkeypatch.setattr(
        run_unmeet,
        "build_application",
        lambda settings: _application(events, ingestion_result=result, fail_fast=False),
    )

    assert run_unmeet.main() == 0

    assert events == ["ingestion", "analysis"]


def test_main_skips_analysis_when_all_sources_fail(monkeypatch) -> None:
    events: list[str] = []
    result = _ingestion_result(
        (SourceIngestionError("hackernews", "unavailable"),), successful_source_count=0
    )
    monkeypatch.setattr(run_unmeet, "Settings", lambda: object())
    monkeypatch.setattr(
        run_unmeet,
        "build_application",
        lambda settings: _application(events, ingestion_result=result, fail_fast=False),
    )

    assert run_unmeet.main() == 1

    assert events == ["ingestion"]


def test_build_application_wires_multiple_connectors_with_factories(monkeypatch) -> None:
    connector = object()
    reddit_connector = object()
    preprocessing_service = object()
    embedding_service = type("EmbeddingService", (), {"model_name": "model-a"})()
    pipeline = object()
    clusterer = type(
        "Clusterer",
        (),
        {"min_cluster_size": 5, "min_samples": None, "metric": "euclidean"},
    )()
    multi_source_kwargs = {}

    monkeypatch.setattr(run_unmeet, "HackerNewsConnector", lambda limit: connector)
    monkeypatch.setattr(
        run_unmeet.RedditConnector,
        "from_settings",
        lambda settings: reddit_connector,
    )
    monkeypatch.setattr(run_unmeet, "PreprocessingService", lambda: preprocessing_service)
    monkeypatch.setattr(run_unmeet, "Qwen3ProblemClassifier", lambda: object())
    monkeypatch.setattr(run_unmeet, "ProblemDetectionService", lambda classifier: object())
    monkeypatch.setattr(run_unmeet, "EmbeddingService", lambda model_name: embedding_service)
    monkeypatch.setattr(run_unmeet, "SourceItemRepository", lambda: object())
    monkeypatch.setattr(run_unmeet, "Pipeline", lambda **kwargs: pipeline)
    monkeypatch.setattr(run_unmeet, "HDBSCANClusterer", lambda: clusterer)
    monkeypatch.setattr(run_unmeet, "ClusteringService", lambda repository, clusterer: object())
    monkeypatch.setattr(run_unmeet, "TopicLabelingService", lambda: object())
    monkeypatch.setattr(run_unmeet, "ClusterRepository", lambda: object())
    monkeypatch.setattr(run_unmeet, "ClusterMatchingService", lambda: object())
    monkeypatch.setattr(run_unmeet, "TrendDetectionService", lambda: object())
    monkeypatch.setattr(run_unmeet, "AnalysisOrchestrator", lambda **kwargs: object())
    monkeypatch.setattr(
        run_unmeet,
        "MultiSourceIngestionService",
        lambda **kwargs: multi_source_kwargs.update(kwargs) or object(),
    )
    settings = type(
        "Settings",
        (),
        {
            "embedding_model": "model-a",
            "enabled_sources": ("hackernews", "reddit"),
            "ingestion_fail_fast": False,
        },
    )()

    application = run_unmeet.build_application(settings)

    assert application.fail_fast is False
    assert multi_source_kwargs["pipeline"] is pipeline
    assert multi_source_kwargs["connectors"] == (connector, reddit_connector)
    assert multi_source_kwargs["fail_fast"] is False


@pytest.mark.parametrize(
    "sources",
    [
        ("hackernews", "hackernews"),
        ("hackernews", "HackerNews"),
        ("hackernews", " hackernews "),
    ],
)
def test_build_connectors_rejects_duplicate_sources_before_construction(monkeypatch, sources) -> None:
    def unexpected_connector(*args, **kwargs):
        raise AssertionError("connector construction must not be attempted")

    monkeypatch.setattr(run_unmeet, "HackerNewsConnector", unexpected_connector)
    settings = type("Settings", (), {"enabled_sources": sources})()

    with pytest.raises(ValueError, match="Duplicate ingestion source: hackernews"):
        run_unmeet._build_connectors(settings)


def test_build_connectors_normalizes_valid_hackernews_and_reddit_sources(monkeypatch) -> None:
    hackernews = object()
    reddit = object()
    monkeypatch.setattr(run_unmeet, "HackerNewsConnector", lambda limit: hackernews)
    monkeypatch.setattr(run_unmeet.RedditConnector, "from_settings", lambda settings: reddit)
    settings = type("Settings", (), {"enabled_sources": (" HackerNews ", "REDDIT")})()

    connectors = run_unmeet._build_connectors(settings)

    assert connectors == (hackernews, reddit)


def test_module_has_a_main_guard() -> None:
    source = Path(run_unmeet.__file__).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(main())" in source
