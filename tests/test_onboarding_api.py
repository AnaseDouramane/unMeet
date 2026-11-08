from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.config import settings as base_settings
from app.inbox.schemas import InboxItem
from app.llm.client import LLMRequestError
from app.net.safe_fetch import FetchError, UnsafeUrlError
from app.onboarding.service import OnboardingError, OnboardingProposal, TopicProposal
from app.reply.service import ReplyDraft, ReplyError
from app.tenancy.schemas import Role
from app.tenancy.store import InMemoryTenancyStore
from app.topics.store import InMemoryTopicStore
from app.usage.llm_usage import UsageTotals


class NoSearch:
    def search(self, query: str, limit: int):
        return ()


class FakeOnboarding:
    def __init__(self, result=None) -> None:
        self.result = result or OnboardingProposal(
            "https://acme.test/",
            "Acme cleans CRM duplicates.",
            "RevOps managers",
            ("Dedupely",),
            (
                TopicProposal(
                    "CRM duplicates", "duplicate contacts", ("pain_point",), ("HubSpot",)
                ),
                TopicProposal("Dedupe tools", "asking for a tool", ("solution_search",)),
            ),
        )
        self.calls: list[tuple[str, int | None]] = []

    def analyze(self, url, workspace_id=None):
        self.calls.append((url, workspace_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeReply:
    def __init__(self, result=None) -> None:
        self.result = result or ReplyDraft(
            "Disclosure: I work at Acme. Try merging.", True, False, "rules"
        )
        self.calls: list[dict] = []

    def draft(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeUsage:
    def __init__(self, cost: float | None = 0.0) -> None:
        self.cost = cost
        self.calls: list[tuple] = []

    def totals(self, since=None, workspace_id=None):
        self.calls.append((since, workspace_id))
        return (UsageTotals("onboarding", 1, 100, 10, self.cost),)


class FakeInbox:
    def __init__(self) -> None:
        self.item = InboxItem(
            5,
            "reddit",
            "Post",
            "https://x.test",
            "u",
            datetime(2026, 11, 1, tzinfo=UTC),
            "pain_point",
            "quote",
            (),
            2,
            1,
            "CRM",
            "why",
        )

    def get_item(self, workspace_id, signal_id):
        return self.item if (workspace_id, signal_id) == (1, 5) else None

    def signal_text(self, workspace_id, signal_id):
        return (
            "Full text of the post about duplicates"
            if (workspace_id, signal_id) == (1, 5)
            else None
        )


def build(onboarding=None, reply=None, usage=None, plan="team"):
    tenancy = InMemoryTenancyStore()
    workspace = tenancy.create_workspace("Acme", "owner@acme.test")
    tenancy.set_plan(workspace.id, plan)
    other = tenancy.create_workspace("Other", "o@other.test")
    owner = tenancy.list_members(workspace.id)[0].user_id
    tenancy.add_member(workspace.id, "mia@acme.test", Role.MEMBER)
    deps = ApiDependencies(
        analytics_reader=EmptyAnalyticsReadFacade(),
        semantic_search=NoSearch(),
        topic_store=InMemoryTopicStore(),
        tenancy=tenancy,
        inbox=FakeInbox(),
        usage_reader=usage or FakeUsage(),
        onboarding=onboarding,
        reply_assistant=reply,
    )
    app = create_app(
        deps,
        settings=replace(
            base_settings,
            api_key="op-key",
            environment="production",
            rate_limit_read_per_minute=0,
            rate_limit_write_per_minute=0,
        ),
    )
    client = TestClient(app)
    admin = {"X-API-Key": tenancy.create_api_key(workspace.id, "k")[1]}
    return client, deps, admin, workspace.id, other.id, owner


def test_analyze_returns_a_proposal_and_saves_nothing() -> None:
    service = FakeOnboarding()
    client, deps, admin, workspace, *_ = build(onboarding=service)

    response = client.post(
        "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=admin
    )

    body = response.json()
    assert response.status_code == 200
    assert body["product_summary"] == "Acme cleans CRM duplicates." and body["competitors"] == [
        "Dedupely"
    ]
    assert [t["name"] for t in body["topics"]] == ["CRM duplicates", "Dedupe tools"]
    assert service.calls == [("https://acme.test", workspace)]
    assert deps.topic_store.count(workspace) == 0


@pytest.mark.parametrize(
    "error,status,code",
    [
        (UnsafeUrlError("the host must be public"), 400, "unsafe_url"),
        (FetchError("the site answered HTTP 404"), 422, "fetch_failed"),
        (OnboardingError("the model proposed no usable topics"), 422, "analysis_failed"),
        (LLMRequestError("provider down"), 502, "llm_unavailable"),
    ],
)
def test_analyze_maps_failures_to_clear_errors(error, status, code) -> None:
    client, _, admin, *_ = build(onboarding=FakeOnboarding(error))
    response = client.post(
        "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=admin
    )
    assert response.status_code == status and response.json()["code"] == code


def test_analyze_needs_a_manager_a_configured_model_and_a_sane_url() -> None:
    client, _, admin, *_ = build(onboarding=None)
    assert (
        client.post(
            "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=admin
        ).json()["code"]
        == "llm_not_configured"
    )

    client, _, admin, *_ = build(onboarding=FakeOnboarding())
    assert (
        client.post("/api/v1/onboarding/analyze", json={"url": "https://acme.test"}).status_code
        == 401
    )
    assert (
        client.post("/api/v1/onboarding/analyze", json={"url": "x"}, headers=admin).status_code
        == 422
    )
    member_key = {"X-API-Key": "garbage"}
    assert (
        client.post(
            "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=member_key
        ).status_code
        == 401
    )


def test_analyses_are_limited_per_workspace_per_hour() -> None:
    service = FakeOnboarding()
    client, deps, admin, _, other, _ = build(onboarding=service)
    other_key = {"X-API-Key": deps.tenancy.create_api_key(other, "k")[1]}
    deps.tenancy.set_plan(other, "team")

    codes = [
        client.post(
            "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=admin
        ).status_code
        for _ in range(11)
    ]
    assert codes == [200] * 10 + [429]
    assert len(service.calls) == 10
    assert (
        client.post(
            "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=other_key
        ).status_code
        == 200
    )


def test_an_exhausted_ai_budget_blocks_analysis_with_402() -> None:
    usage = FakeUsage(cost=29.5)  # the team budget is 29.0
    client, _, admin, workspace, *_ = build(onboarding=FakeOnboarding(), usage=usage)
    response = client.post(
        "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=admin
    )
    assert response.status_code == 402 and response.json()["code"] == "llm_budget_exceeded"
    assert (
        usage.calls[0][1] == workspace and usage.calls[0][0].day == 1
    )  # this month, this workspace

    # With no prices configured the spend is unknown and nothing is blocked.
    (
        client,
        *_,
    ) = build(onboarding=FakeOnboarding(), usage=FakeUsage(cost=None))[:1]


def test_unknown_spend_does_not_block() -> None:
    client, _, admin, *_ = build(onboarding=FakeOnboarding(), usage=FakeUsage(cost=None))
    assert (
        client.post(
            "/api/v1/onboarding/analyze", json={"url": "https://acme.test"}, headers=admin
        ).status_code
        == 200
    )


def test_confirm_creates_the_edited_topics_and_remembers_the_profile() -> None:
    client, deps, admin, workspace, *_ = build()
    body = {
        "website_url": "https://acme.test",
        "product_summary": "Acme cleans CRM duplicates.",
        "topics": [
            {
                "name": "CRM duplicates",
                "description": "edited by the user",
                "intents": ["pain_point"],
                "products": [" HubSpot "],
            },
            {"name": "Dedupe tools", "description": "asking for a tool"},
        ],
    }
    response = client.post("/api/v1/onboarding/confirm", json=body, headers=admin)

    assert response.status_code == 201
    assert [t["name"] for t in response.json()["created"]] == ["CRM duplicates", "Dedupe tools"]
    assert response.json()["skipped"] == []
    stored = deps.topic_store.list(workspace)
    assert stored[0].description == "edited by the user" and stored[0].products == ("HubSpot",)
    profile = deps.tenancy.get_workspace(workspace)
    assert (profile.website_url, profile.product_summary) == (
        "https://acme.test",
        "Acme cleans CRM duplicates.",
    )
    events = deps.audit_log.list(workspace_id=workspace)
    assert [e.details.get("via") for e in events if e.action == "topic.create"] == [
        "onboarding",
        "onboarding",
    ]


def test_confirm_reports_what_did_not_fit_the_plan_or_is_invalid() -> None:
    client, _, admin, *_ = build(plan="free")  # one topic allowed
    topics = [
        {"name": "First", "description": "ok"},
        {"name": "Second", "description": "over the limit"},
    ]
    body = client.post("/api/v1/onboarding/confirm", json={"topics": topics}, headers=admin).json()
    assert [t["name"] for t in body["created"]] == ["First"]
    assert body["skipped"][0]["name"] == "Second" and "free plan" in body["skipped"][0]["reason"]

    client, _, admin, *_ = build(plan="team")
    client.post(
        "/api/v1/onboarding/confirm",
        json={"topics": [{"name": "Same", "description": "d"}]},
        headers=admin,
    )
    again = client.post(
        "/api/v1/onboarding/confirm",
        json={
            "topics": [
                {"name": "Same", "description": "d"},
                {"name": "Bad", "description": "d", "intents": ["rant"]},
            ]
        },
        headers=admin,
    ).json()
    assert next(s["reason"] for s in again["skipped"]) == "a topic with this name exists"
    assert "unknown intents" in again["skipped"][1]["reason"]
    assert (
        client.post("/api/v1/onboarding/confirm", json={"topics": []}, headers=admin).status_code
        == 422
    )


# -- reply drafts ------------------------------------------------------------------------------


def test_reply_draft_uses_the_workspace_profile_and_never_posts() -> None:
    reply = FakeReply()
    client, deps, admin, workspace, *_ = build(reply=reply)
    deps.tenancy.set_profile(workspace, "https://acme.test", "Acme cleans CRM duplicates.")

    response = client.post("/api/v1/inbox/5/reply-draft", headers=admin)

    body = response.json()
    assert response.status_code == 200 and body["draft"].startswith("Disclosure:")
    assert body["community_rules"] == "rules" and "never posts" in body["note"]
    assert reply.calls == [
        {
            "source": "reddit",
            "post_text": "Full text of the post about duplicates",
            "company": "Acme",
            "product_summary": "Acme cleans CRM duplicates.",
            "workspace_id": workspace,
        }
    ]


def test_reply_draft_only_works_for_signals_in_the_callers_inbox() -> None:
    client, deps, admin, _, other, _ = build(reply=FakeReply())
    other_key = {"X-API-Key": deps.tenancy.create_api_key(other, "k")[1]}
    assert client.post("/api/v1/inbox/5/reply-draft", headers=other_key).status_code == 404
    assert (
        client.post("/api/v1/inbox/999/reply-draft", headers=admin).json()["code"]
        == "signal_not_found"
    )
    assert client.post("/api/v1/inbox/5/reply-draft").status_code == 401


def test_reply_draft_failures_and_budget() -> None:
    client, *_ = build(reply=None)
    # Without a configured model there is nothing to call.
    _, deps, admin, *_ = build(reply=None)
    assert (
        TestClient(
            create_app(
                deps, settings=replace(base_settings, api_key="op", environment="production")
            )
        )
        .post("/api/v1/inbox/5/reply-draft", headers=admin)
        .json()["code"]
        == "llm_not_configured"
    )

    for error, status, code in [
        (ReplyError("no reply"), 422, "draft_failed"),
        (LLMRequestError("x"), 502, "llm_unavailable"),
    ]:
        client, _, admin, *_ = build(reply=FakeReply(error))
        response = client.post("/api/v1/inbox/5/reply-draft", headers=admin)
        assert (response.status_code, response.json()["code"]) == (status, code)

    client, _, admin, *_ = build(reply=FakeReply(), usage=FakeUsage(cost=100.0))
    assert client.post("/api/v1/inbox/5/reply-draft", headers=admin).status_code == 402


def test_workspace_usage_reports_month_to_date_against_the_budget() -> None:
    usage = FakeUsage(cost=1.25)
    client, _, admin, workspace, *_ = build(usage=usage)
    body = client.get("/api/v1/workspace/usage", headers=admin).json()

    assert body["spent_usd"] == 1.25 and body["llm_budget_usd"] == 29.0
    assert body["total_tokens"] == 110 and body["calls"] == 1
    assert body["month_start"].startswith(datetime.now(UTC).strftime("%Y-%m-01"))
    assert usage.calls[0][1] == workspace

    client, _, admin, *_ = build(usage=FakeUsage(cost=None))
    assert client.get("/api/v1/workspace/usage", headers=admin).json()["spent_usd"] is None
    assert client.get("/api/v1/workspace/usage").status_code == 401


def test_confirm_stores_the_keywords_and_the_topic_api_returns_them() -> None:
    client, deps, admin, workspace, *_ = build()
    body = {
        "topics": [
            {
                "name": "Dupes",
                "description": "d",
                "keywords": ["merge duplicate contacts", " hubspot dedupe "],
            }
        ]
    }

    created = client.post("/api/v1/onboarding/confirm", json=body, headers=admin).json()["created"][
        0
    ]

    assert created["keywords"] == ["merge duplicate contacts", "hubspot dedupe"]
    assert deps.topic_store.list(workspace)[0].keywords == (
        "merge duplicate contacts",
        "hubspot dedupe",
    )
    assert (
        client.get("/api/v1/topics", headers=admin).json()["items"][0]["keywords"]
        == created["keywords"]
    )
    bad = {"topics": [{"name": "Bad", "description": "d", "keywords": ['say "hi"']}]}
    skipped = client.post("/api/v1/onboarding/confirm", json=bad, headers=admin).json()["skipped"]
    assert "keywords" in skipped[0]["reason"]
