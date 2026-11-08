from dataclasses import replace

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.audit.log import AuditEvent, InMemoryAuditLog
from app.config import settings as base_settings
from app.tenancy.store import InMemoryTenancyStore
from app.topics.store import InMemoryTopicStore

API_KEY = "test-key-123"
TOPIC = {"name": "CRM hygiene", "intents": ["pain_point"], "webhook_url": "https://x.example/hook"}


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


class BrokenAudit:
    def record(self, event):
        raise RuntimeError("audit store down")

    def list(self, limit=100, offset=0):
        return ()


def team_tenancy() -> InMemoryTenancyStore:
    """A tenancy store whose default workspace is on the team plan (tests act as the operator)."""
    tenancy = InMemoryTenancyStore()
    tenancy.set_plan(tenancy.ensure_default_workspace().id, "team")
    return tenancy


def _client(audit=None):
    audit = audit or InMemoryAuditLog()
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            topic_store=InMemoryTopicStore(),
            tenancy=team_tenancy(),
            audit_log=audit,
        ),
        settings=replace(base_settings, api_key=API_KEY, environment="production"),
    )
    return TestClient(app), audit


def test_topic_writes_are_audited_without_secrets() -> None:
    client, audit = _client()
    headers = {"X-API-Key": API_KEY, "X-Request-ID": "req-1"}

    topic_id = client.post("/api/v1/topics", json=TOPIC, headers=headers).json()["id"]
    assert client.delete(f"/api/v1/topics/{topic_id}", headers=headers).status_code == 204

    delete, create = audit.list()
    assert (create.action, create.resource_type, create.resource_id) == (
        "topic.create",
        "topic",
        str(topic_id),
    )
    assert create.details == {"name": "CRM hygiene", "has_webhook": True}
    assert "x.example" not in str(create.details)  # the webhook URL itself is never stored
    assert create.request_id == "req-1"
    assert create.actor.startswith("key:") and API_KEY not in create.actor
    assert delete.action == "topic.delete"


def test_failed_or_rejected_writes_are_not_audited() -> None:
    client, audit = _client()
    assert client.post("/api/v1/topics", json=TOPIC).status_code == 401  # no key
    assert client.delete("/api/v1/topics/99", headers={"X-API-Key": API_KEY}).status_code == 404
    assert (
        client.post(
            "/api/v1/topics", json={"name": "x"}, headers={"X-API-Key": API_KEY}
        ).status_code
        == 400
    )
    assert audit.list() == ()


def test_a_broken_audit_store_does_not_fail_the_write(caplog) -> None:
    client, _ = _client(BrokenAudit())
    response = client.post("/api/v1/topics", json=TOPIC, headers={"X-API-Key": API_KEY})
    assert response.status_code == 201
    assert "audit write failed" in caplog.text


def test_audit_endpoint_requires_the_key_and_paginates_newest_first() -> None:
    client, audit = _client()
    for index in range(3):
        audit.record(AuditEvent("key:abc", "topic.create", "topic", str(index)))

    assert client.get("/api/v1/audit").status_code == 401
    body = client.get("/api/v1/audit", params={"limit": 2}, headers={"X-API-Key": API_KEY}).json()
    assert [e["resource_id"] for e in body["items"]] == ["2", "1"]
    second = client.get(
        "/api/v1/audit", params={"limit": 2, "offset": 2}, headers={"X-API-Key": API_KEY}
    ).json()
    assert [e["resource_id"] for e in second["items"]] == ["0"]
