from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.analytics.schemas import (
    AnalyticsResult,
    ClusterRankingItem,
    DashboardSummary,
    HistoricalRunAnalyticsInput,
    SourceBreakdownItem,
    SourceProblemCount,
    TimeSeriesGranularity,
    TimeSeriesPoint,
    TrendDistribution,
)
from app.clustering.schemas import ClusterTrend
from app.database.schemas import PersistedClusterDetails, PersistedClusterRunDetails
from app.opportunities.ranking import OpportunityRankingResult


class AnalyticsService:
    """Builds immutable display DTOs from repository-provided snapshots.

    Time series aggregate every compatible run supplied by the caller. Periods with
    no supplied run are deliberately omitted; this service never invents gaps.
    """

    _STATUSES = frozenset({"new", "rising", "stable", "falling"})

    def __init__(self, top_n: int = 10) -> None:
        if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
            raise ValueError("top_n must be a positive integer")
        self._top_n = top_n

    def build(
        self,
        latest_run: PersistedClusterRunDetails | None,
        clusters: Sequence[PersistedClusterDetails],
        trends: Sequence[ClusterTrend],
        rankings: Sequence[OpportunityRankingResult],
        source_problem_counts: Sequence[SourceProblemCount],
        historical_runs: Sequence[HistoricalRunAnalyticsInput],
        granularity: TimeSeriesGranularity = TimeSeriesGranularity.DAY,
    ) -> AnalyticsResult:
        if latest_run is None:
            if any((clusters, trends, rankings, source_problem_counts, historical_runs)):
                raise ValueError("latest_run is required when analytics input is not empty")
            return self._empty_result()
        self._validate_aware_datetime(latest_run.created_at, "latest_run.created_at")
        if not isinstance(granularity, TimeSeriesGranularity):
            raise ValueError("granularity must be a TimeSeriesGranularity")

        clusters_by_id = self._validate_clusters(latest_run, clusters)
        trends_by_cluster_id = self._validate_trends(clusters_by_id, trends)
        ranking_items = self._build_ranking_items(clusters_by_id, rankings)
        source_breakdown = self._build_source_breakdown(source_problem_counts)
        trend_distribution = self._trend_distribution(trends_by_cluster_id.values())
        time_series = self._build_time_series(latest_run, historical_runs, granularity)
        summary = DashboardSummary(
            total_problems=sum(item.problem_count for item in source_breakdown),
            total_clusters=len(clusters_by_id),
            new_clusters=trend_distribution.new_count,
            rising_clusters=trend_distribution.rising_count,
            stable_clusters=trend_distribution.stable_count,
            falling_clusters=trend_distribution.falling_count,
            source_count=len(source_breakdown),
            latest_run_id=latest_run.id,
            latest_run_created_at=latest_run.created_at,
        )
        return AnalyticsResult(
            summary=summary,
            top_opportunities=ranking_items[: self._top_n],
            source_breakdown=source_breakdown,
            trend_distribution=trend_distribution,
            time_series=time_series,
        )

    @staticmethod
    def _empty_result() -> AnalyticsResult:
        distribution = TrendDistribution(0, 0, 0, 0)
        return AnalyticsResult(
            summary=DashboardSummary(0, 0, 0, 0, 0, 0, 0, None, None),
            top_opportunities=(),
            source_breakdown=(),
            trend_distribution=distribution,
            time_series=(),
        )

    @staticmethod
    def _validate_clusters(
        latest_run: PersistedClusterRunDetails,
        clusters: Sequence[PersistedClusterDetails],
    ) -> dict[int, PersistedClusterDetails]:
        result: dict[int, PersistedClusterDetails] = {}
        for cluster in clusters:
            if cluster.id in result:
                raise ValueError(f"duplicate cluster id: {cluster.id}")
            if cluster.run_id != latest_run.id:
                raise ValueError("cluster does not belong to latest_run")
            if cluster.document_count < 0:
                raise ValueError("cluster document_count must be non-negative")
            result[cluster.id] = cluster
        return result

    def _validate_trends(
        self,
        clusters_by_id: dict[int, PersistedClusterDetails],
        trends: Sequence[ClusterTrend],
    ) -> dict[int, ClusterTrend]:
        result: dict[int, ClusterTrend] = {}
        for trend in trends:
            if trend.current_cluster_id in result:
                raise ValueError(f"duplicate trend cluster id: {trend.current_cluster_id}")
            if trend.current_cluster_id not in clusters_by_id:
                raise ValueError("trend references an unknown cluster")
            if trend.status not in self._STATUSES:
                raise ValueError(f"invalid trend status: {trend.status}")
            result[trend.current_cluster_id] = trend
        if set(result) != set(clusters_by_id):
            raise ValueError("trends must cover every current cluster exactly once")
        return result

    @staticmethod
    def _build_ranking_items(
        clusters_by_id: dict[int, PersistedClusterDetails],
        rankings: Sequence[OpportunityRankingResult],
    ) -> tuple[ClusterRankingItem, ...]:
        rankings_by_cluster_id: dict[int, OpportunityRankingResult] = {}
        ranks: set[int] = set()
        for ranking in rankings:
            if ranking.cluster_id in rankings_by_cluster_id:
                raise ValueError(f"duplicate ranking cluster id: {ranking.cluster_id}")
            if ranking.cluster_id not in clusters_by_id:
                raise ValueError("ranking references an unknown cluster")
            if ranking.rank <= 0 or ranking.rank in ranks:
                raise ValueError("ranking ranks must be unique positive integers")
            cluster = clusters_by_id[ranking.cluster_id]
            if ranking.label != cluster.label or ranking.document_count != cluster.document_count:
                raise ValueError("ranking does not match current cluster")
            rankings_by_cluster_id[ranking.cluster_id] = ranking
            ranks.add(ranking.rank)
        if set(rankings_by_cluster_id) != set(clusters_by_id):
            raise ValueError("rankings must cover every current cluster exactly once")
        return tuple(
            ClusterRankingItem(
                cluster_id=ranking.cluster_id,
                label=ranking.label,
                rank=ranking.rank,
                opportunity_score=ranking.opportunity_score,
                document_count=ranking.document_count,
                growth_rate=ranking.growth_rate,
                status=ranking.status,
                source_count=ranking.source_count,
                average_problem_confidence=ranking.average_problem_confidence,
                keywords=clusters_by_id[ranking.cluster_id].keywords,
            )
            for ranking in sorted(rankings, key=lambda item: (item.rank, item.cluster_id))
        )

    @staticmethod
    def _build_source_breakdown(
        source_problem_counts: Sequence[SourceProblemCount],
    ) -> tuple[SourceBreakdownItem, ...]:
        counts: dict[str, int] = {}
        for item in source_problem_counts:
            if not item.source or not item.source.strip():
                raise ValueError("source must not be blank")
            if item.source in counts:
                raise ValueError(f"duplicate source: {item.source}")
            AnalyticsService._validate_non_negative_integer(item.problem_count, "problem_count")
            counts[item.source] = item.problem_count
        positive_counts = {source: count for source, count in counts.items() if count > 0}
        total = sum(positive_counts.values())
        if not total:
            return ()
        ordered_counts = sorted(positive_counts.items(), key=lambda item: (-item[1], item[0]))
        items = [
            SourceBreakdownItem(source, count, count / total)
            for source, count in ordered_counts
        ]
        correction = 1.0 - sum(item.percentage for item in items)
        if correction:
            last = items[-1]
            items[-1] = SourceBreakdownItem(
                last.source,
                last.problem_count,
                last.percentage + correction,
            )
        return tuple(items)

    def _build_time_series(
        self,
        latest_run: PersistedClusterRunDetails,
        historical_runs: Sequence[HistoricalRunAnalyticsInput],
        granularity: TimeSeriesGranularity,
    ) -> tuple[TimeSeriesPoint, ...]:
        buckets: dict[datetime, list[int]] = {}
        run_ids: set[int] = set()
        for history in historical_runs:
            if history.run.id in run_ids:
                raise ValueError(f"duplicate historical run id: {history.run.id}")
            run_ids.add(history.run.id)
            if history.run.metadata != latest_run.metadata:
                raise ValueError("historical run is not compatible with latest_run")
            self._validate_aware_datetime(history.run.created_at, "historical run created_at")
            self._validate_non_negative_integer(history.total_problems, "total_problems")
            self._validate_non_negative_integer(history.cluster_count, "cluster_count")
            distribution = self._trend_distribution(history.trends)
            bucket = self._period_start(history.run.created_at, granularity)
            values = buckets.setdefault(bucket, [0, 0, 0, 0, 0, 0])
            values[0] += history.total_problems
            values[1] += history.cluster_count
            values[2] += distribution.new_count
            values[3] += distribution.rising_count
            values[4] += distribution.stable_count
            values[5] += distribution.falling_count
        return tuple(
            TimeSeriesPoint(period_start, *buckets[period_start])
            for period_start in sorted(buckets)
        )

    def _trend_distribution(self, trends: Sequence[ClusterTrend]) -> TrendDistribution:
        counts = Counter()
        for trend in trends:
            if trend.status not in self._STATUSES:
                raise ValueError(f"invalid trend status: {trend.status}")
            counts[trend.status] += 1
        return TrendDistribution(
            new_count=counts["new"],
            rising_count=counts["rising"],
            stable_count=counts["stable"],
            falling_count=counts["falling"],
        )

    @staticmethod
    def _period_start(value: datetime, granularity: TimeSeriesGranularity) -> datetime:
        utc_value = value.astimezone(UTC)
        if granularity is TimeSeriesGranularity.DAY:
            return utc_value.replace(hour=0, minute=0, second=0, microsecond=0)
        if granularity is TimeSeriesGranularity.WEEK:
            day_start = utc_value.replace(hour=0, minute=0, second=0, microsecond=0)
            return day_start - timedelta(days=day_start.weekday())
        return utc_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _validate_aware_datetime(value: datetime, name: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")

    @staticmethod
    def _validate_non_negative_integer(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
