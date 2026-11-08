from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    ApiDependencies,
    DatabaseUnavailableError,
    build_default_dependencies,
)
from app.api.errors import ApiError
from app.api.middleware import ApiMiddleware, SlidingWindowRateLimiter
from app.api.routes import (
    analytics,
    audit,
    clusters,
    health,
    inbox,
    onboarding,
    opportunities,
    privacy,
    search,
    signals,
    topics,
    trends,
    usage,
    workspaces,
)
from app.api.schemas import ErrorResponse
from app.config import Settings

logger = logging.getLogger(__name__)


def create_app(
    dependencies: ApiDependencies | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    api_settings = settings or Settings()
    app = FastAPI(title=api_settings.api_title, version=api_settings.api_version)
    app.state.settings = api_settings
    app.state.onboarding_limiter = SlidingWindowRateLimiter(window_seconds=3600)
    app.state.dependencies = dependencies or build_default_dependencies(api_settings)
    app.add_middleware(
        ApiMiddleware,
        read_limit_per_minute=api_settings.rate_limit_read_per_minute,
        write_limit_per_minute=api_settings.rate_limit_write_per_minute,
        trust_proxy=api_settings.trust_proxy_headers,
    )
    # CORS is added last so it is outermost: 429 responses still carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_settings.api_cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-API-Key",
            "X-Request-ID",
            "X-Workspace-ID",
        ],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "Retry-After",
        ],
    )
    _register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(analytics.router)
    app.include_router(opportunities.router)
    app.include_router(clusters.router)
    app.include_router(trends.router)
    app.include_router(search.router)
    app.include_router(signals.router)
    app.include_router(topics.router)
    app.include_router(audit.router)
    app.include_router(usage.router)
    app.include_router(privacy.router)
    app.include_router(workspaces.router)
    app.include_router(inbox.router)
    app.include_router(onboarding.router)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, error: ApiError) -> JSONResponse:
        return _error_response(error.status_code, error.code, error.message, error.details)

    @app.exception_handler(DatabaseUnavailableError)
    async def database_error_handler(_: Request, error: DatabaseUnavailableError) -> JSONResponse:
        return _error_response(503, "database_unavailable", str(error))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
        return _error_response(422, "validation_error", "request validation failed", error.errors())

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, error: Exception) -> JSONResponse:
        logger.exception("unexpected API error")
        return _error_response(500, "internal_error", "an unexpected error occurred")


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    payload = ErrorResponse(code=code, message=message, details=details).model_dump()
    return JSONResponse(status_code=status_code, content=payload)


app = create_app()
