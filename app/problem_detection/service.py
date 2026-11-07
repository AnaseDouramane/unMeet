from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from numbers import Real

from app.preprocessing.schemas import PreparedDocument
from app.problem_detection.schemas import (
    SIGNAL_INTENTS,
    MalformedClassifierOutputError,
    ProblemClassifier,
    ProblemDetectionResult,
    TopicMatch,
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

    @property
    def supports_batching(self) -> bool:
        return callable(getattr(self._classifier, "classify_batch", None))

    @property
    def llm_request_count(self) -> int | None:
        """Requests the classifier sent to its provider, or None when it does not track them."""
        count = getattr(self._classifier, "request_count", None)
        return count if isinstance(count, int) else None

    def detect_batch_with_status(
        self, prepared_documents: Sequence[PreparedDocument]
    ) -> list[tuple[ProblemDetectionResult, bool]]:
        """Classify several documents with one request where the classifier supports it.

        Items the model skipped or answered invalidly are classified again one by one, so a
        flaky batch costs extra requests but never loses or mislabels a document. Without batch
        support this is a plain loop over :meth:`detect_with_status`. Thread-safe.
        """
        documents = list(prepared_documents)
        batch_classify = getattr(self._classifier, "classify_batch", None)
        if not callable(batch_classify) or len(documents) <= 1:
            return [self.detect_with_status(document) for document in documents]
        for document in documents:
            self._validate_document_text(document.document_text)
        outcomes = batch_classify([document.document_text for document in documents])
        if len(outcomes) != len(documents):
            outcomes = [MalformedClassifierOutputError("batch size mismatch")] * len(documents)
        results: list[tuple[ProblemDetectionResult, bool]] = []
        for document, outcome in zip(documents, outcomes, strict=True):
            if isinstance(outcome, MalformedClassifierOutputError):
                results.append(self.detect_with_status(document))
                continue
            try:
                results.append((validate_problem_detection_result(outcome), False))
            except (TypeError, ValueError):
                results.append(self.detect_with_status(document))
        return results

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
    if not isinstance(result.topic_matches, tuple) or any(
        not isinstance(match, TopicMatch)
        or isinstance(match.topic_id, bool)
        or not isinstance(match.topic_id, int)
        or not isinstance(match.reason, str)
        or not match.reason.strip()
        for match in result.topic_matches
    ):
        raise ValueError("topic_matches must be a tuple of TopicMatch with non-empty reasons")
    return result
