from __future__ import annotations

import logging
import math
from numbers import Real

from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.schemas import (
    SIGNAL_INTENTS,
    MalformedClassifierOutputError,
    ProblemClassifier,
    ProblemDetectionResult,
)

logger = logging.getLogger(__name__)


class ProblemDetectionService:
    def __init__(self, classifier: ProblemClassifier) -> None:
        self._classifier = classifier
        self.last_detection_was_malformed_output = False

    def detect(self, prepared_document: PreparedDocument) -> ProblemDetectionResult:
        result, malformed = self.detect_with_status(prepared_document)
        self.last_detection_was_malformed_output = malformed
        return result

    def detect_with_status(
        self, prepared_document: PreparedDocument
    ) -> tuple[ProblemDetectionResult, bool]:
        """Classify a document and report whether the output was malformed.

        Unlike :meth:`detect` this keeps no per-call state, so it is safe to call from
        several threads at once.
        """
        document_text = prepared_document.document_text
        self._validate_document_text(document_text)
        try:
            return (
                validate_problem_detection_result(self._classifier.classify(document_text)),
                False,
            )
        except MalformedClassifierOutputError:
            source_item = prepared_document.source_item
            logger.warning(
                "Malformed classifier output for %s:%s; treating document as non-problem",
                source_item.source,
                source_item.external_id,
            )
            return (
                ProblemDetectionResult(
                    is_problem=False,
                    confidence=0.0,
                    reason="Malformed classifier output",
                    classifier_name=self._classifier_name(),
                ),
                True,
            )

    def _classifier_name(self) -> str:
        classifier_name = getattr(self._classifier, "classifier_name", None)
        if isinstance(classifier_name, str) and classifier_name.strip():
            return classifier_name.strip()
        return type(self._classifier).__name__

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
    if result.intent is not None and result.intent not in SIGNAL_INTENTS:
        raise ValueError(f"intent must be one of {sorted(SIGNAL_INTENTS)}")
    if result.pain_quote is not None and (
        not isinstance(result.pain_quote, str) or not result.pain_quote.strip()
    ):
        raise ValueError("pain_quote must be a non-empty string when present")
    if not isinstance(result.products_mentioned, tuple) or any(
        not isinstance(product, str) or not product.strip()
        for product in result.products_mentioned
    ):
        raise ValueError("products_mentioned must be a tuple of non-empty strings")
    if result.severity is not None and (
        isinstance(result.severity, bool)
        or not isinstance(result.severity, int)
        or not 1 <= result.severity <= 3
    ):
        raise ValueError("severity must be an integer between 1 and 3")
    return result
