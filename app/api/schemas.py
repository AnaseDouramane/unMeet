from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TrendStatus = Literal["new", "rising", "stable", "falling"]
ClusterSortField = Literal["document_count", "opportunity_score", "growth_rate"]


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: object | None = None


class HealthResponse(BaseModel):
    status: str
    application: str
    version: str


class DashboardSummaryResponse(BaseModel):
    total_problems: int
    total_clusters: int
    new_clusters: int
    rising_clusters: int
    stable_clusters: int
    falling_clusters: int
    source_count: int
    latest_run_id: int | None
    latest_run_created_at: datetime | None


class TrendDistributionResponse(BaseModel):
    new_count: int
    rising_count: int
    stable_count: int
    falling_count: int


class SourceBreakdownResponse(BaseModel):
    source: str
    problem_count: int
    percentage: float = Field(ge=0, le=1)


class AnalyticsSummaryResponse(BaseModel):
    summary: DashboardSummaryResponse
    trend_distribution: TrendDistributionResponse
    source_breakdown: list[SourceBreakdownResponse]


class OpportunityResponse(BaseModel):
    cluster_id: int
    label: str
    rank: int
    opportunity_score: float = Field(ge=0, le=1)
    document_count: int
    growth_rate: float | None
    status: TrendStatus
    source_count: int
    average_problem_confidence: float = Field(ge=0, le=1)
    keywords: list[str]


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]


class ClusterListResponse(BaseModel):
    items: list[OpportunityResponse]
    limit: int
    offset: int


class PublicDocumentResponse(BaseModel):
    id: int
    source: str
    title: str
    body: str
    url: str
    author: str | None
    published_at: datetime
    problem_confidence: float = Field(ge=0, le=1)


class ClusterDetailResponse(BaseModel):
    cluster: OpportunityResponse
    documents: list[PublicDocumentResponse]


class TimeSeriesPointResponse(BaseModel):
    period_start: datetime
    problem_count: int
    cluster_count: int
    new_count: int
    rising_count: int
    stable_count: int
    falling_count: int


class TrendsResponse(BaseModel):
    trend_distribution: TrendDistributionResponse
    time_series: list[TimeSeriesPointResponse]


class SearchResponse(BaseModel):
    items: list[PublicDocumentResponse]
