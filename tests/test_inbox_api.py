from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.config import settings as base_settings
from app.inbox.schemas import InboxItem
from app.tenancy.store import InMemoryTenancyStore
from app.topics.schemas import TopicDefinition
from app.topics.store import InMemoryTopicStore


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


class FakeInbox:
    """Two workspaces' signals; mimics the repository's visibility rules."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.states: dict[tuple[int, int], tuple[str, str | None]] = {}
        self.visible = {1: {10, 11}, 2: {20}}

    def _item(self, workspace_id: int, signal_id: int) -> InboxItem:
        state, note = self.states.get((workspace_id, signal_id), ("new", None))
        return InboxItem(
            signal_id=signal_id,
            source="reddit",
            title=f"Post {signal_id}",
            url="https://example.test",
            author="u",
            published_at=datetime(2026, 11, 1, tzinfo=UTC),
            intent="pain_point",
            pain_quote="quote",
            products_mentioned=("HubSpot",),
            severity=2,
            topic_id=1,
            topic_name="CRM",
            relevance_reason="why",
            state=state,
            note=note,
        )

    def list_items(self, workspace_id, topic_id=None, state="new", limit=50, offset=0):
        self.calls.append(("list", workspace_id, topic_id, state, limit, offset))
        items = [self._item(workspace_id, s) for s in sorted(self.visible[workspace_id])]
        return tuple(i for i in items if state == "all" or i.state == state)

    def counts(self, workspace_id):
        counts = {"new": 0, "relevant": 0, "not_relevant": 0, "replied": 0}
        for s in self.visible[workspace_id]:
            counts[self._item(workspace_id, s).state] += 1
        return counts

    def get_item(self, workspace_id, signal_id):
        return (
            self._item(workspace_id, signal_id) if signal_id in self.visible[workspace_id] else None
        )

    def set_state(self, workspace_id, signal_ids, state, note=None, topic_id=None, user_id=None):
        self.calls.append(("set", workspace_id, tuple(signal_ids), state, note, topic_id, user_id))
        changed = [s for s in signal_ids if s in self.visible[workspace_id]]
        for s in changed:
            self.states[(workspace_id, s)] = (state, note)
        return len(changed)

    def feedback_examples(self, workspace_id, topic_id, per_label=3):
        return ()


@pytest.fixture
def env():
    inbox, tenancy, topics = FakeInbox(), InMemoryTenancyStore(), InMemoryTopicStore()
    acme = tenancy.create_workspace("Acme", "a@acme.test").id
    beta = tenancy.create_workspace("Beta", "b@beta.test").id
    topics.create(TopicDefinition(name="CRM", description="crm"), acme)
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(),
            semantic_search=NoSearch(),
            topic_store=topics,
            tenancy=tenancy,
            inbox=inbox,
        ),
        settings=replace(
            base_settings,
            api_key=None,
            environment="production",
            rate_limit_read_per_minute=0,
            rate_limit_write_per_minute=0,
        ),
    )
    client = TestClient(app)
    keys = {
        "acme": {"X-API-Key": tenancy.create_api_key(acme, "k")[1]},
        "beta": {"X-API-Key": tenancy.create_api_key(beta, "k")[1]},
    }
    return client, inbox, keys


def test_lists_only_the_callers_signals_with_filters_passed_through(env) -> None:
    client, inbox, keys = env
    body = client.get(
        "/api/v1/inbox", params={"topic_id": 1, "state": "all", "limit": 5}, headers=keys["acme"]
    ).json()

    assert [i["signal_id"] for i in body["items"]] == [10, 11]
    assert body["items"][0]["relevance_reason"] == "why" and body["items"][0]["state"] == "new"
    assert inbox.calls[-1] == ("list", 1, 1, "all", 5, 0)
    assert [
        i["signal_id"] for i in client.get("/api/v1/inbox", headers=keys["beta"]).json()["items"]
    ] == [20]


def test_inbox_requires_authentication_and_validates_filters(env) -> None:
    client, _, keys = env
    assert client.get("/api/v1/inbox").status_code == 401
    assert client.get("/api/v1/inbox/counts").status_code == 401
    assert (
        client.post(
            "/api/v1/inbox/state", json={"signal_ids": [10], "state": "relevant"}
        ).status_code
        == 401
    )
    assert (
        client.get("/api/v1/inbox", params={"state": "bogus"}, headers=keys["acme"]).status_code
        == 422
    )
    assert (
        client.get("/api/v1/inbox", params={"limit": 500}, headers=keys["acme"]).status_code == 422
    )


def test_triage_updates_counts_and_the_filtered_views(env) -> None:
    client, _, keys = env
    headers = keys["acme"]

    update = client.post(
        "/api/v1/inbox/state",
        json={"signal_ids": [10, 11], "state": "relevant", "note": "call them"},
        headers=headers,
    )
    assert update.json() == {"updated": 2}
    assert client.get("/api/v1/inbox/counts", headers=headers).json() == {
        "new": 0,
        "relevant": 2,
        "not_relevant": 0,
        "replied": 0,
    }
    assert client.get("/api/v1/inbox", headers=headers).json()["items"] == []
    relevant = client.get("/api/v1/inbox", params={"state": "relevant"}, headers=headers).json()[
        "items"
    ]
    assert [(i["signal_id"], i["note"]) for i in relevant] == [(10, "call them"), (11, "call them")]


def test_other_workspaces_signals_are_not_updated_and_the_count_says_so(env) -> None:
    client, inbox, keys = env
    response = client.post(
        "/api/v1/inbox/state",
        json={"signal_ids": [10, 20, 999], "state": "not_relevant"},
        headers=keys["acme"],
    )
    assert response.json() == {"updated": 1}
    assert (2, 20) not in inbox.states and (1, 10) in inbox.states


def test_state_update_validation(env) -> None:
    client, _, keys = env
    headers = keys["acme"]
    assert (
        client.post(
            "/api/v1/inbox/state", json={"signal_ids": [], "state": "relevant"}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/inbox/state", json={"signal_ids": [1], "state": "maybe"}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/inbox/state",
            json={"signal_ids": list(range(201)), "state": "relevant"},
            headers=headers,
        ).status_code
        == 422
    )
    # A topic from another workspace cannot be attached.
    other_topic = client.post(
        "/api/v1/inbox/state",
        json={"signal_ids": [10], "state": "relevant", "topic_id": 999},
        headers=headers,
    )
    assert other_topic.status_code == 404 and other_topic.json()["code"] == "topic_not_found"


def test_the_actor_is_recorded_for_logged_in_users_and_the_topic_is_kept(env) -> None:
    client, inbox, keys = env
    client.post(
        "/api/v1/inbox/state",
        json={"signal_ids": [10], "state": "relevant", "topic_id": 1},
        headers=keys["acme"],
    )
    call = inbox.calls[-1]
    assert call[:4] == ("set", 1, (10,), "relevant") and call[5] == 1
    assert call[6] is None  # API keys have no user
