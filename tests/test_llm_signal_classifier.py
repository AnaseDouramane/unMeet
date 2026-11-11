import json
from typing import Any

import pytest
import requests

from app.problem_detection.llm import (
    SIGNAL_JSON_SCHEMA,
    LLMClassifierError,
    OpenAICompatibleSignalClassifier,
)
from app.problem_detection.schemas import MalformedClassifierOutputError
from app.problem_detection.service import validate_problem_detection_result

DOCUMENT = (
    "We moved to HubSpot last year. Every Monday I spend three hours cleaning duplicate "
    "contacts by hand before sequences go out. Is there anything that fixes this?"
)


class FakeResponse:
    def __init__(
        self, status_code: int, payload: Any = None, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, json: dict, headers: dict, timeout: float) -> FakeResponse:
        self.requests.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _completion(content: dict[str, Any] | str) -> FakeResponse:
    text = content if isinstance(content, str) else json.dumps(content)
    return FakeResponse(200, {"choices": [{"message": {"content": text}}]})


def _signal(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "is_problem": True,
        "confidence": 0.92,
        "intent": "solution_search",
        "pain_quote": "I spend three hours cleaning duplicate contacts by hand",
        "products_mentioned": ["HubSpot", "hubspot", " "],
        "severity": 2,
        "reason": "Recurring manual work and an explicit request for a tool.",
    }
    payload.update(overrides)
    return payload


def _classifier(session: FakeSession, **kwargs: Any) -> OpenAICompatibleSignalClassifier:
    sleeps: list[float] = []
    classifier = OpenAICompatibleSignalClassifier(
        model="llama-3.3-70b-versatile",
        api_key="test-key",
        session=session,  # type: ignore[arg-type]
        sleep=sleeps.append,
        **kwargs,
    )
    classifier.sleeps = sleeps  # type: ignore[attr-defined]
    return classifier


def test_extracts_a_validated_signal() -> None:
    session = FakeSession([_completion(_signal())])

    result = _classifier(session).classify(DOCUMENT)

    assert validate_problem_detection_result(result) is result
    assert result.is_problem is True
    assert result.intent == "solution_search"
    assert result.pain_quote == "I spend three hours cleaning duplicate contacts by hand"
    assert result.products_mentioned == ("HubSpot",)
    assert result.severity == 2
    assert result.classifier_name == "OpenAICompatibleSignalClassifier:llama-3.3-70b-versatile"


def test_request_uses_json_schema_auth_and_deterministic_sampling() -> None:
    session = FakeSession([_completion(_signal())])

    _classifier(session, base_url="https://llm.example/v1/").classify(DOCUMENT)

    request = session.requests[0]
    assert request["url"] == "https://llm.example/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert request["json"]["temperature"] == 0
    assert request["json"]["response_format"]["json_schema"]["schema"] == SIGNAL_JSON_SCHEMA


def test_json_object_mode_for_providers_without_schema_support() -> None:
    session = FakeSession([_completion(_signal())])

    _classifier(session, use_json_schema=False).classify(DOCUMENT)

    assert session.requests[0]["json"]["response_format"] == {"type": "json_object"}


def test_invented_quotes_are_dropped() -> None:
    session = FakeSession([_completion(_signal(pain_quote="HubSpot is a disaster"))])

    result = _classifier(session).classify(DOCUMENT)

    assert result.is_problem is True
    assert result.pain_quote is None


def test_quote_matching_ignores_whitespace_case_and_wrapping_quotes() -> None:
    quote = '"every monday   I spend three hours"'
    session = FakeSession([_completion(_signal(pain_quote=quote))])

    result = _classifier(session).classify(DOCUMENT)

    assert result.pain_quote == "every monday I spend three hours"


def test_non_problems_carry_no_signal_details() -> None:
    session = FakeSession(
        [_completion(_signal(is_problem=False, intent="none", severity=None, pain_quote=None))]
    )

    result = _classifier(session).classify("We just launched version 2.0 of our app.")

    assert result.is_problem is False
    assert result.intent == "none"
    assert result.pain_quote is None
    assert result.products_mentioned == ()
    assert result.severity is None


def test_fenced_json_is_accepted() -> None:
    session = FakeSession([_completion("```json\n" + json.dumps(_signal()) + "\n```")])

    assert _classifier(session).classify(DOCUMENT).is_problem is True


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[1, 2]",
        json.dumps(_signal(is_problem="yes")),
        json.dumps(_signal(confidence=1.5)),
        json.dumps(_signal(intent="rant")),
        json.dumps(_signal(reason="")),
    ],
)
def test_malformed_outputs_raise_the_contract_error(content: str) -> None:
    session = FakeSession([_completion(content)])

    with pytest.raises(MalformedClassifierOutputError):
        _classifier(session).classify(DOCUMENT)


def test_rate_limits_are_retried_honouring_retry_after() -> None:
    session = FakeSession(
        [
            FakeResponse(429, {"error": "slow down"}, {"Retry-After": "7"}),
            FakeResponse(503, {"error": "busy"}),
            _completion(_signal()),
        ]
    )
    classifier = _classifier(session)

    result = classifier.classify(DOCUMENT)

    assert result.is_problem is True
    assert classifier.sleeps == [7.0, 2.0]  # type: ignore[attr-defined]


def test_network_errors_are_retried_then_reported() -> None:
    session = FakeSession([requests.Timeout("t1"), requests.ConnectionError("c2")])

    with pytest.raises(LLMClassifierError):
        _classifier(session, max_retries=1).classify(DOCUMENT)


def test_client_errors_fail_fast() -> None:
    session = FakeSession([FakeResponse(401, {"error": "invalid api key"})])

    with pytest.raises(LLMClassifierError, match="401"):
        _classifier(session).classify(DOCUMENT)

    assert len(session.requests) == 1


def test_long_documents_are_truncated_before_sending() -> None:
    session = FakeSession([_completion(_signal(pain_quote=None))])

    _classifier(session, max_document_chars=50).classify("x" * 500)

    sent = session.requests[0]["json"]["messages"][1]["content"]
    assert sent == "Text:\n" + "x" * 50


def test_json_is_found_after_a_reasoning_block_or_around_short_text() -> None:
    from app.llm.client import parse_json_object

    assert parse_json_object('<think>Let me check the schema...</think>\n{"a": 1}') == {"a": 1}
    assert parse_json_object('<THINK>\nmulti\nline\n</THINK>```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json_object('Here is the JSON: {"a": 3} Hope it helps.') == {"a": 3}


def test_unreadable_answers_say_what_the_model_returned() -> None:
    from app.llm.client import LLMResponseError, parse_json_object

    for content, fragment in (
        ("I'm sorry, I can't help with that.", "I'm sorry"),
        ("", "empty answer"),
        ('{"a": 1', '{"a": 1'),
        ("[1, 2]", "[1, 2]"),
    ):
        with pytest.raises(LLMResponseError) as raised:
            parse_json_object(content)
        assert fragment in str(raised.value) or "JSON object" in str(raised.value)
