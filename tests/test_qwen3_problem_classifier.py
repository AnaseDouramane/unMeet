import sys
from types import SimpleNamespace

import pytest

from app.problem_detection.qwen3 import DEFAULT_QWEN3_MODEL, Qwen3ProblemClassifier
from app.problem_detection.schemas import MalformedClassifierOutputError


class FakeTokenizer:
    def __init__(
        self,
        output: str,
        rejects_non_thinking: bool = False,
        model_inputs: object | None = None,
    ) -> None:
        self.output = output
        self.rejects_non_thinking = rejects_non_thinking
        self.model_inputs = model_inputs or {"input_ids": [[101, 102]]}
        self.chat_template_calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []
        self.prompts: list[str] = []

    def apply_chat_template(self, messages, **kwargs) -> str:
        self.chat_template_calls.append((messages, kwargs))
        if self.rejects_non_thinking and "enable_thinking" in kwargs:
            raise TypeError("enable_thinking is unsupported")
        return "\n".join(message["content"] for message in messages)

    def __call__(self, prompt: str, return_tensors: str):
        self.prompts.append(prompt)
        assert return_tensors == "pt"
        return self.model_inputs

    def decode(self, token_ids, skip_special_tokens: bool) -> str:
        assert list(token_ids) == [999]
        assert skip_special_tokens is True
        return self.output


class FakeModel:
    def __init__(self) -> None:
        self.eval_calls = 0
        self.device: str | None = None
        self.to_calls: list[str] = []
        self.generate_calls: list[dict[str, object]] = []
        self.load_kwargs: dict[str, object] = {}

    def to(self, device: str) -> "FakeModel":
        self.to_calls.append(device)
        self.device = device
        return self

    def eval(self) -> None:
        self.eval_calls += 1

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return [[101, 102, 999]]


class FakeInputIds(list):
    def __init__(self) -> None:
        super().__init__([[101, 102]])
        self.device: str | None = None

    def to(self, device: str) -> "FakeInputIds":
        self.device = device
        return self


class FakeModelInputs(dict):
    def __init__(self) -> None:
        super().__init__(input_ids=FakeInputIds())
        self.to_calls: list[str] = []

    def to(self, device: str) -> "FakeModelInputs":
        self.to_calls.append(device)
        self["input_ids"].to(device)
        return self


class FakeInferenceMode:
    def __init__(self, torch: "FakeTorch") -> None:
        self.torch = torch

    def __enter__(self) -> None:
        self.torch.inference_mode_entries += 1

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class FakeTorch:
    float16 = "float16"

    def __init__(self, cuda_available: bool) -> None:
        self.cuda = SimpleNamespace(is_available=lambda: cuda_available)
        self.inference_mode_entries = 0

    def inference_mode(self) -> FakeInferenceMode:
        return FakeInferenceMode(self)


def _install_fake_transformers(
    monkeypatch, tokenizer: FakeTokenizer, model: FakeModel, cuda_available: bool = False
):
    tokenizer_loads: list[str] = []
    model_loads: list[str] = []

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(model_name: str) -> FakeTokenizer:
            tokenizer_loads.append(model_name)
            return tokenizer

    class AutoModelForCausalLM:
        @staticmethod
        def from_pretrained(model_name: str, **kwargs) -> FakeModel:
            model_loads.append(model_name)
            model.load_kwargs = kwargs
            return model

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=AutoTokenizer,
            AutoModelForCausalLM=AutoModelForCausalLM,
        ),
    )
    fake_torch = FakeTorch(cuda_available)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    return tokenizer_loads, model_loads, fake_torch


def _classifier(
    monkeypatch,
    output: str,
    cuda_available: bool = False,
    device: str | None = None,
    **kwargs,
):
    tokenizer = FakeTokenizer(output, **kwargs)
    model = FakeModel()
    tokenizer_loads, model_loads, fake_torch = _install_fake_transformers(
        monkeypatch, tokenizer, model, cuda_available
    )
    return (
        Qwen3ProblemClassifier(device=device),
        tokenizer,
        model,
        tokenizer_loads,
        model_loads,
        fake_torch,
    )


