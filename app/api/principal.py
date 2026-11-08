"""Who is calling and for which workspace.

Credentials, in the order they are tried:

1. a workspace API key (``um_...``) sent as ``X-API-Key`` or ``Authorization: Bearer``;
2. the operator key (``UNMEET_API_KEY``): support/ops access, workspace chosen with
   ``X-Workspace-ID``;
3. a JWT from the configured auth provider; the workspace comes from ``X-Workspace-ID`` or is
   the user's only one;
4. no credentials in the development environment: the default workspace, so a fresh checkout
   keeps working. Any other environment answers 401.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, Request

from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.auth.jwt import InvalidTokenError
from app.tenancy.schemas import Principal, Role, parse_api_key_prefix


def _credential(request: Request) -> str | None:
    provided = request.headers.get("X-API-Key")
    if provided:
        return provided.strip()
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _requested_workspace(request: Request) -> int | None:
    raw = request.headers.get("X-Workspace-ID")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as error:
        raise ApiError(400, "invalid_workspace", "X-Workspace-ID must be an integer") from error


def get_principal(
    request: Request, dependencies: ApiDependencies = Depends(get_dependencies)
) -> Principal:
    settings = request.app.state.settings
    credential = _credential(request)
    tenancy = dependencies.tenancy

    if credential is None:
        if settings.environment == "development" and settings.api_key is None:
            workspace = tenancy.ensure_default_workspace()
            return Principal(workspace.id, Role.OWNER, "dev")
        raise ApiError(401, "unauthorized", "authentication is required")

    if parse_api_key_prefix(credential) is not None:
        key = tenancy.authenticate_api_key(credential)
        if key is None:
            raise ApiError(401, "unauthorized", "invalid or revoked API key")
        return Principal(key.workspace_id, Role.ADMIN, "api_key")

    if settings.api_key is not None and secrets.compare_digest(
        credential.encode(), settings.api_key.encode()
    ):
        requested = _requested_workspace(request)
        if requested is None:
            return Principal(tenancy.ensure_default_workspace().id, Role.OWNER, "operator")
        if tenancy.get_workspace(requested) is None:
            raise ApiError(404, "workspace_not_found", f"workspace {requested} does not exist")
        return Principal(requested, Role.OWNER, "operator")

    verifier = dependencies.token_verifier
    if verifier is None:
        raise ApiError(401, "unauthorized", "invalid credentials")
    try:
        claims = verifier.verify(credential)
    except InvalidTokenError as error:
        raise ApiError(401, "unauthorized", "invalid or expired token") from error
    user = tenancy.get_or_create_user(claims.email, claims.subject)
    memberships = tenancy.workspaces_for_user(user.id)
    requested = _requested_workspace(request)
    if requested is None:
        if len(memberships) == 1:
            workspace, role = memberships[0]
            return Principal(workspace.id, role, "jwt", user.id)
        raise ApiError(
            400,
            "workspace_required",
            "send X-Workspace-ID: you belong to "
            + ("no workspace yet" if not memberships else f"{len(memberships)} workspaces"),
        )
    role_in_workspace = tenancy.role_of(requested, user.id)
    if role_in_workspace is None:
        # Same answer as for a workspace that does not exist: never reveal other tenants.
        raise ApiError(404, "workspace_not_found", f"workspace {requested} does not exist")
    return Principal(requested, role_in_workspace, "jwt", user.id)


def require_manager(principal: Principal = Depends(get_principal)) -> Principal:
    """Owners, admins and workspace API keys; plain members get 403."""
    if not principal.role.can_manage:
        raise ApiError(403, "forbidden", "this action needs an owner or admin")
    return principal


def get_user_identity(request: Request, dependencies: ApiDependencies = Depends(get_dependencies)):
    """The logged-in user (JWT only), for actions that are not tied to a workspace yet."""
    credential = _credential(request)
    verifier = dependencies.token_verifier
    if credential is None or verifier is None or parse_api_key_prefix(credential) is not None:
        raise ApiError(401, "unauthorized", "log in to do this")
    try:
        claims = verifier.verify(credential)
    except InvalidTokenError as error:
        raise ApiError(401, "unauthorized", "invalid or expired token") from error
    return dependencies.tenancy.get_or_create_user(claims.email, claims.subject)
