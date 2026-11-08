from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import ApiDependencies, EmptyAnalyticsReadFacade
from app.config import settings as base_settings
from app.demo.service import MAX_SIGNALS, DemoBusyError, DemoService, canonical_key
from app.llm.client import LLMRequestError
from app.net.safe_fetch import FetchError, UnsafeUrlError
from app.onboarding.service import OnboardingError, OnboardingProposal, TopicProposal
from app.signals.schemas import Signal, SignalQuery

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


def proposal(topics=2):
    return OnboardingProposal(
        "https://acme.test/",
        "Acme cleans CRM duplicates.",
        "RevOps",
        ("Dedupely",),
        tuple(
            TopicProposal(f"Topic {i}", f"description {i}", ("pain_point",), ())
            for i in range(topics)
        ),
    )


def signal(i, similarity, day=1, **kw):
    values = dict(
        id=i,
        source="reddit",
        external_id=str(i),
        title=f"Post {i}",
        url=f"https://x.test/{i}",
        author=f"user{i}",
        published_at=NOW - timedelta(days=day),
        intent="pain_point",
        pain_quote=f"quote {i}",
        products_mentioned=(),
        severity=2,
        confidence=0.9,
        similarity=similarity,
    )
    values.update(kw)
    return Signal(**values)


class Onboarding:
    def __init__(self, result=None) -> None:
        self.result = result or proposal()
        self.urls: list[str] = []

    def analyze(self, url, workspace_id=None):
        self.urls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Reader:
    def __init__(self, by_topic=None) -> None:
        self.by_topic = by_topic or {}
        self.calls: list[tuple[SignalQuery, str | None]] = []

    def find(self, query, topic=None):
        self.calls.append((query, topic))
        return self.by_topic.get(topic, ())


def service(onboarding=None, reader=None, clock=lambda: NOW, **kw):
    return DemoService(onboarding or Onboarding(), reader or Reader(), clock=clock, **kw)


def test_best_signals_across_topics_are_merged_ranked_and_capped_without_authors() -> None:
    reader = Reader(
        {
            "description 0": [signal(1, 0.9), signal(2, 0.5), signal(3, 0.8), signal(4, 0.7)],
            "description 1": [
                signal(2, 0.95),
                signal(5, 0.6),
                signal(6, 0.4),
            ],  # 2 appears twice: best kept
        }
    )
    result = service(reader=reader).run("https://acme.test")

    assert [s.title for s in result.signals] == ["Post 2", "Post 1", "Post 3", "Post 4", "Post 5"]
    assert len(result.signals) == MAX_SIGNALS and result.signals[0].similarity == 0.95
    assert result.topics == ("Topic 0", "Topic 1") and result.competitors == ("Dedupely",)
    assert not hasattr(result.signals[0], "author") and "user" not in str(result)
    assert all(q.limit == MAX_SIGNALS for q, _ in reader.calls)


def test_ties_prefer_newer_posts() -> None:
    reader = Reader({"description 0": [signal(1, 0.7, day=5), signal(2, 0.7, day=1)]})
    result = service(Onboarding(proposal(1)), reader).run("https://acme.test")
    assert [s.title for s in result.signals] == ["Post 2", "Post 1"]


def test_an_empty_corpus_still_returns_the_analysis() -> None:
    result = service().run("https://acme.test")
    assert result.signals == () and result.product_summary.startswith("Acme")


def test_results_are_cached_per_site_for_a_day_and_cache_hits_are_free() -> None:
    onboarding, clock = Onboarding(), [NOW]
    demo = service(onboarding, clock=lambda: clock[0], daily_limit=1)

    first = demo.run("https://Acme.test/pricing/")
    assert demo.run("https://acme.test/pricing") is first  # same site, free: cap not touched
    assert onboarding.urls == ["https://Acme.test/pricing/"]
    with pytest.raises(DemoBusyError):
        demo.run("https://other.test")  # the single daily analysis is used

    clock[0] = NOW + timedelta(hours=25)  # new day and the cache expired
    assert demo.run("https://acme.test/pricing") is not first
    assert canonical_key("HTTPS://Acme.TEST/a/b/") == "acme.test/a/b"


