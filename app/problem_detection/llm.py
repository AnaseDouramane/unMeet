"""Signal classifier backed by any OpenAI-compatible chat completions API.

Works with hosted providers (Groq, OpenAI, OpenRouter, Together) and local servers (vLLM,
Ollama, LM Studio) by changing ``base_url`` and ``model``. Compared with the local Qwen3
classifier it is fast on any machine and extracts the actionable signal fields.

Design choices:

- Structured output: the request asks for a JSON object matching :data:`SIGNAL_JSON_SCHEMA`;
  the response is still validated strictly because not every provider enforces schemas.
- Grounded quotes: ``pain_quote`` must be a verbatim excerpt of the document. Quotes the model
  paraphrased or invented are dropped rather than stored, so users never see fabricated text
  attributed to a real person.
- Transient errors (timeouts, HTTP 429 and 5xx) are retried with exponential backoff that
  honours ``Retry-After``; other errors fail fast.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Sequence
from numbers import Real
from typing import Any

import requests

from app.llm.client import (
    ChatCompletionsClient,
    LLMRequestError,
    LLMResponseError,
    parse_json_object,
)
from app.problem_detection.schemas import (
    SIGNAL_INTENTS,
    MalformedClassifierOutputError,
    ProblemDetectionResult,
    SignalIntent,
)

SYSTEM_PROMPT = """You analyse public posts and comments for go-to-market teams.
Decide whether the text expresses a real problem, need or pain point of its author, and extract
the signal.

is_problem is true only when the author directly (or with strong implicit evidence) expresses a
concrete difficulty, frustration, cost, inefficiency, manual or repetitive work, unmet need, or a
request for a tool or solution. News, announcements, launches, tutorials, descriptions of
solutions, generic opinions and technology comparisons are not problems. If uncertain, choose
false.

intent:
- "pain_point": the author describes a problem they have.
- "feature_request": the author asks for a capability in an existing product.
- "solution_search": the author is looking for, or asking for recommendations on, a tool or service.
- "competitor_complaint": the author criticises a specific named product or company.
- "none": not a problem.

pain_quote: the shortest verbatim excerpt (copied exactly, at most 200 characters) that states
the pain; null when is_problem is false.
products_mentioned: names of products or companies the author mentions, as written; [] if none.
severity: 1 minor annoyance, 2 recurring cost or friction, 3 blocking, costly or urgent; null
when is_problem is false.
reason: one short sentence explaining the decision.
Answer with one JSON object only."""

SIGNAL_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "is_problem",
        "confidence",
        "intent",
        "pain_quote",
        "products_mentioned",
        "severity",
        "reason",
    ],
    "properties": {
        "is_problem": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "intent": {"type": "string", "enum": sorted(SIGNAL_INTENTS)},
        "pain_quote": {"type": ["string", "null"]},
        "products_mentioned": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": ["integer", "null"], "minimum": 1, "maximum": 3},
        "reason": {"type": "string"},
    },
}

BATCH_SYSTEM_PROMPT = (
    SYSTEM_PROMPT.replace(
        "Answer with one JSON object only.",
        "",
    ).rstrip()
    + """
