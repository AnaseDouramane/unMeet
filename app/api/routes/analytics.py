from fastapi import APIRouter, Depends

from app.analytics.schemas import TimeSeriesGranularity
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.routes.common import trend_distribution_response
from app.api.schemas import AnalyticsSummaryResponse, DashboardSummaryResponse, SourceBreakdownResponse


router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def summary(dependencies: ApiDependencies = Depends(get_dependencies)) -> AnalyticsSummaryResponse:
    result = dependencies.analytics_reader.get_analytics(TimeSeriesGranularity.DAY)
    return AnalyticsSummaryResponse(
        summary=DashboardSummaryResponse(**result.summary.__dict__),
        trend_distribution=trend_distribution_response(result.trend_distribution),
        source_breakdown=[SourceBreakdownResponse(**item.__dict__) for item in result.source_breakdown],
    )
