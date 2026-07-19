import sys
from types import SimpleNamespace

import pytest

from app.problem_detection.qwen3 import DEFAULT_QWEN3_MODEL, Qwen3ProblemClassifier


class FakeTokenizer:
    def __init__(self, output: str, rejects_non_thinking: bool = False) -> None:
        self.output = output
        self.rejects_non_thinking = rejects_non_thinking
        self.chat_template_calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []
        self.prompts: list[str] = []

    def apply_chat_template(self, messages, **kwargs) -> str:
        self.chat_template_calls.append((messages, kwargs))
        if self.rejects_non_thinking and "enable_thinking" in kwargs:
            raise TypeError("enable_thinking is unsupported")
        return "rendered prompt"

    def __call__(self, prompt: str, return_tensors: str):
        self.prompts.append(prompt)
        assert return_tensors == "pt"
        return {"input_ids": [[101, 102]]}

    def decode(self, token_ids, skip_special_tokens: bool) -> str:
        assert list(token_ids) == [999]
        assert skip_special_tokens is True
        return self.output


class FakeModel:
    def __init__(self) -> None:
        self.eval_calls = 0
        self.generate_calls: list[dict[str, object]] = []

    def eval(self) -> None:
        self.eval_calls += 1

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return [[101, 102, 999]]


def _install_fake_transformers(monkeypatch, tokenizer: FakeTokenizer, model: FakeModel):
    tokenizer_loads: list[str] = []
    model_loads: list[str] = []

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(model_name: str) -> FakeTokenizer:
            tokenizer_loads.append(model_name)
            return tokenizer

    class AutoModelForCausalLM:
        @staticmethod
        def from_pretrained(model_name: str) -> FakeModel:
            model_loads.append(model_name)
            return model

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=AutoTokenizer,
            AutoModelForCausalLM=AutoModelForCausalLM,
        ),
    )
    return tokenizer_loads, model_loads


def _classifier(monkeypatch, output: str, **kwargs):
    tokenizer = FakeTokenizer(output, **kwargs)
    model = FakeModel()
    tokenizer_loads, model_loads = _install_fake_transformers(monkeypatch, tokenizer, model)
    return Qwen3ProblemClassifier(), tokenizer, model, tokenizer_loads, model_loads


def test_qwen3_classifier_returns_a_positive_classification_with_a_correct_prompt(
    monkeypatch,
) -> None:
    classifier, tokenizer, model, tokenizer_loads, model_loads = _classifier(
        monkeypatch,
        '{"is_problem": true, "confidence": 0.91, "reason": "Deployment keeps failing"}',
    )

    result = classifier.classify("My deployment keeps failing and I need help")

    assert result.is_problem is True
    assert result.confidence == pytest.approx(0.91)
    assert result.reason == "Deployment keeps failing"
    assert result.classifier_name == f"Qwen3ProblemClassifier:{DEFAULT_QWEN3_MODEL}"
    assert tokenizer_loads == [DEFAULT_QWEN3_MODEL]
    assert model_loads == [DEFAULT_QWEN3_MODEL]
    assert model.eval_calls == 1
    assert model.generate_calls == [
        {"input_ids": [[101, 102]], "do_sample": False, "max_new_tokens": 128}
    ]
    messages, options = tokenizer.chat_template_calls[0]
    assert options["enable_thinking"] is False
    assert options["add_generation_prompt"] is True
    assert "problem, need, or pain point" in messages[0]["content"]
    assert "news, announcements, tutorials, promotions" in messages[0]["content"]
    assert messages[1]["content"].endswith("My deployment keeps failing and I need help")


def test_qwen3_classifier_returns_a_negative_classification(monkeypatch) -> None:
    classifier, _, _, _, _ = _classifier(
        monkeypatch,
        '{"is_problem": false, "confidence": 0.88, "reason": "Product announcement"}',
    )

    result = classifier.classify("We are pleased to announce version 2.0")

    assert result.is_problem is False
    assert result.confidence == pytest.approx(0.88)
    assert result.reason == "Product announcement"


def test_qwen3_classifier_loads_the_model_and_tokenizer_once_per_instance(monkeypatch) -> None:
    classifier, _, model, tokenizer_loads, model_loads = _classifier(
        monkeypatch,
        '{"is_problem": true, "confidence": 0.8, "reason": "Need support"}',
    )

    classifier.classify("I need support")
    classifier.classify("I still need support")

    assert tokenizer_loads == [DEFAULT_QWEN3_MODEL]
    assert model_loads == [DEFAULT_QWEN3_MODEL]
    assert model.eval_calls == 1
    assert len(model.generate_calls) == 2


def test_qwen3_classifier_accepts_json_wrapped_in_a_markdown_fence(monkeypatch) -> None:
    classifier, _, _, _, _ = _classifier(
        monkeypatch,
        '```json\n{"is_problem": true, "confidence": 1.0, "reason": "Clear pain point"}\n```',
    )

    result = classifier.classify("This is a clear pain point")

    assert result.is_problem is True
    assert result.confidence == 1.0


def test_qwen3_classifier_falls_back_when_the_template_does_not_support_non_thinking(
    monkeypatch,
) -> None:
    classifier, tokenizer, _, _, _ = _classifier(
        monkeypatch,
        '{"is_problem": false, "confidence": 0.7, "reason": "Generic discussion"}',
        rejects_non_thinking=True,
    )

    classifier.classify("A generic discussion")

    assert tokenizer.chat_template_calls[0][1]["enable_thinking"] is False
    assert "enable_thinking" not in tokenizer.chat_template_calls[1][1]


@pytest.mark.parametrize(
    "output, error",
    [
        ("not JSON", "malformed JSON"),
        ('{"is_problem": true, "confidence": 0.9}', "exactly is_problem"),
        ('{"is_problem": true, "confidence": 1.1, "reason": "Too high"}', "between 0 and 1"),
        (
            'Answer: {"is_problem": true, "confidence": 0.9, "reason": "Extra prose"}',
            "malformed JSON",
        ),
        (
            '{"is_problem": true, "confidence": 0.9, "reason": "Extra field", "other": 1}',
            "exactly is_problem",
        ),
        (
            '{"is_problem": true, "confidence": 0.9, "confidence": 0.8, "reason": "Duplicate"}',
            "duplicate fields",
        ),
    ],
)
def test_qwen3_classifier_rejects_malformed_or_ambiguous_output(
    monkeypatch, output: str, error: str
) -> None:
    classifier, _, _, _, _ = _classifier(monkeypatch, output)

    with pytest.raises(ValueError, match=error):
        classifier.classify("Please classify this content")