You receive several texts, each introduced by a header like "### Text 3". Analyse every text
independently, using only that text. Answer with one JSON object of the form
{"results": [...]} holding exactly one entry per text, each with the fields above plus "index"
set to the text number from its header."""
)

BATCH_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", *SIGNAL_JSON_SCHEMA["required"]],
                "properties": {
                    "index": {"type": "integer", "minimum": 0},
                    **SIGNAL_JSON_SCHEMA["properties"],
                },
            },
        }
    },
}

_MAX_QUOTE_LENGTH = 200
_MAX_PRODUCTS = 10


LLMClassifierError = LLMRequestError


class OpenAICompatibleSignalClassifier:
    def __init__(
        self,
        model: str,
        base_url: str = "https://api.groq.com/openai/v1",
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 4,
        max_document_chars: int = 6000,
        batch_max_document_chars: int = 2000,
        use_json_schema: bool = True,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_document_chars <= 0:
            raise ValueError("max_document_chars must be positive")
        if batch_max_document_chars <= 0:
            raise ValueError("batch_max_document_chars must be positive")
        self._client = ChatCompletionsClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            session=session,
            sleep=sleep,
        )
        self.model = self._client.model
        self.base_url = self._client.base_url
        self.max_document_chars = max_document_chars
        self.batch_max_document_chars = batch_max_document_chars
        self.use_json_schema = use_json_schema

    @property
    def classifier_name(self) -> str:
        return f"OpenAICompatibleSignalClassifier:{self.model}"

    def classify(self, document_text: str) -> ProblemDetectionResult:
        if not isinstance(document_text, str):
            raise TypeError("document_text must be a string")
        if not document_text.strip():
            raise ValueError("document_text must not be empty")

        text = document_text[: self.max_document_chars]
        try:
            content = self._client.complete(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Text:\n{text}"},
                ],
                response_format=self._response_format(),
            )
            payload = parse_json_object(content)
        except LLMResponseError as error:
            raise MalformedClassifierOutputError(str(error)) from error
        return self._to_result(payload, text)

    @property
    def request_count(self) -> int:
        return self._client.request_count

    def classify_batch(
        self, document_texts: Sequence[str]
    ) -> list[ProblemDetectionResult | MalformedClassifierOutputError]:
        """Classify several documents in one request.

        Returns one entry per input, in order. An entry is a
        :class:`MalformedClassifierOutputError` when the model skipped that text or returned an
        invalid answer for it, so the caller can retry only those items. Quotes are verified
        against their own text, exactly as in :meth:`classify`.
        """
        texts = list(document_texts)
        if not texts:
            return []
        for text in texts:
            if not isinstance(text, str):
                raise TypeError("document_text must be a string")
            if not text.strip():
                raise ValueError("document_text must not be empty")
        truncated = [text[: self.batch_max_document_chars] for text in texts]
        prompt = "\n\n".join(f"### Text {i}\n{text}" for i, text in enumerate(truncated))
        try:
            content = self._client.complete(
                messages=[
                    {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format=self._response_format(BATCH_JSON_SCHEMA, "signal_batch"),
            )
            payload = parse_json_object(content)
        except LLMResponseError as error:
            malformed = MalformedClassifierOutputError(str(error))
            return [malformed] * len(texts)
        entries = payload.get("results")
        by_index: dict[int, Any] = {}
        if isinstance(entries, list):
            for entry in entries:
                index = entry.get("index") if isinstance(entry, dict) else None
                if isinstance(index, int) and not isinstance(index, bool):
                    by_index.setdefault(index, entry)
        results: list[ProblemDetectionResult | MalformedClassifierOutputError] = []
        for index, text in enumerate(truncated):
            entry = by_index.get(index)
            if entry is None:
                results.append(MalformedClassifierOutputError(f"no result for text {index}"))
                continue
            try:
                results.append(self._to_result(entry, text))
            except MalformedClassifierOutputError as error:
                results.append(error)
        return results

    def _response_format(
        self, schema: dict[str, Any] | None = None, name: str = "signal"
    ) -> dict[str, Any]:
        if self.use_json_schema:
            return {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": schema or SIGNAL_JSON_SCHEMA},
            }
        return {"type": "json_object"}

    def _to_result(self, payload: dict[str, Any], text: str) -> ProblemDetectionResult:
        is_problem = payload.get("is_problem")
        if not isinstance(is_problem, bool):
            raise MalformedClassifierOutputError("is_problem must be a boolean")

        confidence = payload.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, Real):
            raise MalformedClassifierOutputError("confidence must be numeric")
        confidence_value = float(confidence)
        if not math.isfinite(confidence_value) or not 0.0 <= confidence_value <= 1.0:
            raise MalformedClassifierOutputError("confidence must be between 0 and 1")

        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise MalformedClassifierOutputError("reason must be a non-empty string")

        intent = payload.get("intent")
        if intent not in SIGNAL_INTENTS:
            raise MalformedClassifierOutputError(f"intent must be one of {sorted(SIGNAL_INTENTS)}")

        if not is_problem:
            return ProblemDetectionResult(
                is_problem=False,
                confidence=confidence_value,
                reason=reason.strip(),
                classifier_name=self.classifier_name,
                intent="none",
            )

        return ProblemDetectionResult(
            is_problem=True,
            confidence=confidence_value,
            reason=reason.strip(),
            classifier_name=self.classifier_name,
            intent=_problem_intent(intent),
            pain_quote=_grounded_quote(payload.get("pain_quote"), text),
            products_mentioned=_products(payload.get("products_mentioned")),
            severity=_severity(payload.get("severity")),
        )


def _problem_intent(intent: Any) -> SignalIntent:
    # A problem labelled "none" is contradictory; keep the safest actionable reading.
    return "pain_point" if intent == "none" else intent


def _normalise_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _grounded_quote(quote: Any, text: str) -> str | None:
    """Return the quote only if it appears verbatim (modulo whitespace and case) in the text."""
    if not isinstance(quote, str):
        return None
    normalised_quote = _normalise_whitespace(quote).strip("\"'“”")
    if not normalised_quote:
        return None
    if normalised_quote.lower() not in _normalise_whitespace(text).lower():
        return None
    return normalised_quote[:_MAX_QUOTE_LENGTH]


def _products(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    products: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        name = _normalise_whitespace(item)
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            products.append(name[:100])
    return tuple(products[:_MAX_PRODUCTS])


def _severity(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    severity = round(float(value))
    return severity if 1 <= severity <= 3 else None
