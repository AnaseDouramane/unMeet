from __future__ import annotations

import json
import math
import re
from numbers import Real
from typing import Any

from app.problem_detection.schemas import ProblemDetectionResult

DEFAULT_QWEN3_MODEL = "Qwen/Qwen3-0.6B"


class Qwen3ProblemClassifier:
    def __init__(
        self,
        model_name: str = DEFAULT_QWEN3_MODEL,
        max_new_tokens: int = 128,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must not be empty")
        if isinstance(max_new_tokens, bool) or not isinstance(max_new_tokens, int):
            raise TypeError("max_new_tokens must be an integer")
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be positive")

        self.model_name = model_name.strip()
        self.max_new_tokens = max_new_tokens
        self._tokenizer: Any | None = None
        self._model: Any | None = None

    def classify(self, document_text: str) -> ProblemDetectionResult:
        if not isinstance(document_text, str):
            raise TypeError("document_text must be a string")
        if not document_text.strip():
            raise ValueError("document_text must not be empty")

        tokenizer, model = self._load_components()
        prompt = self._build_prompt(tokenizer, document_text)
        output = self._generate(tokenizer, model, prompt)
        payload = self._parse_output(output)
        return self._to_result(payload)

    def _load_components(self) -> tuple[Any, Any]:
        if self._tokenizer is None or self._model is None:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            if self._tokenizer is None:
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            if self._model is None:
                self._model = AutoModelForCausalLM.from_pretrained(self.model_name)
                self._model.eval()
        return self._tokenizer, self._model

    def _build_prompt(self, tokenizer: Any, document_text: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Classify whether the content itself expresses a real problem, need, or pain point. "
                    "Set is_problem to true only when the text directly, or with strong implicit evidence, "
                    "expresses at least one of: a concrete difficulty; a lived frustration; a manual, costly, "
                    "or repetitive task; an unmet need; or an explicit request for a tool or solution. "
                    "Set is_problem to false for news and announcements, product releases, tutorials and "
                    "guides, descriptions of solutions, generic opinions, and technical content without an "
                    "expressed pain point. Do not infer a problem merely because a product, technology, or "
                    "solution could satisfy a possible need. If uncertain, set is_problem to false. "
                    "Examples: \n"
                    "- Content: 'Every week I manually copy invoices into our accounting system; it takes hours.' "
                    "Result: is_problem=true.\n"
                    "- Content: 'Is there a tool that alerts me when a customer's subscription is about to expire?' "
                    "Result: is_problem=true.\n"
                    "- Content: 'OpenAI released a new model with improved reasoning capabilities.' "
                    "Result: is_problem=false.\n"
                    "- Content: 'This guide shows how to deploy FastAPI with Docker.' Result: is_problem=false.\n"
                    "- Content: 'We are announcing version 2.0 of our analytics platform.' Result: is_problem=false. "
                    "Return exactly one JSON object with no prose or extra fields: "
                    '{"is_problem": boolean, "confidence": number between 0 and 1, '
                    '"reason": "short non-empty explanation"}. '
                    "Do not use markdown unless required by the response format."
                ),
            },
            {"role": "user", "content": f"Content to classify:\n{document_text}"},
        ]
        try:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

    def _generate(self, tokenizer: Any, model: Any, prompt: str) -> str:
        model_inputs = tokenizer(prompt, return_tensors="pt")
        device = getattr(model, "device", None)
        if device is not None:
            if hasattr(model_inputs, "to"):
                model_inputs = model_inputs.to(device)
            else:
                model_inputs = {
                    key: value.to(device) if hasattr(value, "to") else value
                    for key, value in model_inputs.items()
                }

        generated_ids = model.generate(
            **model_inputs,
            do_sample=False,
            max_new_tokens=self.max_new_tokens,
        )
        input_ids = model_inputs["input_ids"]
        prompt_length = len(input_ids[0])
        return tokenizer.decode(generated_ids[0][prompt_length:], skip_special_tokens=True).strip()

    @staticmethod
    def _parse_output(output: str) -> dict[str, Any]:
        if not isinstance(output, str) or not output.strip():
            raise ValueError("classifier output must contain JSON")

        candidate = output.strip()
        if candidate.startswith("```"):
            fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL)
            if fenced is None:
                raise ValueError("classifier output must contain exactly one JSON object")
            candidate = fenced.group(1)
        elif "```" in candidate:
            raise ValueError("classifier output must contain exactly one JSON object")

        try:
            payload = json.loads(candidate, object_pairs_hook=Qwen3ProblemClassifier._unique_object)
        except json.JSONDecodeError as error:
            raise ValueError("classifier output contains malformed JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("classifier output JSON must be an object")
        return payload

    @staticmethod
    def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError("classifier output JSON contains duplicate fields")
            payload[key] = value
        return payload

    def _to_result(self, payload: dict[str, Any]) -> ProblemDetectionResult:
        expected_fields = {"is_problem", "confidence", "reason"}
        if set(payload) != expected_fields:
            raise ValueError(
                "classifier output JSON must contain exactly is_problem, confidence, reason"
            )

        is_problem = payload["is_problem"]
        if not isinstance(is_problem, bool):
            raise ValueError("classifier output is_problem must be a bool")

        confidence = payload["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, Real):
            raise ValueError("classifier output confidence must be numeric")
        normalized_confidence = float(confidence)
        if not math.isfinite(normalized_confidence):
            raise ValueError("classifier output confidence must be finite")
        if not 0.0 <= normalized_confidence <= 1.0:
            raise ValueError("classifier output confidence must be between 0 and 1")

        reason = payload["reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("classifier output reason must not be empty")

        return ProblemDetectionResult(
            is_problem=is_problem,
            confidence=normalized_confidence,
            reason=reason.strip(),
            classifier_name=f"Qwen3ProblemClassifier:{self.model_name}",
        )
