from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.problem_detection.qwen3 import Qwen3ProblemClassifier

EXAMPLES = [
    "Every sprint we waste hours manually writing release notes.",
    "I wish there were a simple tool to monitor all my SaaS subscriptions.",
    "OpenAI released a new coding model today.",
    "Here is a guide to deploy FastAPI with Docker.",
]


def main() -> int:
    classifier = Qwen3ProblemClassifier()

    for text in EXAMPLES:
        print(f"\nText: {text}")
        try:
            result = classifier.classify(text)
        except (ImportError, OSError) as error:
            print(f"Unable to load Qwen3 locally: {error}")
            print("Check the Transformers installation, network access, and available disk space.")
            return 1
        except ValueError as error:
            print(f"Qwen3 returned an invalid classification response: {error}")
            continue
        except Exception as error:
            print(f"Unexpected Qwen3 classification error: {error}")
            continue

        print(f"is_problem: {result.is_problem}")
        print(f"confidence: {result.confidence}")
        print(f"reason: {result.reason}")
        print(f"classifier_name: {result.classifier_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
