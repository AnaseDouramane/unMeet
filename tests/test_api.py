from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.analytics.schemas import (
    AnalyticsResult,
    ClusterRankingItem,
    DashboardSummary,
    SourceBreakdownItem,
    TimeSeriesGranularity,
    TimeSeriesPoint,
    TrendDistribution,
)
from app.api.app import create_app
from app.api.dependencies import (
    ApiDependencies,
    ClusterDetail,
    DatabaseUnavailableError,
    PublicDocument,
)


def _item(
    cluster_id: int,
    rank: int,
    status: str = "stable",
    score: float = 0.5,
    count: int = 3,
    growth_rate: float | None = 0.0,
) -> ClusterRankingItem:
    return ClusterRankingItem(
        cluster_id,
        f"cluster-{cluster_id}",
        rank,
        score,
        count,
        growth_rate,
        status,
        2,
        0.8,
        ("keyword",),
    )


def _document(document_id: int = 1) -> PublicDocument:
    return PublicDocument(
        document_id,
        "reddit",
        "A repeated manual task",
        "I spend hours copying values between systems.",
        "https://example.test/post",
        "alice",
        datetime(2025, 1, 1, tzinfo=UTC),
        0.9,
    )


def _analytics_result() -> AnalyticsResult:
    return AnalyticsResult(
        DashboardSummary(10, 2, 1, 1, 0, 0, 2, 7, datetime(2025, 1, 2, tzinfo=UTC)),
        (),
        (
            SourceBreakdownItem("hackernews", 7, 0.7),
            SourceBreakdownItem("reddit", 3, 0.3),
        ),
        TrendDistribution(1, 1, 0, 0),
        (
            TimeSeriesPoint(datetime(2025, 1, 1, tzinfo=UTC), 4, 1, 1, 0, 0, 0),
            TimeSeriesPoint(datetime(2025, 1, 2, tzinfo=UTC), 6, 2, 0, 1, 0, 0),
        ),
    )


class FakeAnalyticsReader:
    def __init__(self) -> None:
        self.items = (
            _item(2, 2, "stable", 0.6, 8, 0.0),
            _item(1, 1, "rising", 0.9, 5, 1.2),
        )
        self.periods: list[TimeSeriesGranularity] = []

    def get_analytics(self, period: TimeSeriesGranularity) -> AnalyticsResult:
        self.periods.append(period)
        return _analytics_result()

    def get_opportunities(self):
        return self.items

    def get_clusters(self):
        return self.items

    def get_cluster(self, cluster_id: int):
        item = next((item for item in self.items if item.cluster_id == cluster_id), None)
        return None if item is None else ClusterDetail(item, (_document(),))


class FakeSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int):
        self.calls.append((query, limit))
        return (_document(),)


def _client(reader=None, search=None) -> TestClient:
    dependencies = ApiDependencies(reader or FakeAnalyticsReader(), search or FakeSearch())
    return TestClient(create_app(dependencies=dependencies))


def test_health_does_not_construct_qwen(monkeypatch) -> None:
    from app.problem_detection.qwen3 import Qwen3ProblemClassifier

    def fail_if_constructed(*args, **kwargs):
        raise AssertionError("Qwen must not be constructed by the API")

    monkeypatch.setattr(Qwen3ProblemClassifier, "__init__", fail_if_constructed)

    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_summary_returns_aggregated_read_data() -> None:
    response = _client().get("/api/v1/analytics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_problems"] == 10
    assert body["trend_distribution"]["new_count"] == 1
    assert body["source_breakdown"][0]["source"] == "hackernews"


def test_opportunities_apply_limit_and_status_filter() -> None:
    client = _client()

    response = client.get("/api/v1/opportunities", params={"limit": 1, "status": "rising"})

    assert response.status_code == 200
    assert [item["cluster_id"] for item in response.json()["items"]] == [1]


def test_clusters_support_sorting_and_pagination() -> None:
    response = _client().get(
        "/api/v1/clusters",
        params={"sort_by": "document_count", "limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["cluster_id"] == 2


def test_cluster_detail_hides_centroid_and_handles_not_found() -> None:
    client = _client()

    found = client.get("/api/v1/clusters/1")
    missing = client.get("/api/v1/clusters/99")

    assert found.status_code == 200
    assert "centroid" not in found.json()["cluster"]
    assert found.json()["documents"][0]["id"] == 1
    assert missing.status_code == 404
    assert missing.json()["code"] == "cluster_not_found"


def test_trends_support_each_period() -> None:
    reader = FakeAnalyticsReader()
    client = _client(reader=reader)

    for period in ("day", "week", "month"):
        response = client.get("/api/v1/trends", params={"period": period, "limit": 1})
        assert response.status_code == 200
        assert len(response.json()["time_series"]) == 1

    assert reader.periods == [
        TimeSeriesGranularity.DAY,
        TimeSeriesGranularity.WEEK,
        TimeSeriesGranularity.MONTH,
    ]


def test_search_validates_query_and_delegates_to_semantic_search() -> None:
    search = FakeSearch()
    client = _client(search=search)

    valid = client.get("/api/v1/search", params={"q": "manual exports", "limit": 3})
    empty = client.get("/api/v1/search", params={"q": "   "})

    assert valid.status_code == 200
    assert valid.json()["items"][0]["source"] == "reddit"
    assert search.calls == [("manual exports", 3)]
    assert empty.status_code == 400
    assert empty.json()["code"] == "invalid_query"


def test_invalid_limits_return_400() -> None:
    client = _client()

    response = client.get("/api/v1/opportunities", params={"limit": 0})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_limit"


def test_database_error_returns_503() -> None:
    class FailingReader(FakeAnalyticsReader):
        def get_analytics(self, period: TimeSeriesGranularity) -> AnalyticsResult:
            raise DatabaseUnavailableError("database is unavailable")

    response = _client(reader=FailingReader()).get("/api/v1/analytics/summary")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"
