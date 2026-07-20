from datetime import UTC, datetime

import pytest

from app.analytics import (
    AnalyticsService,
    HistoricalRunAnalyticsInput,
    SourceProblemCount,
    TimeSeriesGranularity,
)
from app.clustering.schemas import ClusterTrend
from app.database.schemas import (
    ClusterRunMetadata,
    PersistedClusterDetails,
    PersistedClusterRunDetails,
)
from app.opportunities.ranking import OpportunityRankingResult, OpportunityScoreComponents


METADATA = ClusterRunMetadata("embedding-v1", 3, None, "euclidean")


def _run(run_id: int, created_at: datetime, metadata: ClusterRunMetadata = METADATA):
    return PersistedClusterRunDetails(run_id, created_at, metadata)


def _cluster(cluster_id: int, run_id: int = 1, count: int = 3) -> PersistedClusterDetails:
    return PersistedClusterDetails(
        cluster_id,
        run_id,
        cluster_id,
        f"label-{cluster_id}",
        (f"keyword-{cluster_id}",),
        (0.0,),
        count,
    )


def _trend(cluster_id: int, status: str = "stable", count: int = 3) -> ClusterTrend:
    return ClusterTrend(cluster_id, None, f"label-{cluster_id}", count, 1, count - 1, 0.0, status, None)


def _ranking(cluster: PersistedClusterDetails, rank: int, score: float = 0.5):
    return OpportunityRankingResult(
        cluster.id,
        cluster.label,
        rank,
        score,
        cluster.document_count,
        0.0,
        "stable",
        1,
        0.8,
        OpportunityScoreComponents(1.0, 0.25, 1.0, 0.8),
    )


def _history(
    run_id: int,
    created_at: datetime,
    total_problems: int,
    cluster_count: int,
    trends: tuple[ClusterTrend, ...],
    metadata: ClusterRunMetadata = METADATA,
) -> HistoricalRunAnalyticsInput:
    return HistoricalRunAnalyticsInput(
        _run(run_id, created_at, metadata), total_problems, cluster_count, trends
    )


def _current_input():
    latest = _run(1, datetime(2025, 1, 3, 12, tzinfo=UTC))
    clusters = (_cluster(1, count=5), _cluster(2, count=3), _cluster(3, count=2))
    trends = (
        _trend(1, "new", 5),
        _trend(2, "rising", 3),
        _trend(3, "falling", 2),
    )
    rankings = (_ranking(clusters[1], 2, 0.7), _ranking(clusters[0], 1, 0.9), _ranking(clusters[2], 3, 0.4))
    sources = (SourceProblemCount("reddit", 2), SourceProblemCount("hackernews", 8))
    return latest, clusters, trends, rankings, sources


def test_summary_top_ranking_breakdown_and_distribution_are_correct() -> None:
    latest, clusters, trends, rankings, sources = _current_input()

    result = AnalyticsService(top_n=2).build(latest, clusters, trends, rankings, sources, ())

    assert result.summary.total_problems == 10
    assert result.summary.total_clusters == 3
    assert result.summary.new_clusters == 1
    assert result.summary.rising_clusters == 1
    assert result.summary.stable_clusters == 0
    assert result.summary.falling_clusters == 1
    assert result.summary.source_count == 2
    assert result.summary.latest_run_id == 1
    assert [item.cluster_id for item in result.top_opportunities] == [1, 2]
    assert result.top_opportunities[0].keywords == ("keyword-1",)
    assert [item.source for item in result.source_breakdown] == ["hackernews", "reddit"]
    assert [item.percentage for item in result.source_breakdown] == [0.8, 0.2]
    assert sum(item.percentage for item in result.source_breakdown) == 1.0
    assert result.trend_distribution.new_count == 1
    assert result.trend_distribution.falling_count == 1


def test_source_breakdown_is_deterministic_for_equal_counts() -> None:
    latest, clusters, trends, rankings, _ = _current_input()

    result = AnalyticsService().build(
        latest,
        tuple(reversed(clusters)),
        tuple(reversed(trends)),
        tuple(reversed(rankings)),
        (SourceProblemCount("reddit", 2), SourceProblemCount("hackernews", 2)),
        (),
    )

    assert [item.source for item in result.source_breakdown] == ["hackernews", "reddit"]
    assert all(0.0 <= item.percentage <= 1.0 for item in result.source_breakdown)
    assert sum(item.percentage for item in result.source_breakdown) == 1.0


@pytest.mark.parametrize(
    ("granularity", "expected_period", "expected_problems", "expected_clusters"),
    [
        (TimeSeriesGranularity.DAY, datetime(2025, 1, 1, tzinfo=UTC), 2, 1),
        (TimeSeriesGranularity.WEEK, datetime(2024, 12, 30, tzinfo=UTC), 5, 3),
        (TimeSeriesGranularity.MONTH, datetime(2025, 1, 1, tzinfo=UTC), 5, 3),
    ],
)
def test_time_series_aggregates_day_week_and_month(
    granularity, expected_period, expected_problems, expected_clusters
) -> None:
    latest, clusters, trends, rankings, sources = _current_input()
    history = (
        _history(2, datetime(2025, 1, 1, 10, tzinfo=UTC), 2, 1, (_trend(1, "new"),)),
        _history(3, datetime(2025, 1, 2, 10, tzinfo=UTC), 3, 2, (_trend(2, "rising"),)),
        _history(4, datetime(2025, 2, 1, 10, tzinfo=UTC), 7, 4, (_trend(3, "falling"),)),
    )

    result = AnalyticsService().build(
        latest, clusters, trends, rankings, sources, tuple(reversed(history)), granularity
    )

    assert result.time_series[0].period_start == expected_period
    assert result.time_series[0].problem_count == expected_problems
    assert result.time_series[0].cluster_count == expected_clusters
    assert [point.period_start for point in result.time_series] == sorted(
        point.period_start for point in result.time_series
    )


def test_empty_input_returns_explicit_empty_result() -> None:
    result = AnalyticsService().build(None, (), (), (), (), ())

    assert result.summary.total_problems == 0
    assert result.summary.latest_run_id is None
    assert result.top_opportunities == ()
    assert result.source_breakdown == ()
    assert result.time_series == ()


def test_rejects_invalid_top_n() -> None:
    with pytest.raises(ValueError, match="top_n"):
        AnalyticsService(top_n=0)


def test_rejects_naive_latest_run_timestamp() -> None:
    latest, clusters, trends, rankings, sources = _current_input()
    naive = _run(latest.id, datetime(2025, 1, 3, 12))

    with pytest.raises(ValueError, match="timezone-aware"):
        AnalyticsService().build(naive, clusters, trends, rankings, sources, ())


def test_rejects_incompatible_historical_runs() -> None:
    latest, clusters, trends, rankings, sources = _current_input()
    incompatible_metadata = ClusterRunMetadata("other-model", 3, None, "euclidean")
    history = _history(
        2,
        datetime(2025, 1, 2, tzinfo=UTC),
        2,
        1,
        (_trend(1, "new"),),
        incompatible_metadata,
    )

    with pytest.raises(ValueError, match="not compatible"):
        AnalyticsService().build(latest, clusters, trends, rankings, sources, (history,))


def test_rejects_inconsistent_current_inputs() -> None:
    latest, clusters, trends, rankings, sources = _current_input()

    with pytest.raises(ValueError, match="cover every current cluster"):
        AnalyticsService().build(latest, clusters, trends[:-1], rankings, sources, ())
