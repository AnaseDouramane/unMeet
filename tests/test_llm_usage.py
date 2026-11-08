import json
from dataclasses import replace
from typing import Any

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.config import settings as base_settings
from app.llm.client import ChatCompletionsClient, LLMUsage
from app.problem_detection.factory import build_usage_sink
from app.problem_detection.llm import OpenAICompatibleSignalClassifier
from app.usage.llm_usage import UsageTotals

API_KEY = "k-123"


class Response:
    status_code = 200

    def __init__(self, payload: Any) -> None:
        self.headers: dict[str, str] = {}
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class Session:
    def __init__(self, *payloads: Any) -> None:
        self.payloads = list(payloads)

    def post(self, url, json, headers, timeout):
        return Response(self.payloads.pop(0))


def _completion(content: str, usage: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        payload["usage"] = usage
    return payload


def test_client_counts_tokens_and_calls_the_sink_with_the_purpose() -> None:
    seen: list[LLMUsage] = []
    client = ChatCompletionsClient(
        "m",
        session=Session(
            _completion("a", {"prompt_tokens": 100, "completion_tokens": 20}),
            _completion("b", {"prompt_tokens": 50, "completion_tokens": 5}),
        ),
        usage_sink=seen.append,
        purpose="cluster_labeling",
    )
    client.complete([{"role": "user", "content": "x"}])
    client.complete([{"role": "user", "content": "y"}])

    assert client.token_usage == (150, 25)
    assert client.request_count == 2
    assert seen == [
        LLMUsage("m", 100, 20, "cluster_labeling"),
        LLMUsage("m", 50, 5, "cluster_labeling"),
    ]
    assert seen[0].total_tokens == 120


def test_missing_or_invalid_usage_is_ignored_and_sink_errors_never_break_a_call() -> None:
    def broken(_: LLMUsage) -> None:
        raise RuntimeError("db down")

    client = ChatCompletionsClient(
        "m",
        session=Session(
            _completion("a"),
            _completion("b", {"prompt_tokens": "many", "completion_tokens": 3}),
            _completion("c", {"prompt_tokens": True, "completion_tokens": 3}),
            _completion("d", {"prompt_tokens": 7, "completion_tokens": 1}),
        ),
        usage_sink=broken,
    )
    assert [client.complete([{"role": "user", "content": "x"}]) for _ in range(4)] == list("abcd")
    assert client.token_usage == (7, 1)  # only the valid report was counted


def test_cost_needs_both_prices_and_is_per_million_tokens() -> None:
    usage = LLMUsage("m", 2_000_000, 500_000)
    assert usage.cost_usd(0.5, 1.5) == 1.0 + 0.75


def test_classifier_reports_usage_as_classification() -> None:
    seen: list[LLMUsage] = []
    answer = {
        "is_problem": False,
        "confidence": 0.9,
        "intent": "none",
        "pain_quote": None,
        "products_mentioned": [],
        "severity": None,
        "reason": "launch",
    }
    classifier = OpenAICompatibleSignalClassifier(
        "m",
        session=Session(
            _completion(json.dumps(answer), {"prompt_tokens": 9, "completion_tokens": 4})
        ),
        usage_sink=seen.append,
    )
    classifier.classify("Just launched our product")
    assert seen == [LLMUsage("m", 9, 4, "classification")]
    assert classifier.token_usage == (9, 4)


def test_usage_sink_is_off_when_tracking_is_disabled() -> None:
    assert build_usage_sink(replace(base_settings, llm_usage_tracking=False)) is None
    assert callable(build_usage_sink(replace(base_settings, llm_usage_tracking=True)))


class FakeUsage:
    def __init__(self, totals: tuple[UsageTotals, ...]) -> None:
        self._totals = totals
        self.since = "unset"

    def totals(self, since=None):
        self.since = since
        return self._totals


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


def _client(reader: FakeUsage) -> TestClient:
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            usage_reader=reader,
        ),
        settings=replace(base_settings, api_key=API_KEY, environment="production"),
    )
    return TestClient(app)


def test_usage_endpoint_sums_tokens_and_cost() -> None:
    reader = FakeUsage(
        (
            UsageTotals("classification", 10, 1000, 200, 0.5),
            UsageTotals("cluster_labeling", 2, 300, 40, 0.1),
        )
    )
    response = _client(reader).get(
        "/api/v1/usage/llm", params={"since": "2026-11-01"}, headers={"X-API-Key": API_KEY}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["total_tokens"] == 1540
    assert body["total_cost_usd"] == 0.6
    assert reader.since.isoformat() == "2026-11-01T00:00:00+00:00"


def test_unpriced_usage_makes_the_total_cost_unknown_not_zero() -> None:
    reader = FakeUsage(
        (UsageTotals("classification", 1, 10, 5, None), UsageTotals("x", 1, 1, 1, 0.2))
    )
    body = _client(reader).get("/api/v1/usage/llm", headers={"X-API-Key": API_KEY}).json()
    assert body["total_cost_usd"] is None and body["total_tokens"] == 17


def test_usage_endpoint_requires_the_api_key() -> None:
    assert _client(FakeUsage(())).get("/api/v1/usage/llm").status_code == 401
