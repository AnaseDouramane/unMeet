import inspect
from datetime import datetime, timezone

import pytest

from app.ingestion.schemas import SourceItem
from app.problem_detection.schemas import MalformedClassifierOutputError, ProblemDetectionResult
from app.problem_detection.service import ProblemDetectionService
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


class FakeBatchConnector:
    def __init__(self, count: int) -> None:
        self.count = count

    def fetch(self):
        yield from (_source_item(index) for index in range(self.count))


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


class BatchClassifier:
    classifier_name = "Qwen3ProblemClassifier:batch-test"

    def __init__(self, malformed_index: int) -> None:
        self.malformed_index = malformed_index
        self.calls = 0

    def classify(self, document_text: str) -> ProblemDetectionResult:
        current_index = self.calls
        self.calls += 1
        if current_index == self.malformed_index:
            raise MalformedClassifierOutputError("classifier output contains malformed JSON")
        return _result(True)


class FailingInfrastructureClassifier:
    classifier_name = "Qwen3ProblemClassifier:batch-test"

    def classify(self, document_text: str) -> ProblemDetectionResult:
        raise RuntimeError("model generation failed")


class SemanticInvalidOutputClassifier:
    classifier_name = "Qwen3ProblemClassifier:batch-test"

    def __init__(self) -> None:
        self.calls = 0

    def classify(self, document_text: str) -> ProblemDetectionResult:
        self.calls += 1
        if self.calls == 1:
            raise MalformedClassifierOutputError(
                "classifier output does not conform to the required contract: "
                "classifier output confidence must be numeric"
            )
        return _result(True)


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
    assert pipeline.last_run_stats.classification_error_count == 0


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
    assert pipeline.last_run_stats.classification_error_count == 0


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


def test_pipeline_persists_all_100_documents_when_one_classifier_output_is_malformed() -> None:
    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    classifier = BatchClassifier(malformed_index=37)
    pipeline = Pipeline(
        settings=type("SettingsStub", (), {"environment": "test"})(),
        connector=FakeBatchConnector(100),
        preprocessing_service=PreprocessingService(),
        repository=repository,
        embedding_service=embedding_service,
        problem_detection_service=ProblemDetectionService(classifier),
    )

    accepted_documents = pipeline.run()

    assert len(accepted_documents) == 99
    assert len(repository.saved) == 100
    assert [saved[0].external_id for saved in repository.saved] == [
        str(index) for index in range(100)
    ]
    malformed_saved = repository.saved[37]
    assert malformed_saved[2] is None
    assert malformed_saved[3] is None
    assert malformed_saved[4] == ProblemDetectionResult(
        False,
        0.0,
        "Malformed classifier output",
        "Qwen3ProblemClassifier:batch-test",
    )
    assert len(embedding_service.calls) == 99
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.acquired_count == 100
    assert pipeline.last_run_stats.problem_count == 99
    assert pipeline.last_run_stats.non_problem_count == 1
    assert pipeline.last_run_stats.embedding_count == 99
    assert pipeline.last_run_stats.classification_error_count == 1


def test_pipeline_propagates_classifier_infrastructure_errors() -> None:
    pipeline = Pipeline(
        settings=type("SettingsStub", (), {"environment": "test"})(),
        connector=FakeBatchConnector(2),
        preprocessing_service=PreprocessingService(),
        repository=FakeRepository(),
        embedding_service=FakeEmbeddingService(),
        problem_detection_service=ProblemDetectionService(FailingInfrastructureClassifier()),
    )

    with pytest.raises(RuntimeError, match="model generation failed"):
        pipeline.run()

    assert pipeline.last_run_stats is None


def test_pipeline_continues_after_a_semantically_invalid_output_then_valid_output() -> None:
    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    pipeline = Pipeline(
        settings=type("SettingsStub", (), {"environment": "test"})(),
        connector=FakeBatchConnector(2),
        preprocessing_service=PreprocessingService(),
        repository=repository,
        embedding_service=embedding_service,
        problem_detection_service=ProblemDetectionService(SemanticInvalidOutputClassifier()),
    )

    accepted_documents = pipeline.run()

    assert [document.source_item.external_id for document in accepted_documents] == ["1"]
    assert len(repository.saved) == 2
    assert repository.saved[0][4] == ProblemDetectionResult(
        False,
        0.0,
        "Malformed classifier output",
        "Qwen3ProblemClassifier:batch-test",
    )
    assert repository.saved[0][2] is None
    assert repository.saved[0][3] is None
    assert repository.saved[1][2] == [1.0] * 384
    assert embedding_service.calls == [accepted_documents[0].document_text]
    assert pipeline.last_run_stats is not None
    assert pipeline.last_run_stats.classification_error_count == 1
