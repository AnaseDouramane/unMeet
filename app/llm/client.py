"""Minimal client for OpenAI-compatible chat completions APIs.

Kept dependency-free (plain ``requests``) so the same code talks to Groq, OpenAI, OpenRouter,
Together or a local vLLM/Ollama server by changing ``base_url``.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

import requests

_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


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
                return str(response.json()["choices"][0]["message"]["content"])
            except (ValueError, KeyError, IndexError, TypeError) as error:
                raise LLMResponseError("LLM response has no message content") from error
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
