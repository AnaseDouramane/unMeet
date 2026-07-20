from fastapi import APIRouter, Depends

from app.analytics.schemas import TimeSeriesGranularity
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.routes.common import trend_distribution_response
from app.api.schemas import TimeSeriesPointResponse, TrendsResponse


router = APIRouter(prefix="/api/v1", tags=["trends"])


@router.get("/trends", response_model=TrendsResponse)
def trends(
    period: TimeSeriesGranularity = TimeSeriesGranularity.DAY,
    limit: int | None = None,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> TrendsResponse:
    if limit is not None and (limit <= 0 or limit > 100):
        raise ApiError(400, "invalid_limit", "limit must be between 1 and 100")
    result = dependencies.analytics_reader.get_analytics(period)
    series = result.time_series if limit is None else result.time_series[-limit:]
    return TrendsResponse(
        trend_distribution=trend_distribution_response(result.trend_distribution),
        time_series=[TimeSeriesPointResponse(**item.__dict__) for item in series],
    )