def test_the_daily_cap_resets_each_utc_day_and_failures_are_not_cached() -> None:
    onboarding, clock = Onboarding(OnboardingError("too little text")), [NOW]
    demo = service(onboarding, clock=lambda: clock[0], daily_limit=2)
    for _ in range(2):
        with pytest.raises(OnboardingError):
            demo.run("https://a.test")
    with pytest.raises(DemoBusyError):
        demo.run("https://a.test")  # failed analyses also spent the cap: they cost tokens
    clock[0] = NOW + timedelta(days=1)
    onboarding.result = proposal()
    assert demo.run("https://a.test").topics


# -- API -------------------------------------------------------------------------------------


class NoSearch:
    def search(self, query, limit):
        return ()


def client(demo, enabled=True, per_visitor=2):
    app = create_app(
        ApiDependencies(
            analytics_reader=EmptyAnalyticsReadFacade(), semantic_search=NoSearch(), demo=demo
        ),
        settings=replace(
            base_settings,
            demo_enabled=enabled,
            demo_per_visitor_per_hour=per_visitor,
            environment="production",
            api_key="op",
            rate_limit_write_per_minute=0,
        ),
    )
    return TestClient(app)


def test_the_demo_is_off_unless_enabled_and_needs_no_credentials_when_on() -> None:
    reader = Reader({"description 0": [signal(1, 0.9)]})
    demo = service(Onboarding(proposal(1)), reader)

    off = client(demo, enabled=False).post("/api/v1/demo", json={"url": "https://acme.test"})
    assert off.status_code == 503 and off.json()["code"] == "demo_disabled"
    assert (
        client(None).post("/api/v1/demo", json={"url": "https://acme.test"}).json()["code"]
        == "demo_disabled"
    )

    on = client(demo).post("/api/v1/demo", json={"url": "https://acme.test"})
    body = on.json()
    assert on.status_code == 200 and body["topics"] == ["Topic 0"]
    assert body["signals"][0]["quote"] == "quote 1" and "author" not in str(body)


def test_each_visitor_gets_a_few_runs_per_hour() -> None:
    c = client(service(), per_visitor=2)
    codes = [
        c.post("/api/v1/demo", json={"url": f"https://site{i}.test"}).status_code for i in range(3)
    ]
    assert codes == [200, 200, 429]
    limited = c.post("/api/v1/demo", json={"url": "https://site9.test"})
    assert (
        limited.json()["code"] == "rate_limited"
        and limited.json()["details"]["retry_after_seconds"] > 0
    )
    # Another visitor (different API key identity) is not affected.
    other = c.post(
        "/api/v1/demo", json={"url": "https://site1.test"}, headers={"X-API-Key": "someone-else"}
    )
    assert other.status_code == 200


@pytest.mark.parametrize(
    "error,status,code",
    [
        (UnsafeUrlError("the host must be public"), 400, "unsafe_url"),
        (FetchError("the site answered HTTP 404"), 422, "fetch_failed"),
        (OnboardingError("no usable topics"), 422, "analysis_failed"),
        (LLMRequestError("down"), 502, "llm_unavailable"),
    ],
)
def test_failures_become_clear_errors(error, status, code) -> None:
    response = client(service(Onboarding(error))).post(
        "/api/v1/demo", json={"url": "https://acme.test"}
    )
    assert (response.status_code, response.json()["code"]) == (status, code)


def test_the_daily_cap_answers_503_and_bad_input_422() -> None:
    c = client(service(daily_limit=1), per_visitor=10)
    assert c.post("/api/v1/demo", json={"url": "https://a.test"}).status_code == 200
    busy = c.post("/api/v1/demo", json={"url": "https://b.test"})
    assert (busy.status_code, busy.json()["code"]) == (503, "demo_busy")
    assert c.post("/api/v1/demo", json={"url": "x"}).status_code == 422
