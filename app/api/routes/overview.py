from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.principal import get_principal
from app.billing.budget import month_start, spent_usd
from app.billing.plans import plan_for
from app.tenancy.schemas import Principal

router = APIRouter(prefix="/api/v1/workspace", tags=["overview"])


class ProfileResponse(BaseModel):
    name: str
    plan: str
    website_url: str | None
    product_summary: str | None


class TopicOverview(BaseModel):
    id: int
    name: str
    description: str | None
    keywords: list[str]
    products: list[str]
    matched: int
    new: int


class RunOverview(BaseModel):
    source: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    status: str
    acquired: int
    skipped: int
    gated_out: int
    llm_requests: int
    problems: int
    matched: int
    errors: int
    error: str | None


class UsageOverview(BaseModel):
    calls: int
    total_tokens: int
    spent_usd: float | None
    llm_budget_usd: float


class OverviewResponse(BaseModel):
    workspace: ProfileResponse
    inbox: dict[str, int]
    topics: list[TopicOverview]
    runs: list[RunOverview]
    usage: UsageOverview


@router.get("/overview", response_model=OverviewResponse)
def workspace_overview(
    principal: Principal = Depends(get_principal),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> OverviewResponse:
    """Everything the overview page shows, in one call."""
    workspace = dependencies.tenancy.get_workspace(principal.workspace_id)
    if workspace is None:
        raise ApiError(404, "workspace_not_found", "workspace does not exist")
    counts = dependencies.inbox.topic_counts(principal.workspace_id)
    totals = dependencies.usage_reader.totals(month_start(), principal.workspace_id)
    return OverviewResponse(
        workspace=ProfileResponse(
            name=workspace.name,
            plan=workspace.plan,
            website_url=workspace.website_url,
            product_summary=workspace.product_summary,
        ),
        inbox=dependencies.inbox.counts(principal.workspace_id),
        topics=[
            TopicOverview(
                id=topic.id,
                name=topic.name,
                description=topic.description,
                keywords=list(topic.keywords),
                products=list(topic.products),
                matched=counts.get(topic.id, (0, 0))[0],
                new=counts.get(topic.id, (0, 0))[1],
            )
            for topic in dependencies.topic_store.list(principal.workspace_id)
        ],
        runs=[
            RunOverview(
                **{k: getattr(run, k) for k in RunOverview.model_fields if k != "duration_seconds"},
                duration_seconds=round((run.finished_at - run.started_at).total_seconds(), 1),
            )
            for run in dependencies.runs.latest(10)
        ],
        usage=UsageOverview(
            calls=sum(t.calls for t in totals),
            total_tokens=sum(t.prompt_tokens + t.completion_tokens for t in totals),
            spent_usd=spent_usd(totals),
            llm_budget_usd=plan_for(workspace.plan).llm_budget_usd,
        ),
    )
