from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.problem_detection.qwen3 import Qwen3ProblemClassifier
from app.problem_detection.schemas import ProblemClassifier, ProblemDetectionResult

DEFAULT_DATASET_PATH = PROJECT_ROOT / "tests" / "fixtures" / "problem_detection_eval.jsonl"


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    text: str
    expected_is_problem: bool
    category: str


@dataclass(frozen=True)
class EvaluationError:
    case: EvaluationCase
    result: ProblemDetectionResult


@dataclass(frozen=True)
class EvaluationReport:
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    errors: tuple[EvaluationError, ...]

    @property
    def total(self) -> int:
        return (
            self.true_positives + self.true_negatives + self.false_positives + self.false_negatives
        )

    @property
    def accuracy(self) -> float:
        return _safe_divide(self.true_positives + self.true_negatives, self.total)

    @property
    def precision(self) -> float:
        return _safe_divide(self.true_positives, self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        return _safe_divide(self.true_positives, self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        return _safe_divide(2 * self.precision * self.recall, self.precision + self.recall)


def load_dataset(path: Path) -> list[EvaluationCase]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"Unable to read evaluation dataset '{path}': {error}") from error

    if not lines:
        raise ValueError(f"Evaluation dataset '{path}' is empty")

    cases: list[EvaluationCase] = []
    case_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"Invalid dataset record at line {line_number}: empty line")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON at line {line_number}: {error.msg}") from error
        case = _parse_case(record, line_number)
        if case.id in case_ids:
            raise ValueError(
                f"Invalid dataset record at line {line_number}: duplicate id '{case.id}'"
            )
        case_ids.add(case.id)
        cases.append(case)
    return cases


def evaluate(
    cases: Iterable[EvaluationCase],
    classifier: ProblemClassifier,
    progress_callback: Callable[[int, int, EvaluationCase], None] | None = None,
) -> EvaluationReport:
    cases = list(cases)
    true_positives = true_negatives = false_positives = false_negatives = 0
    errors: list[EvaluationError] = []

    for current, case in enumerate(cases, start=1):
        if progress_callback is not None:
            progress_callback(current, len(cases), case)
        result = classifier.classify(case.text)
        if result.is_problem and case.expected_is_problem:
            true_positives += 1
        elif not result.is_problem and not case.expected_is_problem:
            true_negatives += 1
        elif result.is_problem:
            false_positives += 1
            errors.append(EvaluationError(case=case, result=result))
        else:
            false_negatives += 1
            errors.append(EvaluationError(case=case, result=result))

    return EvaluationReport(
        true_positives=true_positives,
        true_negatives=true_negatives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        errors=tuple(errors),
    )


def format_report(report: EvaluationReport) -> str:
    lines = [
        "Problem Detection evaluation",
        f"Cases: {report.total}",
        f"TP: {report.true_positives}  TN: {report.true_negatives}  "
        f"FP: {report.false_positives}  FN: {report.false_negatives}",
        f"Accuracy: {report.accuracy:.3f}",
        f"Precision: {report.precision:.3f}",
        f"Recall: {report.recall:.3f}",
        f"F1: {report.f1_score:.3f}",
        "Errors:",
    ]
    if not report.errors:
        lines.append("  None")
    for error in report.errors:
        case = error.case
        result = error.result
        lines.extend(
            [
                f"  id: {case.id}",
                f"  category: {case.category}",
                f"  text: {case.text}",
                f"  expected: {case.expected_is_problem}",
                f"  predicted: {result.is_problem}",
                f"  confidence: {result.confidence}",
                f"  reason: {result.reason}",
            ]
        )
    return "\n".join(lines)


def _parse_case(record: object, line_number: int) -> EvaluationCase:
    if not isinstance(record, dict):
        raise ValueError(f"Invalid dataset record at line {line_number}: expected a JSON object")

    required_fields = {"id", "text", "expected_is_problem", "category"}
    if set(record) != required_fields:
        raise ValueError(
            f"Invalid dataset record at line {line_number}: expected exactly "
            "id, text, expected_is_problem, category"
        )

    case_id = record["id"]
    text = record["text"]
    expected_is_problem = record["expected_is_problem"]
    category = record["category"]
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError(
            f"Invalid dataset record at line {line_number}: id must be a non-empty string"
        )
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            f"Invalid dataset record at line {line_number}: text must be a non-empty string"
        )
    if not isinstance(expected_is_problem, bool):
        raise ValueError(
            f"Invalid dataset record at line {line_number}: expected_is_problem must be a bool"
        )
    if not isinstance(category, str) or not category.strip():
        raise ValueError(
            f"Invalid dataset record at line {line_number}: category must be a non-empty string"
        )
    return EvaluationCase(
        id=case_id.strip(),
        text=text.strip(),
        expected_is_problem=expected_is_problem,
        category=category.strip(),
    )


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Qwen3 problem detection on a labeled JSONL dataset."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    args = parser.parse_args()

    try:
        cases = load_dataset(args.dataset)
    except ValueError as error:
        print(f"Dataset error: {error}", file=sys.stderr)
        return 2

    print(f"Loaded cases: {len(cases)}")
    try:
        classifier = Qwen3ProblemClassifier()
        print(f"Selected device: {classifier.device_name}")
        report = evaluate(
            cases,
            classifier,
            progress_callback=lambda current, total, case: print(
                f"Evaluating {current}/{total}: {case.id}"
            ),
        )
    except ImportError as error:
        print(
            f"Unable to import a required dependency (PyTorch or Transformers): {error}",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as error:
        print(f"Unable to select a device or initialize CUDA: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Unable to load Qwen3 locally: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Qwen3 returned an invalid classification response: {error}", file=sys.stderr)
        return 1

    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
