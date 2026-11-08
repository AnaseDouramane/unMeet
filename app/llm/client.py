"""Minimal client for OpenAI-compatible chat completions APIs.

Kept dependency-free (plain ``requests``) so the same code talks to Groq, OpenAI, OpenRouter,
Together or a local vLLM/Ollama server by changing ``base_url``.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class LLMUsage:
    """Token usage of one completion, as reported by the provider."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    purpose: str = "completion"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def cost_usd(self, input_per_mtok: float, output_per_mtok: float) -> float:
        return (
            self.prompt_tokens * input_per_mtok + self.completion_tokens * output_per_mtok
        ) / 1_000_000


class LLMRequestError(RuntimeError):
    """Raised when the provider cannot be reached or rejects the request."""


class LLMResponseError(ValueError):
    """Raised when the provider answers without usable content."""


class ChatCompletionsClient:
    def __init__(
        self,
        model: str,
        base_url: str = "https://api.groq.com/openai/v1",
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 4,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        usage_sink: Callable[[LLMUsage], None] | None = None,
        purpose: str = "completion",
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must not be empty")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        self.model = model.strip()
        self.base_url = base_url.strip().rstrip("/")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._session = session or requests.Session()
        self._sleep = sleep
        self._request_count = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._count_lock = threading.Lock()
        self._usage_sink = usage_sink
        self._purpose = purpose

    @property
    def request_count(self) -> int:
        """Completions requested so far (retries of one request are not counted)."""
        with self._count_lock:
            return self._request_count

    @property
    def token_usage(self) -> tuple[int, int]:
        """(prompt_tokens, completion_tokens) reported by the provider so far."""
        with self._count_lock:
            return self._prompt_tokens, self._completion_tokens

    def _record_usage(self, payload: Any) -> None:
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            return
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if (
            isinstance(prompt, bool)
            or not isinstance(prompt, int)
            or prompt < 0
            or isinstance(completion, bool)
            or not isinstance(completion, int)
            or completion < 0
        ):
            return
        with self._count_lock:
            self._prompt_tokens += prompt
            self._completion_tokens += completion
        if self._usage_sink is not None:
            # Accounting must never break a completion.
            with contextlib.suppress(Exception):
                self._usage_sink(LLMUsage(self.model, prompt, completion, self._purpose))

    def complete(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Return the assistant message content, retrying transient failures.

        Timeouts, connection errors and HTTP 408/409/429/5xx are retried with exponential
        backoff (honouring ``Retry-After``); other HTTP errors fail immediately.
        """
        with self._count_lock:
            self._request_count += 1
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages,
        }
        if response_format is not None:
            body["response_format"] = response_format
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except (requests.Timeout, requests.ConnectionError) as error:
                if attempt == self.max_retries:
                    raise LLMRequestError(f"LLM request failed: {error}") from error
                self._sleep(backoff_seconds(attempt, None))
                continue

            if response.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                self._sleep(backoff_seconds(attempt, response.headers.get("Retry-After")))
                continue
            if response.status_code >= 400:
                raise LLMRequestError(
                    f"LLM provider returned HTTP {response.status_code}: {response.text[:300]}"
                )
            try:
                payload = response.json()
                content = str(payload["choices"][0]["message"]["content"])
            except (ValueError, KeyError, IndexError, TypeError) as error:
                raise LLMResponseError("LLM response has no message content") from error
            self._record_usage(payload)
            return content
        raise LLMRequestError("LLM request failed after retries")  # pragma: no cover


def parse_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a surrounding markdown code fence."""
    candidate = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL)
    if fenced is not None:
        candidate = fenced.group(1)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise LLMResponseError("LLM output is not valid JSON") from error
    if not isinstance(payload, dict):
        raise LLMResponseError("LLM output must be a JSON object")
    return payload


def backoff_seconds(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None:
        try:
            return min(max(float(retry_after), 0.0), 60.0)
        except ValueError:
            pass
    return float(min(2**attempt, 30))
