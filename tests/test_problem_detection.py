from datetime import datetime, timezone

import pytest

from app.ingestion.schemas import SourceItem
from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.schemas import ProblemDetectionResult
from app.problem_detection.service import ProblemDetectionService


class FakeProblemClassifier:
    def __init__(self, result: ProblemDetectionResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def classify(self, document_text: str) -> ProblemDetectionResult:
        self.calls.append(document_text)
        return self.result


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
