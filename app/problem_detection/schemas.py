from dataclasses import dataclass, field
from typing import Literal, Protocol

SignalIntent = Literal[
    "pain_point",
    "feature_request",
    "solution_search",
    "competitor_complaint",
    "none",
]
SIGNAL_INTENTS: frozenset[str] = frozenset(
    {"pain_point", "feature_request", "solution_search", "competitor_complaint", "none"}
)


class MalformedClassifierOutputError(ValueError):
    """Raised when a classifier response cannot be parsed as the required JSON output."""


@dataclass(frozen=True)
class ProblemDetectionResult:
    """Classification of one document.

    The first four fields are produced by every classifier. The signal fields are optional and
    filled by classifiers that extract actionable details for go-to-market users:

    - ``intent``: what the author is doing (complaining, asking for a feature, shopping for a
      solution, criticising a named product);
    - ``pain_quote``: the shortest verbatim excerpt of the document that states the pain;
    - ``products_mentioned``: product or company names the author mentions;
    - ``severity``: 1 (minor annoyance) to 3 (blocking or costly).
    """

    is_problem: bool
    confidence: float
    reason: str
    classifier_name: str
    intent: SignalIntent | None = None
    pain_quote: str | None = None
    products_mentioned: tuple[str, ...] = field(default_factory=tuple)
    severity: int | None = None


class ProblemClassifier(Protocol):
    def classify(self, document_text: str) -> ProblemDetectionResult: ...
