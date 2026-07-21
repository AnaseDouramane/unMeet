"""Run in Google Colab: classify exported JSONL on GPU with resumable output.

Example: python scripts/colab_classify_qwen.py input.jsonl --output results.jsonl
Copy the output to durable storage (for example Google Drive) between sessions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

from app.problem_detection.qwen3 import Qwen3ProblemClassifier
from app.problem_detection.classification_jsonl import parse_classification_json_line
from app.problem_detection.schemas import MalformedClassifierOutputError


def _read_jsonl(path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON at input line {line_number}") from error
        if set(record) != {"source", "external_id", "document_text"} or not all(
            isinstance(record[field], str) and record[field].strip() for field in record
        ):
            raise ValueError(f"Invalid record at input line {line_number}")
        records.append(record)
    return records


def _completed_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    completed: set[tuple[str, str]] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"Unable to read existing output: {error}") from error
    for line_number, line in enumerate(lines, start=1):
        record = parse_classification_json_line(line, line_number)
        if record.key in completed:
            raise ValueError(
                "Duplicate record in existing output at line "
                f"{line_number}: source='{record.source}', external_id='{record.external_id}'"
            )
        completed.add(record.key)
    return completed


def classify_file(input_path: Path, output_path: Path, classifier: Qwen3ProblemClassifier) -> int:
    records = _read_jsonl(input_path)
    completed = _completed_keys(output_path)
    pending = [item for item in records if (item["source"], item["external_id"]) not in completed]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    with output_path.open("a", encoding="utf-8", newline="\n") as output_file:
        for index, item in enumerate(pending, start=1):
            try:
                result = classifier.classify(item["document_text"])
                payload = {
                    "source": item["source"], "external_id": item["external_id"],
                    "is_problem": result.is_problem, "confidence": result.confidence,
                    "reason": result.reason, "classifier_name": result.classifier_name,
                }
            except (MalformedClassifierOutputError, ValueError):
                # A valid conservative record makes resume deterministic and preserves progress.
                payload = {
                    "source": item["source"], "external_id": item["external_id"],
                    "is_problem": False, "confidence": 0.0,
                    "reason": "Invalid classifier output", "classifier_name": classifier.classifier_name,
                }
            output_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            output_file.flush()
            elapsed = perf_counter() - started
            rate = index / elapsed if elapsed else 0.0
            eta = (len(pending) - index) / rate if rate else 0.0
            print(f"{index}/{len(pending)} | {rate:.2f} doc/s | ETA {eta:.0f}s", flush=True)
    return len(pending)


def main() -> int:
    parser = argparse.ArgumentParser(description="Colab GPU batch classifier for Qwen3-0.6B")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        classifier = Qwen3ProblemClassifier(device="cuda")
        count = classify_file(args.input_path, args.output, classifier)
    except Exception as error:
        print(f"Classification failed: {error}", file=sys.stderr)
        return 1
    print(f"Classified: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
