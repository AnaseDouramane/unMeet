from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.config import settings
from app.signals.schemas import SignalQuery
from app.topics.store import InMemoryTopicStore

API_KEY = "test-key-123"


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


class RecordingReader:
    def __init__(self) -> None:
        self.calls: list[tuple[SignalQuery, str | None]] = []

    def find(self, query: SignalQuery, topic: str | None = None):
        self.calls.append((query, topic))
        return ()


def _client(api_key: str | None = API_KEY, environment: str = "production"):
    reader = RecordingReader()
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            signal_reader=reader,
            topic_store=InMemoryTopicStore(),
        ),
        settings=replace(settings, api_key=api_key, environment=environment),
    )
    return TestClient(app), reader


TOPIC = {
    "name": "CRM hygiene",
    "description": "duplicate contacts in the CRM",
    "intents": ["competitor_complaint", "solution_search"],
    "products": [" HubSpot "],
    "min_severity": 2,
    "webhook_url": "https://api.clay.com/v3/sources/webhook/abc",
}


def test_create_list_and_delete_topics_with_api_key() -> None:
    client, _ = _client()
    headers = {"Authorization": f"Bearer {API_KEY}"}

    created = client.post("/api/v1/topics", json=TOPIC, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["products"] == ["HubSpot"]
    assert body["has_webhook"] is True
    assert "webhook_url" not in body

    listed = client.get("/api/v1/topics").json()["items"]
    assert [topic["name"] for topic in listed] == ["CRM hygiene"]

    duplicate = client.post("/api/v1/topics", json=TOPIC, headers=headers)
    assert duplicate.status_code == 409

    assert client.delete(f"/api/v1/topics/{body['id']}", headers={"X-API-Key": API_KEY}).status_code == 204
    assert client.delete(f"/api/v1/topics/{body['id']}", headers=headers).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"X-API-Key": ""}])
def test_writes_require_a_valid_api_key(headers) -> None:
    client, _ = _client()

    assert client.post("/api/v1/topics", json=TOPIC, headers=headers).status_code == 401


def test_writes_fail_closed_without_a_configured_key_outside_development() -> None:
    client, _ = _client(api_key=None, environment="production")

    response = client.post("/api/v1/topics", json=TOPIC)

    assert response.status_code == 503
    assert response.json()["code"] == "auth_not_configured"


def test_development_allows_writes_without_a_key() -> None:
    client, _ = _client(api_key=None, environment="development")

    assert client.post("/api/v1/topics", json=TOPIC).status_code == 201


def test_invalid_topics_return_400() -> None:
    client, _ = _client()
    headers = {"X-API-Key": API_KEY}

    unsafe = client.post(
        "/api/v1/topics", json={**TOPIC, "webhook_url": "http://10.0.0.1/hook"}, headers=headers
    )
    empty = client.post("/api/v1/topics", json={"name": "Nothing"}, headers=headers)

    assert unsafe.status_code == 400 and "webhook_url" in unsafe.json()["message"]
    assert empty.status_code == 400


def test_topic_signals_reuse_the_topic_filters() -> None:
    client, reader = _client()
    topic_id = client.post("/api/v1/topics", json=TOPIC, headers={"X-API-Key": API_KEY}).json()["id"]

    response = client.get(f"/api/v1/topics/{topic_id}/signals", params={"limit": 10})

    assert response.status_code == 200
    query, description = reader.calls[0]
    assert description == "duplicate contacts in the CRM"
    assert query.intents == ("competitor_complaint", "solution_search")
    assert query.products == ("HubSpot",)
    assert query.min_severity == 2
    assert query.limit == 10
    assert query.topic_id == topic_id
    assert client.get("/api/v1/topics/999/signals").status_code == 404
