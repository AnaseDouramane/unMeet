from __future__ import annotations

import math
from numbers import Real

from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.schemas import ProblemClassifier, ProblemDetectionResult


class ProblemDetectionService:
    def __init__(self, classifier: ProblemClassifier) -> None:
        self._classifier = classifier

    def detect(self, prepared_document: PreparedDocument) -> ProblemDetectionResult:
        document_text = prepared_document.document_text
        self._validate_document_text(document_text)
        return validate_problem_detection_result(self._classifier.classify(document_text))

    @staticmethod
    def _validate_document_text(document_text: str) -> None:
        if not isinstance(document_text, str):
            raise TypeError("document_text must be a string")
        if not document_text.strip():
            raise ValueError("document_text must not be empty")


def validate_problem_detection_result(result: ProblemDetectionResult) -> ProblemDetectionResult:
    if not isinstance(result, ProblemDetectionResult):
        raise TypeError("classifier must return a ProblemDetectionResult")
    if not isinstance(result.is_problem, bool):
        raise ValueError("is_problem must be a bool")
    if isinstance(result.confidence, bool) or not isinstance(result.confidence, Real):
        raise ValueError("confidence must be numeric")
    confidence = float(result.confidence)
    if not math.isfinite(confidence):
        raise ValueError("confidence must be finite")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(result.reason, str) or not result.reason.strip():
        raise ValueError("reason must not be empty")
    if not isinstance(result.classifier_name, str) or not result.classifier_name.strip():
        raise ValueError("classifier_name must not be empty")
    return result
