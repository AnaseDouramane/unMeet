from dataclasses import replace

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.audit.log import InMemoryAuditLog
from app.config import settings as base_settings

API_KEY = "k-1"


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


class FakePrivacy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def erase_author(self, source: str, author: str) -> int:
        self.calls.append((source, author))
        return 3


def _client():
    privacy, audit = FakePrivacy(), InMemoryAuditLog()
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            privacy=privacy,
            audit_log=audit,
        ),
        settings=replace(base_settings, api_key=API_KEY, environment="production"),
    )
    return TestClient(app), privacy, audit


def test_erasure_requires_the_key_and_audits_without_the_username() -> None:
    client, privacy, audit = _client()
    body = {"source": "Reddit", "author": "some_user"}

    assert client.post("/api/v1/privacy/erasure", json=body).status_code == 401
    response = client.post("/api/v1/privacy/erasure", json=body, headers={"X-API-Key": API_KEY})

    assert response.status_code == 200 and response.json() == {"deleted_items": 3}
    assert privacy.calls == [("Reddit", "some_user")]
    (event,) = audit.list()
    assert event.action == "privacy.erasure"
    assert event.details == {"source": "reddit", "deleted_items": 3}
    assert "some_user" not in str(event)


def test_erasure_rejects_blank_values() -> None:
    client, privacy, _ = _client()
    headers = {"X-API-Key": API_KEY}
    assert (
        client.post(
            "/api/v1/privacy/erasure", json={"source": "  ", "author": "x"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post("/api/v1/privacy/erasure", json={"source": "r"}, headers=headers).status_code
        == 422
    )
    assert privacy.calls == []
