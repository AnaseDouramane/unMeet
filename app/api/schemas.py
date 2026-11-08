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


SignalIntentParam = Literal[
    "pain_point", "feature_request", "solution_search", "competitor_complaint"
]


class SignalResponse(BaseModel):
    id: int
    source: str
    title: str
    url: str
    author: str | None
    published_at: datetime
    intent: str | None
    pain_quote: str | None
    products_mentioned: list[str]
    severity: int | None
    confidence: float
    similarity: float | None = Field(
        default=None, description="Cosine similarity to the topic, when a topic was given"
    )
    relevance_reason: str | None = Field(
        default=None,
        description="Why the model judged this a match for the tracked topic (topic feeds only)",
    )


class SignalListResponse(BaseModel):
    items: list[SignalResponse]
    limit: int
    offset: int


class TopicCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    intents: list[SignalIntentParam] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list, max_length=20)
    sources: list[str] = Field(default_factory=list, max_length=10)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    min_severity: int | None = Field(default=None, ge=1, le=3)
    max_distance: float = Field(default=0.6, gt=0, le=2)
    webhook_url: str | None = Field(default=None, max_length=2000)


class TopicResponse(BaseModel):
    id: int
    name: str
    description: str | None
    intents: list[str]
    products: list[str]
    sources: list[str]
    keywords: list[str] = []
    min_severity: int | None
    max_distance: float
    has_webhook: bool
    created_at: datetime | None
    last_delivered_at: datetime | None


class TopicListResponse(BaseModel):
    items: list[TopicResponse]
