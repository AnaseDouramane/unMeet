from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError

from app.analysis.orchestrator import AnalysisRunResult
from app.clustering.schemas import ClusterTrend
from app.config import Settings
from scripts import run_analysis


@dataclass
class FakeRepository:
    counts: tuple[tuple[str, int], ...]
    error: Exception | None = None

    def count_problems_by_source(self) -> tuple[tuple[str, int], ...]:
        if self.error is not None:
            raise self.error
        return self.counts


class FakeOrchestrator:
    def __init__(self, result: AnalysisRunResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def run(self) -> AnalysisRunResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _result(
    document_count: int = 3,
    trends: tuple[ClusterTrend, ...] = (),
) -> AnalysisRunResult:
    return AnalysisRunResult(
        run_id=42,
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        cluster_count=0,
        document_count=document_count,
        clusters=(),
        matching=(),
        trend=trends,
    )


def test_main_runs_the_orchestrator_once_and_prints_analysis_summary(monkeypatch, capsys) -> None:
    trends = (
        ClusterTrend(1, None, "new", 2, 0, 2, None, "new", None),
        ClusterTrend(2, 9, "stable", 1, 1, 0, 0.0, "stable", 0.9),
    )
    orchestrator = FakeOrchestrator(_result(trends=trends))
    application = run_analysis.AnalysisApplication(FakeRepository((("reddit", 4),)), orchestrator)
    monkeypatch.setattr(run_analysis, "build_application", lambda settings: application)
    monkeypatch.setattr(run_analysis, "perf_counter", lambda: 10.0)

    assert run_analysis.main() == 0

    assert orchestrator.calls == 1
    output = capsys.readouterr().out
    assert "Problemi disponibili: 4" in output
    assert "Documenti con embedding: 3" in output
    assert "Run ID: 42" in output
    assert "Cluster creati: 0" in output
    assert "Documenti assegnati ai cluster: 0" in output
    assert "Documenti rumore: 3" in output
    assert "new: 1, rising: 0, stable: 1, falling: 0" in output
    assert "Durata totale: 0.00s" in output


def test_summary_handles_no_documents_and_all_noise() -> None:
    no_documents = run_analysis.format_summary(0, _result(document_count=0), 1.25)
    all_noise = run_analysis.format_summary(5, _result(document_count=5), 1.25)

    assert "Documenti con embedding: 0" in no_documents
    assert "Documenti rumore: 0" in no_documents
    assert "Documenti con embedding: 5" in all_noise
    assert "Documenti rumore: 5" in all_noise


def test_main_reports_database_errors(monkeypatch, capsys) -> None:
    database_error = OperationalError("SELECT", {}, Exception("database unavailable"))
    application = run_analysis.AnalysisApplication(FakeRepository((), database_error), FakeOrchestrator())
    monkeypatch.setattr(run_analysis, "build_application", lambda settings: application)

    assert run_analysis.main() == 1

    assert "Database error during analysis" in capsys.readouterr().err


def test_main_reports_analysis_errors(monkeypatch, capsys) -> None:
    application = run_analysis.AnalysisApplication(
        FakeRepository((("hackernews", 2),)),
        FakeOrchestrator(error=ValueError("invalid cluster")),
    )
    monkeypatch.setattr(run_analysis, "build_application", lambda settings: application)

    assert run_analysis.main() == 1

    assert "Analysis error: invalid cluster" in capsys.readouterr().err


def test_build_application_uses_settings_embedding_model(monkeypatch) -> None:
    captured = {}

    class FakeOrchestratorConstructor:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(run_analysis, "SourceItemRepository", lambda: object())
    monkeypatch.setattr(run_analysis, "ClusteringService", lambda repository, clusterer: object())
    monkeypatch.setattr(run_analysis, "TopicLabelingService", lambda: object())
    monkeypatch.setattr(run_analysis, "ClusterRepository", lambda: object())
    monkeypatch.setattr(run_analysis, "ClusterMatchingService", lambda: object())
    monkeypatch.setattr(run_analysis, "TrendDetectionService", lambda: object())
    monkeypatch.setattr(run_analysis, "AnalysisOrchestrator", FakeOrchestratorConstructor)

    application = run_analysis.build_application(Settings(embedding_model="offline-model"))

    assert application.source_item_repository is not None
    assert captured["metadata"].embedding_model == "offline-model"