def test_qwen3_classifier_returns_a_positive_classification_with_a_correct_prompt(
    monkeypatch,
) -> None:
    classifier, tokenizer, model, tokenizer_loads, model_loads, fake_torch = _classifier(
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
    assert classifier.device_name == "cpu"
    assert classifier.model_device_name == "cpu"
    assert classifier.input_ids_device_name is None
    assert model.to_calls == ["cpu"]
    assert model.load_kwargs == {}
    assert fake_torch.inference_mode_entries == 1
    assert model.generate_calls == [
        {"input_ids": [[101, 102]], "do_sample": False, "max_new_tokens": 128}
    ]
    _, options = tokenizer.chat_template_calls[0]
    assert options["enable_thinking"] is False
    assert options["add_generation_prompt"] is True
    assert tokenizer.prompts[0].endswith("My deployment keeps failing and I need help")


def test_qwen3_classifier_sends_the_complete_prompt_contract_to_the_tokenizer(monkeypatch) -> None:
    classifier, tokenizer, _, _, _, _ = _classifier(
        monkeypatch,
        '{"is_problem": false, "confidence": 0.8, "reason": "Prompt contract test"}',
    )

    classifier.classify("Content under test")

    prompt = tokenizer.prompts[0]
    assert "a concrete difficulty, frustration, cost, inefficiency" in prompt
    assert "manual or repetitive task" in prompt
    assert "concrete request for a tool or solution" in prompt
    assert "news and announcements" in prompt
    assert "product releases" in prompt
    assert "tutorials and guides" in prompt
    assert "descriptions of solutions" in prompt
    assert "If uncertain, set is_problem to false" in prompt
    assert (
        "Do not infer a problem merely because a product, technology, or solution could satisfy"
        in prompt
    )
    assert (
        "Generic preferences, technology comparisons, and broad opinions are not problems" in prompt
    )
    assert "maintainability or efficiency into an unexpressed pain point" in prompt

    assert (
        "Every week I manually copy invoices into our accounting system; it takes hours." in prompt
    )
    assert (
        "Is there a tool that alerts me when a customer's subscription is about to expire?"
        in prompt
    )
    assert "OpenAI released a new model with improved reasoning capabilities." in prompt
    assert "This guide shows how to deploy FastAPI with Docker." in prompt
    assert "We are announcing version 2.0 of our analytics platform." in prompt
    assert "Many developers prefer typed languages for large codebases." in prompt
    assert "FastAPI is simpler than Django for small services." in prompt
    assert "Rust is a great technology for reliable systems." in prompt
    assert prompt.count("Result: is_problem=true") == 2
    assert prompt.count("Result: is_problem=false") == 6


def test_qwen3_classifier_returns_a_negative_classification(monkeypatch) -> None:
    classifier, _, _, _, _, _ = _classifier(
        monkeypatch,
        '{"is_problem": false, "confidence": 0.88, "reason": "Product announcement"}',
    )

    result = classifier.classify("We are pleased to announce version 2.0")

    assert result.is_problem is False
    assert result.confidence == pytest.approx(0.88)
    assert result.reason == "Product announcement"


def test_qwen3_classifier_loads_the_model_and_tokenizer_once_per_instance(monkeypatch) -> None:
    classifier, _, model, tokenizer_loads, model_loads, _ = _classifier(
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
    classifier, _, _, _, _, _ = _classifier(
        monkeypatch,
        '```json\n{"is_problem": true, "confidence": 1.0, "reason": "Clear pain point"}\n```',
    )

    result = classifier.classify("This is a clear pain point")

    assert result.is_problem is True
    assert result.confidence == 1.0


def test_qwen3_classifier_falls_back_when_the_template_does_not_support_non_thinking(
    monkeypatch,
) -> None:
    classifier, tokenizer, _, _, _, _ = _classifier(
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
        (
            '{"is_problem": true, "confidence": 0.9, "reason": "Valid", "extra": true}',
            "exactly is_problem",
        ),
        ('{"is_problem": "true", "confidence": 0.9, "reason": "Wrong type"}', "is_problem"),
        ('{"is_problem": true, "confidence": "0.9", "reason": "Wrong type"}', "confidence"),
        ('{"is_problem": true, "confidence": -0.1, "reason": "Too low"}', "between 0 and 1"),
        ('{"is_problem": true, "confidence": 1.1, "reason": "Too high"}', "between 0 and 1"),
        ('{"is_problem": true, "confidence": NaN, "reason": "Not finite"}', "finite"),
        ('{"is_problem": true, "confidence": Infinity, "reason": "Not finite"}', "finite"),
        ('{"is_problem": true, "confidence": 0.9, "reason": "   "}', "reason"),
        (
            'Answer: {"is_problem": true, "confidence": 0.9, "reason": "Extra prose"}',
            "malformed JSON",
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
    classifier, _, _, _, _, _ = _classifier(monkeypatch, output)

    with pytest.raises(MalformedClassifierOutputError, match=error):
        classifier.classify("Please classify this content")


def test_qwen3_classifier_marks_invalid_json_with_a_specific_error(monkeypatch) -> None:
    classifier, _, _, _, _, _ = _classifier(monkeypatch, "not JSON")

    with pytest.raises(MalformedClassifierOutputError, match="malformed JSON"):
        classifier.classify("Please classify this content")


def test_qwen3_classifier_automatically_uses_cuda_with_float16(monkeypatch) -> None:
    classifier, _, model, _, _, fake_torch = _classifier(
        monkeypatch,
        '{"is_problem": false, "confidence": 0.8, "reason": "News"}',
        cuda_available=True,
    )

    classifier.classify("A product announcement")

    assert classifier.device_name == "cuda"
    assert classifier.model_device_name == "cuda"
    assert classifier.input_ids_device_name is None
    assert model.load_kwargs == {"torch_dtype": "float16"}
    assert model.to_calls == ["cuda"]
    assert fake_torch.inference_mode_entries == 1


def test_qwen3_classifier_moves_tokenized_inputs_to_the_selected_device(monkeypatch) -> None:
    model_inputs = FakeModelInputs()
    classifier, _, model, _, _, _ = _classifier(
        monkeypatch,
        '{"is_problem": true, "confidence": 0.9, "reason": "Manual work"}',
        cuda_available=True,
        device="cuda",
        model_inputs=model_inputs,
    )

    classifier.classify("I manually reconcile invoices every week")

    assert model.to_calls == ["cuda"]
    assert model_inputs.to_calls == ["cuda"]
    assert model.device == "cuda"
    assert model_inputs["input_ids"].device == "cuda"
    assert classifier.device_name == "cuda"
    assert classifier.model_device_name == "cuda"
    assert classifier.input_ids_device_name == "cuda"
    assert model.generate_calls[0]["input_ids"] == [[101, 102]]


def test_qwen3_classifier_rejects_cuda_when_unavailable(monkeypatch) -> None:
    classifier, _, _, _, _, _ = _classifier(
        monkeypatch,
        '{"is_problem": false, "confidence": 0.8, "reason": "News"}',
        device="cuda",
    )

    with pytest.raises(RuntimeError, match="CUDA was requested"):
        classifier.classify("A product announcement")
