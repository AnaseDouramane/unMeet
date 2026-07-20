from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies import ApiDependencies, DatabaseUnavailableError, build_default_dependencies
from app.api.errors import ApiError
from app.api.routes import analytics, clusters, health, opportunities, search, trends
from app.api.schemas import ErrorResponse
from app.config import Settings


logger = logging.getLogger(__name__)


def create_app(
    dependencies: ApiDependencies | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    api_settings = settings or Settings()
    app = FastAPI(title=api_settings.api_title, version=api_settings.api_version)
    app.state.dependencies = dependencies or build_default_dependencies(api_settings.embedding_model)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_settings.api_cors_origins),
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )
    _register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(analytics.router)
    app.include_router(opportunities.router)
    app.include_router(clusters.router)
    app.include_router(trends.router)
    app.include_router(search.router)
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
