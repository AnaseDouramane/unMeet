from dataclasses import dataclass
from typing import Protocol


class MalformedClassifierOutputError(ValueError):
    """Raised when a classifier response cannot be parsed as the required JSON output."""


@dataclass(frozen=True)
class ProblemDetectionResult:
    is_problem: bool
    confidence: float
    reason: str
    classifier_name: str


class ProblemClassifier(Protocol):
    def classify(self, document_text: str) -> ProblemDetectionResult: ...
