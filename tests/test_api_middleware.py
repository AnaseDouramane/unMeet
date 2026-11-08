import json
import logging
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.api.middleware import SlidingWindowRateLimiter, client_identity
from app.config import settings as base_settings
from app.tenancy.store import InMemoryTenancyStore
from app.topics.store import InMemoryTopicStore
from app.utils.logging import JsonFormatter, configure_logging

API_KEY = "test-key-123"
OPERATOR = {"X-API-Key": API_KEY}


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


def team_tenancy() -> InMemoryTenancyStore:
    """A tenancy store whose default workspace is on the team plan (tests act as the operator)."""
    tenancy = InMemoryTenancyStore()
    tenancy.set_plan(tenancy.ensure_default_workspace().id, "team")
    return tenancy


def _client(**overrides) -> TestClient:
    tenancy = team_tenancy()
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            topic_store=InMemoryTopicStore(),
            tenancy=tenancy,
        ),
        settings=replace(base_settings, api_key=API_KEY, environment="production", **overrides),
    )
    client = TestClient(app)
    client.tenancy = tenancy  # type: ignore[attr-defined]
    return client


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_limiter_blocks_after_the_limit_and_recovers_when_the_window_slides() -> None:
    clock = Clock()
    limiter = SlidingWindowRateLimiter(window_seconds=60, clock=clock)

    assert [limiter.check("a", 2).allowed for _ in range(3)] == [True, True, False]
    blocked = limiter.check("a", 2)
    assert blocked.retry_after_seconds == 61 or blocked.retry_after_seconds == 60
    assert limiter.check("b", 2).allowed  # other keys are independent
    clock.now = 61
    assert limiter.check("a", 2).allowed


def test_limiter_prunes_idle_keys() -> None:
    clock = Clock()
    limiter = SlidingWindowRateLimiter(window_seconds=10, clock=clock)
    for index in range(50):
        limiter.check(f"k{index}", 5)
    clock.now = 100
    limiter.check("new", 5)
    assert set(limiter._hits) == {"new"}


def test_read_limit_returns_429_with_retry_after_and_headers() -> None:
    client = _client(rate_limit_read_per_minute=2)

    first = client.get("/api/v1/signals", headers=OPERATOR)
    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert first.headers["X-RateLimit-Remaining"] == "1"
    assert client.get("/api/v1/signals", headers=OPERATOR).status_code != 429
    blocked = client.get("/api/v1/signals", headers=OPERATOR)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.json()["code"] == "rate_limited"


def test_health_and_options_are_never_limited() -> None:
    client = _client(rate_limit_read_per_minute=1, rate_limit_write_per_minute=1)
    for _ in range(5):
        assert client.get("/health").status_code == 200
        assert (
            client.options(
                "/api/v1/signals",
                headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
            ).status_code
            == 200
        )


def test_writes_have_their_own_stricter_budget() -> None:
    client = _client(rate_limit_read_per_minute=100, rate_limit_write_per_minute=2)
    headers = {"X-API-Key": API_KEY}
    body = {"name": "t", "intents": ["pain_point"]}

    codes = [
        client.post("/api/v1/topics", json={**body, "name": f"t{i}"}, headers=headers).status_code
        for i in range(3)
    ]

    assert codes[:2] == [201, 201]
    assert codes[2] == 429
    assert client.get("/api/v1/topics", headers=OPERATOR).status_code == 200  # reads unaffected


def test_limit_zero_disables_limiting() -> None:
    client = _client(rate_limit_read_per_minute=0)
    assert all(
        client.get("/api/v1/signals", headers=OPERATOR).status_code == 200 for _ in range(10)
    )


def test_limits_are_per_api_key_and_429_keeps_cors_headers() -> None:
    client = _client(rate_limit_read_per_minute=1)
    workspace = client.tenancy.ensure_default_workspace().id  # type: ignore[attr-defined]
    _, one = client.tenancy.create_api_key(workspace, "one")  # type: ignore[attr-defined]
    _, two = client.tenancy.create_api_key(workspace, "two")  # type: ignore[attr-defined]

    assert client.get("/api/v1/signals", headers={"X-API-Key": one}).status_code == 200
    assert client.get("/api/v1/signals", headers={"X-API-Key": two}).status_code == 200
    blocked = client.get(
        "/api/v1/signals", headers={"X-API-Key": one, "Origin": "http://localhost:3000"}
    )
    assert blocked.status_code == 429
    assert blocked.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_request_id_is_generated_or_echoed() -> None:
    client = _client()
    assert len(client.get("/health").headers["X-Request-ID"]) == 32
    assert (
        client.get("/health", headers={"X-Request-ID": "abc-1"}).headers["X-Request-ID"] == "abc-1"
    )


def test_access_log_has_request_fields_but_never_the_api_key(caplog) -> None:
    client = _client()
    with caplog.at_level(logging.INFO, logger="unmeet.api"):
        client.get("/health", headers={"X-API-Key": API_KEY, "X-Request-ID": "rid-9"})
    record = next(r for r in caplog.records if r.name == "unmeet.api")
    assert (record.request_id, record.method, record.path, record.status) == (
        "rid-9",
        "GET",
        "/health",
        200,
    )
    assert record.client.startswith("key:") and API_KEY not in record.client
    assert API_KEY not in caplog.text


def _request(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 1234),
    }
    return Request(scope)


def test_client_identity_uses_forwarded_for_only_when_trusted() -> None:
    request = _request({"X-Forwarded-For": "203.0.113.7, 10.0.0.1"})
    assert client_identity(request, trust_proxy=False) == "ip:10.0.0.1"
    assert client_identity(request, trust_proxy=True) == "ip:203.0.113.7"
    bearer = _request({"Authorization": "Bearer secret"})
    assert client_identity(bearer, trust_proxy=False).startswith("key:")


def test_json_formatter_keeps_extra_fields_and_exceptions() -> None:
    record = logging.LogRecord("unmeet.x", logging.ERROR, "f.py", 1, "boom %s", ("now",), None)
    record.request_id = "r1"
    try:
        raise ValueError("bad")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "boom now" and payload["level"] == "ERROR"
    assert payload["request_id"] == "r1"
    assert "ValueError: bad" in payload["exception"]
    assert "args" not in payload and "msg" not in payload


@pytest.mark.parametrize("fmt,expected", [("json", JsonFormatter), ("text", logging.Formatter)])
def test_configure_logging_selects_the_formatter(fmt, expected) -> None:
    configure_logging(fmt)
    formatter = logging.getLogger().handlers[0].formatter
    assert type(formatter) is expected
