from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.clustering.schemas import ClusterTrend
from app.database.schemas import PersistedClusterRunDetails


class TimeSeriesGranularity(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True)
class DashboardSummary:
    total_problems: int
    total_clusters: int
    new_clusters: int
    rising_clusters: int
    stable_clusters: int
    falling_clusters: int
    source_count: int
    latest_run_id: int | None
    latest_run_created_at: datetime | None


@dataclass(frozen=True)
class ClusterRankingItem:
    cluster_id: int
    label: str
    rank: int
    opportunity_score: float
    document_count: int
    growth_rate: float | None
    status: str
    source_count: int
    average_problem_confidence: float
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class SourceBreakdownItem:
    source: str
    problem_count: int
    percentage: float


@dataclass(frozen=True)
class TrendDistribution:
    new_count: int
    rising_count: int
    stable_count: int
    falling_count: int


@dataclass(frozen=True)
class TimeSeriesPoint:
    period_start: datetime
    problem_count: int
    cluster_count: int
    new_count: int
    rising_count: int
    stable_count: int
    falling_count: int


@dataclass(frozen=True)
class AnalyticsResult:
    summary: DashboardSummary
    top_opportunities: tuple[ClusterRankingItem, ...]
    source_breakdown: tuple[SourceBreakdownItem, ...]
    trend_distribution: TrendDistribution
    time_series: tuple[TimeSeriesPoint, ...]


@dataclass(frozen=True)
class SourceProblemCount:
    source: str
    problem_count: int


@dataclass(frozen=True)
class HistoricalRunAnalyticsInput:
    run: PersistedClusterRunDetails
    total_problems: int
    cluster_count: int
    trends: tuple[ClusterTrend, ...]
