from fastapi import APIRouter, Depends

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.routes.common import opportunity_response
from app.api.schemas import OpportunityListResponse, TrendStatus


router = APIRouter(prefix="/api/v1", tags=["opportunities"])


@router.get("/opportunities", response_model=OpportunityListResponse)
def opportunities(
    limit: int = 20,
    status: TrendStatus | None = None,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> OpportunityListResponse:
    if limit <= 0 or limit > 100:
        raise ApiError(400, "invalid_limit", "limit must be between 1 and 100")
    items = dependencies.analytics_reader.get_opportunities()
    if status is not None:
        items = [item for item in items if item.status == status]
    ordered = sorted(items, key=lambda item: (item.rank, item.cluster_id))
    return OpportunityListResponse(items=[opportunity_response(item) for item in ordered[:limit]])
