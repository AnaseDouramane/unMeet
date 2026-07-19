from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProblemDetectionResult:
    is_problem: bool
    confidence: float
    reason: str
    classifier_name: str


class ProblemClassifier(Protocol):
    def classify(self, document_text: str) -> ProblemDetectionResult: ...
