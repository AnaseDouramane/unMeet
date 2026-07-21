from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

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
    EmptyAnalyticsReadFacade,
    PublicDocument,
    RepositoryAnalyticsReadFacade,
)
from app.database.schemas import ClusterRunMetadata, PersistedClusterRunDetails
from app.database.schemas import ClusterOpportunityStatistics, PersistedClusterDetails
from app.clustering.schemas import ClusterTrend


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


def test_default_cors_allows_next_development_origin() -> None:
    response = _client().options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


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
    class FailingClusterRepository:
        def find_latest_run(self):
            raise SQLAlchemyError("database connection failed")

    class UnusedSourceItemRepository:
        pass

    response = _client(
        reader=RepositoryAnalyticsReadFacade(
            FailingClusterRepository(),
            UnusedSourceItemRepository(),
        )
    ).get("/api/v1/analytics/summary")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


def test_empty_database_returns_valid_empty_responses() -> None:
    class FakeClusterRepository:
        def find_latest_run(self):
            return None

    class UnexpectedSourceItemRepository:
        def count_problems_by_source(self):
            raise AssertionError("source counts must not be read without an analysis run")

    client = _client(
        reader=RepositoryAnalyticsReadFacade(
            FakeClusterRepository(),
            UnexpectedSourceItemRepository(),
        )
    )

    summary = client.get("/api/v1/analytics/summary")
    clusters = client.get("/api/v1/clusters")
    opportunities = client.get("/api/v1/opportunities")
    trends = client.get("/api/v1/trends")

    assert summary.status_code == 200
    assert summary.json() == {
        "summary": {
            "total_problems": 0,
            "total_clusters": 0,
            "new_clusters": 0,
            "rising_clusters": 0,
            "stable_clusters": 0,
            "falling_clusters": 0,
            "source_count": 0,
            "latest_run_id": None,
            "latest_run_created_at": None,
        },
        "trend_distribution": {
            "new_count": 0,
            "rising_count": 0,
            "stable_count": 0,
            "falling_count": 0,
        },
        "source_breakdown": [],
    }
    assert clusters.status_code == 200
    assert clusters.json()["items"] == []
    assert opportunities.status_code == 200
    assert opportunities.json() == {"items": []}
    assert trends.status_code == 200
    assert trends.json() == {
        "trend_distribution": {
            "new_count": 0,
            "rising_count": 0,
            "stable_count": 0,
            "falling_count": 0,
        },
        "time_series": [],
    }


def test_empty_latest_run_returns_empty_analytics_data() -> None:
    class EmptyRunReader(EmptyAnalyticsReadFacade):
        def get_analytics(self, period: TimeSeriesGranularity) -> AnalyticsResult:
            result = self._empty_result()
            return AnalyticsResult(
                summary=DashboardSummary(
                    0, 0, 0, 0, 0, 0, 0, 42, datetime(2025, 1, 2, tzinfo=UTC)
                ),
                top_opportunities=result.top_opportunities,
                source_breakdown=result.source_breakdown,
                trend_distribution=result.trend_distribution,
                time_series=result.time_series,
            )

    client = _client(reader=EmptyRunReader())

    summary = client.get("/api/v1/analytics/summary")
    clusters = client.get("/api/v1/clusters")
    opportunities = client.get("/api/v1/opportunities")
    trends = client.get("/api/v1/trends")

    assert summary.status_code == 200
    assert summary.json()["summary"]["latest_run_id"] == 42
    assert summary.json()["summary"]["total_clusters"] == 0
    assert clusters.status_code == 200
    assert clusters.json()["items"] == []
    assert opportunities.status_code == 200
    assert opportunities.json() == {"items": []}
    assert trends.status_code == 200
    assert trends.json()["trend_distribution"] == {
        "new_count": 0,
        "rising_count": 0,
        "stable_count": 0,
        "falling_count": 0,
    }
    assert trends.json()["time_series"] == []


def test_persisted_empty_run_returns_problem_summary_and_empty_collections() -> None:
    latest_run = PersistedClusterRunDetails(
        2,
        datetime(2025, 1, 2, tzinfo=UTC),
        ClusterRunMetadata("model-a", 5, None, "euclidean"),
    )

    class FakeClusterRepository:
        def find_latest_run(self):
            return latest_run

        def get_clusters_for_run(self, run_id: int):
            assert run_id == 2
            return ()

        def get_trends_for_run(self, run_id: int):
            assert run_id == 2
            return ()

    class FakeSourceItemRepository:
        def count_problems_by_source(self):
            return (("hackernews", 1),)

    reader = RepositoryAnalyticsReadFacade(FakeClusterRepository(), FakeSourceItemRepository())
    client = _client(reader=reader)

    summary = client.get("/api/v1/analytics/summary")
    opportunities = client.get("/api/v1/opportunities")
    trends = client.get("/api/v1/trends")
    clusters = client.get("/api/v1/clusters")

    assert summary.status_code == 200
    assert summary.json()["summary"] == {
        "total_problems": 1,
        "total_clusters": 0,
        "new_clusters": 0,
        "rising_clusters": 0,
        "stable_clusters": 0,
        "falling_clusters": 0,
        "source_count": 1,
        "latest_run_id": 2,
        "latest_run_created_at": "2025-01-02T00:00:00Z",
    }
    assert opportunities.status_code == 200
    assert opportunities.json() == {"items": []}
    assert trends.status_code == 200
    assert trends.json() == {
        "trend_distribution": {
            "new_count": 0,
            "rising_count": 0,
            "stable_count": 0,
            "falling_count": 0,
        },
        "time_series": [],
    }
    assert clusters.status_code == 200
    assert clusters.json()["items"] == []


def test_repository_reader_serves_all_analytics_endpoints_for_a_valid_two_cluster_run() -> None:
    latest_run = PersistedClusterRunDetails(
        11,
        datetime(2025, 1, 2, tzinfo=UTC),
        ClusterRunMetadata("model-a", 5, None, "euclidean"),
    )
    clusters = (
        PersistedClusterDetails(101, 11, 4, "manual work", ("manual",), (0.1,), 3),
        PersistedClusterDetails(102, 11, 9, "support gaps", ("support",), (0.2,), 2),
    )
    trends = (
        ClusterTrend(101, None, "manual work", 3, 0, 3, None, "new", None),
        ClusterTrend(102, 88, "support gaps", 2, 1, 1, 1.0, "rising", 0.9),
    )

    class FakeClusterRepository:
        def find_latest_run(self):
            return latest_run

        def get_clusters_for_run(self, run_id: int):
            assert run_id == latest_run.id
            return clusters

        def get_trends_for_run(self, run_id: int):
            assert run_id == latest_run.id
            return trends

        def get_opportunity_statistics_for_run(self, run_id: int):
            assert run_id == latest_run.id
            return (
                ClusterOpportunityStatistics(101, 2, 0.8),
                ClusterOpportunityStatistics(102, 1, 0.9),
            )

    class FakeSourceItemRepository:
        def count_problems_by_source(self):
            return (("reddit", 5),)

    client = _client(
        reader=RepositoryAnalyticsReadFacade(FakeClusterRepository(), FakeSourceItemRepository())
    )

    assert client.get("/api/v1/analytics/summary").status_code == 200
    assert client.get("/api/v1/opportunities").status_code == 200
    assert client.get("/api/v1/clusters").status_code == 200
    assert client.get("/api/v1/trends").status_code == 200
