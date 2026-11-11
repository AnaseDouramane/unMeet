from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade, EmptyInbox
from app.config import settings as base_settings
from app.ingestion.runs import IngestionRun, InMemoryRunStore
from app.tenancy.store import InMemoryTenancyStore
from app.topics.schemas import TopicDefinition
from app.topics.store import InMemoryTopicStore
from app.usage.llm_usage import UsageTotals

T0 = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


class NoSearch:
    def search(self, query, limit):
        return ()


class Inbox(EmptyInbox):
    def __init__(self, counts):
        self._counts = counts

    def counts(self, workspace_id):
        return {"new": 4, "relevant": 2, "not_relevant": 1, "replied": 1}

    def topic_counts(self, workspace_id):
        return self._counts


class Usage:
    def totals(self, since=None, workspace_id=None):
        return (
            UsageTotals("onboarding", 2, 1000, 500, 0.01),
            UsageTotals("reply_draft", 3, 300, 200, 0.002),
        )


def build():
    tenancy, topics, runs = InMemoryTenancyStore(), InMemoryTopicStore(), InMemoryRunStore()
    workspace = tenancy.create_workspace("Acme", "o@acme.test")
    tenancy.set_profile(workspace.id, "https://acme.test", "Acme cleans CRM data.")
    crm = topics.create(
        TopicDefinition(
            name="CRM", description="dupes", keywords=("merge contacts",), products=("HubSpot",)
        ),
        workspace.id,
    )
    other = tenancy.create_workspace("Other", "o@other.test")
    topics.create(TopicDefinition(name="Secret", description="theirs"), other.id)
    runs.record(
        IngestionRun(
            "hackernews_topics",
            T0,
            T0 + timedelta(seconds=95.4),
            "ok",
            acquired=60,
            gated_out=8,
            llm_requests=14,
            problems=5,
            matched=2,
            workspace_id=workspace.id,
        )
    )
    runs.record(
        IngestionRun(
            "hackernews_topics",
            T0 + timedelta(hours=1),
            T0 + timedelta(hours=1),
            "ok",
            acquired=99,
            workspace_id=other.id,
        )
    )
    runs.record(
        IngestionRun(
            "hackernews_topics",
            T0 - timedelta(days=1),
            T0 - timedelta(days=1),
            "error",
            error="429",
        )
    )
    deps = ApiDependencies(
        analytics_reader=EmptyAnalyticsReadFacade(),
        semantic_search=NoSearch(),
        tenancy=tenancy,
        topic_store=topics,
        runs=runs,
        inbox=Inbox({crm.id: (3, 2)}),
        usage_reader=Usage(),
    )
    app = create_app(
        deps,
        settings=replace(
            base_settings, api_key="op", environment="production", rate_limit_read_per_minute=0
        ),
    )
    key = {"X-API-Key": tenancy.create_api_key(workspace.id, "k")[1]}
    return TestClient(app), key, crm.id


def test_the_overview_has_the_profile_topics_with_counts_runs_and_usage() -> None:
    client, key, crm_id = build()
    body = client.get("/api/v1/workspace/overview", headers=key).json()

    assert body["workspace"] == {
        "name": "Acme",
        "plan": "free",
        "website_url": "https://acme.test",
        "product_summary": "Acme cleans CRM data.",
    }
    assert body["inbox"] == {"new": 4, "relevant": 2, "not_relevant": 1, "replied": 1}
    assert body["topics"] == [
        {
            "id": crm_id,
            "name": "CRM",
            "description": "dupes",
            "keywords": ["merge contacts"],
            "products": ["HubSpot"],
            "matched": 3,
            "new": 2,
        }
    ]  # the other workspace's topic is not here
    latest, older = body["runs"]  # its own run and the shared one; not the other workspace's
    assert (latest["acquired"], latest["gated_out"], latest["llm_requests"], latest["matched"]) == (
        60,
        8,
        14,
        2,
    )
    assert (
        latest["duration_seconds"] == 95.4
        and older["status"] == "error"
        and older["error"] == "429"
    )
    assert body["usage"] == {
        "calls": 5,
        "total_tokens": 2000,
        "spent_usd": 0.012,
        "llm_budget_usd": 1.0,
    }


def test_the_overview_requires_a_credential() -> None:
    client, _, _ = build()
    assert client.get("/api/v1/workspace/overview").status_code == 401


def test_topics_without_matches_show_zero() -> None:
    client, key, _ = build()
    client.app.state.dependencies.inbox._counts = {}
    topic = client.get("/api/v1/workspace/overview", headers=key).json()["topics"][0]
    assert (topic["matched"], topic["new"]) == (0, 0)


def test_a_run_without_statistics_is_recorded_as_an_error() -> None:
    run = IngestionRun.from_stats("hn", T0, T0, None, None)
    assert run.status == "error" and run.error == "no statistics" and run.acquired == 0
