import sys
from pathlib import Path

import pytest

from app.problem_detection.schemas import ProblemDetectionResult
from scripts import evaluate_problem_classifier
from scripts.evaluate_problem_classifier import (
    EvaluationCase,
    evaluate,
    format_report,
    load_dataset,
)


class FakeClassifier:
    def __init__(self, predictions: dict[str, ProblemDetectionResult]) -> None:
        self.predictions = predictions

    def classify(self, document_text: str) -> ProblemDetectionResult:
        return self.predictions[document_text]


def _result(
    is_problem: bool, confidence: float = 0.8, reason: str = "test reason"
) -> ProblemDetectionResult:
    return ProblemDetectionResult(is_problem, confidence, reason, "FakeClassifier")


def test_load_dataset_loads_valid_jsonl(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"id":"case-001","text":"Need a tool","expected_is_problem":true,'
        '"category":"request_for_tool"}\n'
        '{"id":"case-002","text":"Product news","expected_is_problem":false,"category":"news"}\n',
        encoding="utf-8",
    )

    cases = load_dataset(dataset)

    assert cases == [
        EvaluationCase("case-001", "Need a tool", True, "request_for_tool"),
        EvaluationCase("case-002", "Product news", False, "news"),
    ]


@pytest.mark.parametrize(
    "content, error",
    [
        ("", "is empty"),
        ("not json\n", "Invalid JSON at line 1"),
        ('[]\n', "expected a JSON object"),
        ('{"id":"case-001"}\n', "expected exactly"),
        (
            '{"id":"case-001","text":"Text","expected_is_problem":"true","category":"news"}\n',
            "expected_is_problem must be a bool",
        ),
        (
            '{"id":"case-001","text":"Text","expected_is_problem":false,"category":"news"}\n'
            '{"id":"case-001","text":"Other","expected_is_problem":false,"category":"news"}\n',
            "duplicate id 'case-001'",
        ),
    ],
)
def test_load_dataset_rejects_malformed_records(tmp_path: Path, content: str, error: str) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        load_dataset(dataset)


def test_evaluate_calculates_confusion_matrix_metrics_and_error_reporting() -> None:
    cases = [
        EvaluationCase("tp", "true positive", True, "explicit_pain_point"),
        EvaluationCase("tn", "true negative", False, "news"),
        EvaluationCase("fp", "false positive", False, "tutorial"),
        EvaluationCase("fn", "false negative", True, "manual_workflow"),
    ]
    classifier = FakeClassifier(
        {
            "true positive": _result(True),
            "true negative": _result(False),
            "false positive": _result(True, 0.73, "Misread tutorial as pain"),
            "false negative": _result(False, 0.61, "Missed manual work"),
        }
    )

    report = evaluate(cases, classifier)

    assert report.true_positives == 1
    assert report.true_negatives == 1
    assert report.false_positives == 1
    assert report.false_negatives == 1
    assert report.accuracy == pytest.approx(0.5)
    assert report.precision == pytest.approx(0.5)
    assert report.recall == pytest.approx(0.5)
    assert report.f1_score == pytest.approx(0.5)
    assert [error.case.id for error in report.errors] == ["fp", "fn"]

    rendered = format_report(report)
    assert "TP: 1  TN: 1  FP: 1  FN: 1" in rendered
    assert "id: fp" in rendered
    assert "category: tutorial" in rendered
    assert "text: false positive" in rendered
    assert "expected: False" in rendered
    assert "predicted: True" in rendered
    assert "confidence: 0.73" in rendered
    assert "reason: Misread tutorial as pain" in rendered


def test_evaluate_handles_zero_division_metrics() -> None:
    cases = [EvaluationCase("tn", "news", False, "news")]

    report = evaluate(cases, FakeClassifier({"news": _result(False)}))

    assert report.accuracy == 1.0
    assert report.precision == 0.0
    assert report.recall == 0.0
    assert report.f1_score == 0.0
    assert report.errors == ()
    assert "Errors:\n  None" in format_report(report)


def test_main_runs_evaluation_and_reports_progress_without_loading_qwen(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"id":"case-001","text":"Need a tool","expected_is_problem":true,'
        '"category":"request_for_tool"}\n'
        '{"id":"case-002","text":"Product news","expected_is_problem":false,"category":"news"}\n',
        encoding="utf-8",
    )
    fake_classifier = FakeClassifier(
        {"Need a tool": _result(True), "Product news": _result(False)}
    )
    fake_classifier.device_name = "cuda"
    monkeypatch.setattr(evaluate_problem_classifier, "Qwen3ProblemClassifier", lambda: fake_classifier)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_problem_classifier", "--dataset", str(dataset)],
    )

    assert evaluate_problem_classifier.main() == 0

    output = capsys.readouterr().out
    assert "Loaded cases: 2" in output
    assert "Selected device: cuda" in output
    assert "Evaluating 1/2: case-001" in output
    assert "Evaluating 2/2: case-002" in output
    assert "Accuracy: 1.000" in output


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ImportError("No module named 'torch'"), "Unable to import a required dependency"),
        (RuntimeError("CUDA was requested but is not available"), "Unable to select a device"),
    ],
)
def test_evaluation_entry_point_handles_dependency_and_device_errors(
    monkeypatch, tmp_path: Path, capsys, error, message
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"id":"case-001","text":"Product news","expected_is_problem":false,"category":"news"}\n',
        encoding="utf-8",
    )

    class FailingDeviceClassifier:
        @property
        def device_name(self) -> str:
            raise error

    monkeypatch.setattr(
        evaluate_problem_classifier,
        "Qwen3ProblemClassifier",
        FailingDeviceClassifier,
    )
    monkeypatch.setattr(sys, "argv", ["evaluate_problem_classifier", "--dataset", str(dataset)])

    assert evaluate_problem_classifier.main() == 1

    captured = capsys.readouterr()
    assert message in captured.err
    assert str(error) in captured.err
