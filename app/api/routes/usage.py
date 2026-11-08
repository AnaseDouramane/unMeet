from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.auth import require_api_key
from app.api.dependencies import ApiDependencies, get_dependencies

router = APIRouter(prefix="/api/v1/usage", tags=["usage"], dependencies=[Depends(require_api_key)])


class UsageTotalsResponse(BaseModel):
    purpose: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None


class LlmUsageResponse(BaseModel):
    items: list[UsageTotalsResponse]
    total_tokens: int
    total_cost_usd: float | None


@router.get("/llm", response_model=LlmUsageResponse)
def llm_usage(
    since: date | None = Query(default=None, description="Only calls on or after this date"),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> LlmUsageResponse:
    moment = None if since is None else datetime.combine(since, time.min, tzinfo=UTC)
    totals = dependencies.usage_reader.totals(moment)
    costs = [item.cost_usd for item in totals]
    return LlmUsageResponse(
        items=[UsageTotalsResponse(**vars(item)) for item in totals],
        total_tokens=sum(item.prompt_tokens + item.completion_tokens for item in totals),
        # An unpriced purpose makes the overall cost unknown rather than understated.
        total_cost_usd=None if any(c is None for c in costs) else round(sum(costs), 6),  # type: ignore[arg-type]
    )
