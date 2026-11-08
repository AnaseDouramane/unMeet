from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


class SourceFreshness(BaseModel):
    source: str
    last_processed_at: datetime
    seconds_since: int
    item_count: int
    stale: bool


class IngestionHealth(BaseModel):
    status: str
    stale_after_seconds: int
    sources: list[SourceFreshness]


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        application=request.app.title,
        version=request.app.version,
    )


@router.get("/health/ingestion", response_model=IngestionHealth)
def ingestion_health(
    request: Request, dependencies: ApiDependencies = Depends(get_dependencies)
) -> JSONResponse:
    """200 while every source with data was processed recently, 503 when one went quiet.

    Point an uptime monitor at this URL to be alerted about an ingestion stall. A source that
    has never produced data is not listed: absence is not a stall until the first item lands.
    """
    stale_after = int(request.app.state.settings.ingestion_stale_after_seconds)
    now = datetime.now(UTC)
    sources = []
    for source, moment, count in dependencies.freshness_reader.latest_by_source():
        seconds = max(0, int((now - moment).total_seconds()))
        sources.append(
            SourceFreshness(
                source=source,
                last_processed_at=moment,
                seconds_since=seconds,
                item_count=count,
                stale=seconds > stale_after,
            )
        )
    stale = any(item.stale for item in sources)
    body = IngestionHealth(
        status="stale" if stale else "ok", stale_after_seconds=stale_after, sources=sources
    )
    return JSONResponse(status_code=503 if stale else 200, content=body.model_dump(mode="json"))
