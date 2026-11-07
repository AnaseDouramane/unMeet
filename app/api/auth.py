"""API key protection for endpoints that change data.

Clients send ``Authorization: Bearer <key>`` or ``X-API-Key: <key>``. When ``UNMEET_API_KEY``
is not configured, writes are allowed only in the development environment so a fresh local
checkout keeps working, while any other environment fails closed.
"""

from __future__ import annotations

import secrets

from fastapi import Request

from app.api.errors import ApiError


def require_api_key(request: Request) -> None:
    settings = request.app.state.settings
    expected = settings.api_key
    if expected is None:
        if settings.environment == "development":
            return
        raise ApiError(503, "auth_not_configured", "UNMEET_API_KEY must be set to allow writes")

    provided = request.headers.get("X-API-Key")
    authorization = request.headers.get("Authorization", "")
    if provided is None and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided or not secrets.compare_digest(provided.encode(), expected.encode()):
        raise ApiError(401, "unauthorized", "a valid API key is required")
