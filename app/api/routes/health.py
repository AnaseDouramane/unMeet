from fastapi import APIRouter, Request

from app.api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        application=request.app.title,
        version=request.app.version,
    )
