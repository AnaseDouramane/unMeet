from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.demo.service import DemoBusyError
from app.llm.client import LLMRequestError
from app.net.safe_fetch import FetchError, UnsafeUrlError
from app.onboarding.service import OnboardingError

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class DemoRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000, examples=["https://example.com"])


class DemoSignalResponse(BaseModel):
    source: str
    title: str
    url: str
    published_at: datetime
    quote: str | None
    intent: str | None
    similarity: float | None


class DemoResponse(BaseModel):
    product_summary: str
    competitors: list[str]
    topics: list[str]
    signals: list[DemoSignalResponse]


@router.post("", response_model=DemoResponse)
def run_demo(
    body: DemoRequest,
    request: Request,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> DemoResponse:
    """Public and rate limited: five real recent conversations that match the product at this URL."""
    settings = request.app.state.settings
    service = dependencies.demo
    if not settings.demo_enabled or service is None:
        raise ApiError(503, "demo_disabled", "the live demo is not available right now")
    visitor = getattr(request.state, "client_identity", "unknown")
    decision = request.app.state.demo_limiter.check(visitor, settings.demo_per_visitor_per_hour)
    if not decision.allowed:
        raise ApiError(
            429,
            "rate_limited",
            "you reached the demo limit for this hour",
            {"retry_after_seconds": decision.retry_after_seconds},
        )
    try:
        result = service.run(body.url)
    except UnsafeUrlError as error:
        raise ApiError(400, "unsafe_url", str(error)) from error
    except FetchError as error:
        raise ApiError(422, "fetch_failed", str(error)) from error
    except OnboardingError as error:
        raise ApiError(422, "analysis_failed", str(error)) from error
    except DemoBusyError as error:
        raise ApiError(503, "demo_busy", str(error)) from error
    except LLMRequestError as error:
        raise ApiError(
            502, "llm_unavailable", "the AI provider is unavailable, try again"
        ) from error
    return DemoResponse(
        product_summary=result.product_summary,
        competitors=list(result.competitors),
        topics=list(result.topics),
        signals=[DemoSignalResponse(**vars(s)) for s in result.signals],
    )
