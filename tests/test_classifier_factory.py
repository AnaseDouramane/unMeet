from dataclasses import replace

import pytest

from app.config import settings
from app.problem_detection.factory import build_problem_classifier
from app.problem_detection.llm import OpenAICompatibleSignalClassifier
from app.problem_detection.qwen3 import Qwen3ProblemClassifier


def test_qwen3_backend_builds_the_local_classifier() -> None:
    classifier = build_problem_classifier(replace(settings, classifier_backend="qwen3"))

    assert isinstance(classifier, Qwen3ProblemClassifier)


def test_llm_backend_builds_a_configured_api_classifier() -> None:
    configured = replace(
        settings,
        classifier_backend="llm",
        llm_model="llama-3.3-70b-versatile",
        llm_base_url="https://llm.example/v1",
        llm_api_key="secret",
        llm_use_json_schema=False,
    )

    classifier = build_problem_classifier(configured)

    assert isinstance(classifier, OpenAICompatibleSignalClassifier)
    assert classifier.model == "llama-3.3-70b-versatile"
    assert classifier.base_url == "https://llm.example/v1"
    assert classifier.use_json_schema is False


def test_llm_backend_requires_a_model() -> None:
    with pytest.raises(ValueError, match="LLM_MODEL"):
        build_problem_classifier(replace(settings, classifier_backend="llm", llm_model=None))


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="CLASSIFIER_BACKEND"):
        build_problem_classifier(replace(settings, classifier_backend="magic"))
