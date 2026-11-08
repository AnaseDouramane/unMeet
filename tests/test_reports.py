from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.analytics.schemas import ClusterRankingItem
from app.api.app import create_app
from app.api.dependencies import (
    ApiDependencies,
    ClusterDetail,
    EmptyAnalyticsReadFacade,
    PublicDocument,
)
from app.config import settings as base_settings
from app.reports.service import (
    MAX_QUOTE_CHARS,
    MAX_QUOTES,
    build_report,
    is_publishable,
    render_markdown,
)

DAY = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def cluster(
    cluster_id=1, label="Sales teams clean CRM duplicates by hand", count=12, score=0.5, **kw
):
    values = dict(
        cluster_id=cluster_id,
        label=label,
        rank=1,
        opportunity_score=score,
        document_count=count,
        growth_rate=0.25,
        status="rising",
        source_count=3,
        average_problem_confidence=0.9,
        keywords=("crm",),
    )
    values.update(kw)
    return ClusterRankingItem(**values)


def doc(i, quote="I spend hours deduping contacts", **kw):
    values = dict(
        id=i,
        source="reddit",
        title=f"Title {i}",
        body="body text that is long",
        url=f"https://x.test/{i}",
        author=f"user{i}",
        published_at=DAY,
        problem_confidence=0.9,
        pain_quote=quote,
    )
    values.update(kw)
    return PublicDocument(**values)


def test_only_clusters_with_enough_evidence_and_a_label_are_publishable() -> None:
    assert is_publishable(cluster(count=5), 5) and not is_publishable(cluster(count=4), 5)
    assert not is_publishable(cluster(label="   "), 5)


def test_quotes_prefer_the_verified_quote_dedupe_urls_and_are_capped() -> None:
    docs = [doc(i) for i in range(10)] + [doc(0)]  # a repeated URL
    report = build_report(cluster(), tuple(docs))
    assert len(report.quotes) == MAX_QUOTES
    assert len({q.url for q in report.quotes}) == MAX_QUOTES
    assert report.quotes[0].text == "I spend hours deduping contacts"
    assert not hasattr(report.quotes[0], "author")


def test_falls_back_to_the_title_and_truncates_long_text_and_skips_empty() -> None:
    report = build_report(
        cluster(),
        (
            doc(1, quote=None, title="Need a CRM dedupe tool"),
            doc(2, quote="x " * 400),
            doc(3, quote=None, title=""),
        ),
    )
    assert report.quotes[0].text == "Need a CRM dedupe tool"
    assert len(report.quotes[1].text) <= MAX_QUOTE_CHARS and report.quotes[1].text.endswith("…")
    assert len(report.quotes) == 2


def test_markdown_is_copy_ready_with_links_and_no_author_names() -> None:
    markdown = render_markdown(build_report(cluster(), (doc(1), doc(2))), "https://unmeet.test")
    assert markdown.startswith("# Sales teams clean CRM duplicates by hand")
    assert (
        "**12 public posts** across **3 sources** · trend: rising (+25% vs the previous period)"
        in markdown
    )
    assert "> I spend hours deduping contacts" in markdown
    assert "[reddit, 2026-11-03](https://x.test/1)" in markdown
    assert "user1" not in markdown and "Tracked with [unMeet](https://unmeet.test)" in markdown
    single = render_markdown(
        build_report(cluster(source_count=1, growth_rate=None, status="new"), (doc(1),))
    )
    assert (
        "**1 source**" in single and "new this period" in single and "vs the previous" not in single
    )


class Reader(EmptyAnalyticsReadFacade):
    def __init__(self, clusters, documents) -> None:
        self._clusters = clusters
        self._documents = documents
        self.limits: list[int] = []

    def get_clusters(self):
        return self._clusters

    def get_cluster(self, cluster_id, document_limit=20):
        self.limits.append(document_limit)
        item = next((c for c in self._clusters if c.cluster_id == cluster_id), None)
        return ClusterDetail(item, tuple(self._documents)) if item else None


class NoSearch:
    def search(self, query, limit):
        return ()


def client(clusters, documents=(), min_documents=5):
    app = create_app(
        ApiDependencies(analytics_reader=Reader(clusters, documents), semantic_search=NoSearch()),
        settings=replace(
            base_settings,
            report_min_documents=min_documents,
            public_site_url="https://unmeet.test",
            environment="production",
            api_key="op",
        ),
    )
    return TestClient(app)


def test_reports_are_public_ranked_cacheable_and_hide_thin_clusters() -> None:
    c = client(
        [
            cluster(1, count=20, score=0.4),
            cluster(2, label="Teams lose track of renewals", count=9, score=0.9),
            cluster(3, count=2, score=1.0),
        ]
    )

    response = c.get("/api/v1/reports")  # no credentials: public

    assert response.status_code == 200
    assert [i["cluster_id"] for i in response.json()["items"]] == [2, 1]
    assert response.headers["cache-control"] == "public, max-age=300"


def test_report_detail_and_markdown_exports() -> None:
    c = client([cluster(1)], [doc(i) for i in range(3)])

    body = c.get("/api/v1/reports/1").json()
    assert body["title"] == "Sales teams clean CRM duplicates by hand" and len(body["quotes"]) == 3
    assert "author" not in str(body) and "user0" not in str(body)
    markdown = c.get("/api/v1/reports/1.md")
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Tracked with [unMeet](https://unmeet.test)" in markdown.text


def test_unknown_or_unpublishable_reports_are_404() -> None:
    c = client([cluster(1, count=2)])
    assert c.get("/api/v1/reports/1").json()["code"] == "report_not_found"
    assert c.get("/api/v1/reports/99").status_code == 404
    assert c.get("/api/v1/reports/1.md").status_code == 404
