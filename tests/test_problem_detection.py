from datetime import datetime, timezone

import pytest

from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.schemas import MalformedClassifierOutputError, ProblemDetectionResult
from app.problem_detection.service import ProblemDetectionService


class FakeProblemClassifier:
    def __init__(self, result: ProblemDetectionResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def classify(self, document_text: str) -> ProblemDetectionResult:
        self.calls.append(document_text)
        return self.result


class SequencedProblemClassifier:
    classifier_name = "Qwen3ProblemClassifier:test-model"

    def __init__(self, results: list[ProblemDetectionResult | Exception]) -> None:
        self.results = results
        self.calls: list[str] = []

    def classify(self, document_text: str) -> ProblemDetectionResult:
        self.calls.append(document_text)
        result = self.results[len(self.calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result


def _prepared_document(
    document_text: str = "I need help with a failing deployment",
) -> PreparedDocument:
    source_item = SourceItem(
        external_id="1",
        source="test",
        title="Title",
        body="Body",
        url="https://example.com/1",
        author=None,
        published_at=datetime.now(timezone.utc),
        engagement_score=None,
        raw_payload={},
    )
    return PreparedDocument(
        source_item=source_item,
        title="Title",
        body="Body",
        document_text=document_text,
        dedup_hash="hash",
    )


def test_detect_uses_the_prepared_document_text_and_returns_the_classifier_result() -> None:
    result = ProblemDetectionResult(True, 0.9, "Explicit need", "deterministic-fake")
    classifier = FakeProblemClassifier(result)

    detected = ProblemDetectionService(classifier).detect(_prepared_document())

    assert detected == result
    assert classifier.calls == ["I need help with a failing deployment"]


@pytest.mark.parametrize(
    "result, error",
    [
        (ProblemDetectionResult("yes", 0.9, "reason", "fake"), "is_problem"),
        (ProblemDetectionResult(True, float("nan"), "reason", "fake"), "finite"),
        (ProblemDetectionResult(True, float("inf"), "reason", "fake"), "finite"),
        (ProblemDetectionResult(True, -0.1, "reason", "fake"), "between 0 and 1"),
        (ProblemDetectionResult(True, 1.1, "reason", "fake"), "between 0 and 1"),
        (ProblemDetectionResult(True, 0.9, "   ", "fake"), "reason"),
        (ProblemDetectionResult(True, 0.9, "reason", "   "), "classifier_name"),
    ],
)
def test_detect_rejects_invalid_classifier_results(
    result: ProblemDetectionResult, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        ProblemDetectionService(FakeProblemClassifier(result)).detect(_prepared_document())


def test_detect_rejects_an_empty_document_before_calling_the_classifier() -> None:
    classifier = FakeProblemClassifier(ProblemDetectionResult(True, 0.9, "reason", "fake"))

    with pytest.raises(ValueError, match="document_text"):
        ProblemDetectionService(classifier).detect(_prepared_document("   "))

    assert classifier.calls == []


def test_detect_turns_malformed_classifier_output_into_a_negative_result(caplog) -> None:
    classifier = SequencedProblemClassifier(
        [MalformedClassifierOutputError("classifier output contains malformed JSON")]
    )

    with caplog.at_level("WARNING"):
        result = ProblemDetectionService(classifier).detect(_prepared_document())

    assert result == ProblemDetectionResult(
        is_problem=False,
        confidence=0.0,
        reason="Malformed classifier output",
        classifier_name="Qwen3ProblemClassifier:test-model",
    )
    assert "Malformed classifier output for test:1" in caplog.text


def test_detect_continues_after_malformed_output_with_the_next_document() -> None:
    valid_result = ProblemDetectionResult(True, 0.8, "Explicit need", "Qwen3ProblemClassifier:test")
    classifier = SequencedProblemClassifier(
        [MalformedClassifierOutputError("classifier output contains malformed JSON"), valid_result]
    )
    service = ProblemDetectionService(classifier)

    malformed_result = service.detect(_prepared_document("First document"))
    next_result = service.detect(_prepared_document("Second document"))

    assert malformed_result.is_problem is False
    assert next_result == valid_result
    assert classifier.calls == ["First document", "Second document"]


def test_detect_handles_malformed_output_after_a_valid_document() -> None:
    valid_result = ProblemDetectionResult(True, 0.8, "Explicit need", "Qwen3ProblemClassifier:test")
    classifier = SequencedProblemClassifier(
        [valid_result, MalformedClassifierOutputError("classifier output contains malformed JSON")]
    )
    service = ProblemDetectionService(classifier)

    first_result = service.detect(_prepared_document("First document"))
    malformed_result = service.detect(_prepared_document("Second document"))

    assert first_result == valid_result
    assert malformed_result == ProblemDetectionResult(
        False,
        0.0,
        "Malformed classifier output",
        "Qwen3ProblemClassifier:test-model",
    )
    assert classifier.calls == ["First document", "Second document"]


def test_detect_propagates_classifier_infrastructure_errors() -> None:
    classifier = SequencedProblemClassifier([RuntimeError("model generation failed")])

    with pytest.raises(RuntimeError, match="model generation failed"):
        ProblemDetectionService(classifier).detect(_prepared_document())
