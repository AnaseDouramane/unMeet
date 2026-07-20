import inspect
from datetime import datetime, timezone

import pytest

from app.ingestion.schemas import SourceItem
from app.problem_detection.schemas import ProblemDetectionResult
from app.services.pipeline import Pipeline
from app.services.preprocessing import PreprocessingService


class FakeHackerNewsConnector:
    def __init__(self, limit: int = 10) -> None:
        self.limit = limit
        self.fetch_calls = 0

    def fetch(self):
        self.fetch_calls += 1
        for index in range(10):
            yield _source_item(index)


class FakeMixedConnector:
    def __init__(self, limit: int = 10) -> None:
        self.limit = limit

    def fetch(self):
        yield from (_source_item(index) for index in range(3))


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.model_name = "fake-embedding-model"
        self.calls: list[str] = []

    def encode(self, document_text: str) -> list[float]:
        self.calls.append(document_text)
        embedding_value = float(len(self.calls))
        return [embedding_value] * 384


class FakeProblemDetectionService:
    def __init__(self, results: list[ProblemDetectionResult]) -> None:
        self.results = results
        self.calls: list[str] = []

    def detect(self, prepared_document) -> ProblemDetectionResult:
        self.calls.append(prepared_document.document_text)
        return self.results[len(self.calls) - 1]


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[SourceItem, object, list[float] | None, str | None, object]] = []

    def save(
        self,
        source_item,
        prepared_document,
        embedding=None,
        embedding_model=None,
        problem_detection_result=None,
    ):
        self.saved.append(
            (source_item, prepared_document, embedding, embedding_model, problem_detection_result)
        )
        return prepared_document


def _source_item(index: int) -> SourceItem:
    return SourceItem(
        external_id=str(index),
        source="hackernews",
        title=f"<h1>Title {index}</h1>",
        body=f"<p>Body {index}</p>",
        url=f"https://example.com/{index}",
        author="alice",
        published_at=datetime.fromtimestamp(1_700_000_000 + index, tz=timezone.utc),
        engagement_score=index,
        raw_payload={"id": index, "type": "story"},
    )


def _result(is_problem: bool) -> ProblemDetectionResult:
    return ProblemDetectionResult(
        is_problem=is_problem,
        confidence=0.9,
        reason="deterministic test classification",
        classifier_name="fake-problem-classifier",
    )


def test_pipeline_requires_injected_operational_dependencies() -> None:
    with pytest.raises(TypeError):
        Pipeline(settings=type("SettingsStub", (), {"environment": "test"})())

    source = inspect.getsource(Pipeline.__init__)
    assert "HackerNewsConnector(" not in source
    assert "PreprocessingService(" not in source
    assert "SourceItemRepository(" not in source
    assert "EmbeddingService(" not in source


def test_pipeline_returns_problem_documents_and_passes_embeddings() -> None:
    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    problem_detection_service = FakeProblemDetectionService([_result(True)] * 10)
    pipeline = Pipeline(
        settings=type("SettingsStub", (), {"environment": "test"})(),
        connector=FakeHackerNewsConnector(),
        preprocessing_service=PreprocessingService(),
        repository=repository,
        embedding_service=embedding_service,
        problem_detection_service=problem_detection_service,
    )
    prepared_documents = pipeline.run()

    assert len(prepared_documents) == 10
    assert len(repository.saved) == 10
    assert embedding_service.calls == [document.document_text for document in prepared_documents]
    assert [document.source_item.external_id for document in prepared_documents] == [
        str(index) for index in range(10)
    ]
    assert [saved[0].external_id for saved in repository.saved] == [
        str(index) for index in range(10)
    ]
    assert [saved[1].document_text for saved in repository.saved] == embedding_service.calls
    assert [saved[2] for saved in repository.saved] == [
        [float(index + 1)] * 384 for index in range(10)
    ]
    assert [saved[3] for saved in repository.saved] == ["fake-embedding-model"] * 10
    assert all(saved[4].is_problem is True for saved in repository.saved)
    assert prepared_documents[0].title == "Title 0"
    assert prepared_documents[0].body == "Body 0"
    assert prepared_documents[0].document_text == "Title 0\n\nBody 0"
    assert prepared_documents[0].source_item.title == "<h1>Title 0</h1>"
    assert prepared_documents[0].source_item.body == "<p>Body 0</p>"
    assert repository.saved[0][0].external_id == "0"
    assert repository.saved[0][1].dedup_hash == prepared_documents[0].dedup_hash
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.acquired_count == 10
    assert pipeline.last_run_stats.problem_count == 10
    assert pipeline.last_run_stats.non_problem_count == 0
    assert pipeline.last_run_stats.embedding_count == 10


def test_pipeline_persists_non_problems_without_embedding_and_preserves_problem_order() -> None:
    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    problem_detection_service = FakeProblemDetectionService(
        [_result(True), _result(False), _result(True)]
    )
    pipeline = Pipeline(
        settings=type("SettingsStub", (), {"environment": "test"})(),
        connector=FakeMixedConnector(),
        preprocessing_service=PreprocessingService(),
        repository=repository,
        embedding_service=embedding_service,
        problem_detection_service=problem_detection_service,
    )

    accepted_documents = pipeline.run()

    assert [document.source_item.external_id for document in accepted_documents] == ["0", "2"]
    assert len(repository.saved) == 3
    assert [saved[0].external_id for saved in repository.saved] == ["0", "1", "2"]
    assert embedding_service.calls == [
        accepted_documents[0].document_text,
        accepted_documents[1].document_text,
    ]
    assert repository.saved[1][2] is None
    assert repository.saved[1][3] is None
    assert repository.saved[1][4].is_problem is False
    assert [saved[4].is_problem for saved in repository.saved] == [True, False, True]
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.acquired_count == 3
    assert pipeline.last_run_stats.problem_count == 2
    assert pipeline.last_run_stats.non_problem_count == 1
    assert pipeline.last_run_stats.embedding_count == 2


def test_pipeline_clears_previous_run_statistics_when_a_later_run_fails() -> None:
    class FailingOnSecondFetchConnector:
        def __init__(self) -> None:
            self.calls = 0

        def fetch(self):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("connector failed")
            yield _source_item(1)

    pipeline = Pipeline(
        settings=type("SettingsStub", (), {"environment": "test"})(),
        connector=FailingOnSecondFetchConnector(),
        preprocessing_service=PreprocessingService(),
        repository=FakeRepository(),
        embedding_service=FakeEmbeddingService(),
        problem_detection_service=FakeProblemDetectionService([_result(True)]),
    )

    pipeline.run()
    assert pipeline.last_run_stats is not None

    with pytest.raises(RuntimeError, match="connector failed"):
        pipeline.run()

    assert pipeline.last_run_stats is None
