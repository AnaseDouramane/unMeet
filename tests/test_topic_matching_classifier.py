import json
from typing import Any

from app.problem_detection.llm import (
    BATCH_JSON_SCHEMA,
    SIGNAL_JSON_SCHEMA,
    TOPIC_PROMPT,
    OpenAICompatibleSignalClassifier,
)
from app.problem_detection.schemas import ProblemDetectionResult, TopicContext, TopicMatch

TEXT = "Every Monday I spend three hours cleaning duplicate contacts in HubSpot by hand."
CRM = TopicContext(7, "CRM hygiene", "teams cleaning duplicate CRM data")
BILLING = TopicContext(9, "Billing", None)


class Response:
    status_code = 200
    def __init__(self, content: Any) -> None:
        self.headers: dict[str, str] = {}
        self._payload = {"choices": [{"message": {"content": json.dumps(content)}}]}
        self.text = ""

    def json(self) -> Any:
        return self._payload


class Session:
    def __init__(self, *contents: Any) -> None:
        self.contents = list(contents)
        self.requests: list[dict[str, Any]] = []

    def post(self, url, json, headers, timeout):
        self.requests.append(json)
        return Response(self.contents.pop(0))


def _signal(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "is_problem": True,
        "confidence": 0.9,
        "intent": "pain_point",
        "pain_quote": "spend three hours cleaning duplicate contacts",
        "products_mentioned": ["HubSpot"],
        "severity": 2,
        "reason": "manual work",
        "topic_matches": [{"topic_id": 7, "reason": "Cleans duplicate contacts by hand."}],
    }
    payload.update(overrides)
    return payload


def _classifier(session: Session) -> OpenAICompatibleSignalClassifier:
    return OpenAICompatibleSignalClassifier(
        model="m",
        api_key="k",
        session=session,
        sleep=lambda _: None,  # type: ignore[arg-type]
    )


def test_topics_are_listed_in_the_prompt_and_schema() -> None:
    session = Session(_signal())
    result = _classifier(session).classify(TEXT, [CRM, BILLING])

    request = session.requests[0]
    user = request["messages"][1]["content"]
    assert "Candidate topics:" in user
    assert "topic_id 7: CRM hygiene — teams cleaning duplicate CRM data" in user
    assert "topic_id 9: Billing" in user
    assert TOPIC_PROMPT in request["messages"][0]["content"]
    schema = request["response_format"]["json_schema"]["schema"]
    assert "topic_matches" in schema["required"]
    assert result.topic_matches == (TopicMatch(7, "Cleans duplicate contacts by hand."),)


def test_without_topics_the_request_is_unchanged() -> None:
    session = Session(_signal())
    result = _classifier(session).classify(TEXT)

    request = session.requests[0]
    assert "Candidate topics" not in request["messages"][1]["content"]
    assert TOPIC_PROMPT not in request["messages"][0]["content"]
    assert request["response_format"]["json_schema"]["schema"] == SIGNAL_JSON_SCHEMA
    assert result.topic_matches == ()


def test_invented_or_malformed_matches_are_dropped_not_fatal() -> None:
    matches = [
        {"topic_id": 7, "reason": "  Real   match.  "},
        {"topic_id": 7, "reason": "duplicate of the first"},
        {"topic_id": 99, "reason": "topic that was never offered"},
        {"topic_id": 9, "reason": "   "},
        {"topic_id": True, "reason": "bool is not an id"},
        {"topic_id": "7", "reason": "string id"},
        "garbage",
    ]
    result = _classifier(Session(_signal(topic_matches=matches))).classify(TEXT, [CRM, BILLING])
    assert isinstance(result, ProblemDetectionResult)
    assert result.topic_matches == (TopicMatch(7, "Real match."),)


def test_non_problem_never_carries_matches() -> None:
    payload = _signal(is_problem=False, intent="none", severity=None, pain_quote=None)
    result = _classifier(Session(payload)).classify(TEXT, [CRM])
    assert result.topic_matches == ()


def test_batch_lists_each_texts_own_topics() -> None:
    entries = [
        {**_signal(), "index": 0},
        {**_signal(topic_matches=[{"topic_id": 9, "reason": "Invoices."}]), "index": 1},
    ]
    session = Session({"results": entries})
    results = _classifier(session).classify_batch(
        [TEXT, "Invoices keep failing for us."], [[CRM], [BILLING]]
    )

    user = session.requests[0]["messages"][1]["content"]
    first, second = user.split("### Text 1")
    assert "topic_id 7" in first and "topic_id 9" not in first
    assert "topic_id 9" in second and "topic_id 7" not in second
    assert results[0].topic_matches == (TopicMatch(7, "Cleans duplicate contacts by hand."),)  # type: ignore[union-attr]
    # Topic 7 was not offered for text 1, so a match on it would be dropped; 9 was offered.
    assert results[1].topic_matches == (TopicMatch(9, "Invoices."),)  # type: ignore[union-attr]
    schema = session.requests[0]["response_format"]["json_schema"]["schema"]
    assert "topic_matches" in schema["properties"]["results"]["items"]["required"]
    assert schema != BATCH_JSON_SCHEMA


def test_batch_without_topics_keeps_the_plain_schema() -> None:
    session = Session({"results": [{**_signal(), "index": 0}]})
    _classifier(session).classify_batch([TEXT])
    assert session.requests[0]["response_format"]["json_schema"]["schema"] == BATCH_JSON_SCHEMA
