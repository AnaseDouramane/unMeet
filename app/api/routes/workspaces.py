from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.audit import record_audit
from app.api.auth import require_api_key
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.principal import get_principal, get_user_identity, require_manager
from app.billing.plans import PLANS, Plan, plan_for
from app.tenancy.schemas import (
    ConflictError,
    NotFoundError,
    Principal,
    Role,
    User,
    Workspace,
)

router = APIRouter(prefix="/api/v1", tags=["workspaces"])


class PlanResponse(BaseModel):
    name: str
    monthly_price_eur: int
    max_topics: int
    max_seats: int
    llm_budget_usd: float
    webhooks: bool
    daily_digest: bool


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    plan: PlanResponse
    role: str | None = None
    topics_used: int | None = None
    seats_used: int | None = None


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PlanChangeRequest(BaseModel):
    plan: str


class MemberResponse(BaseModel):
    user_id: int
    email: str
    role: str


class MemberCreateRequest(BaseModel):
    email: str = Field(max_length=320)
    role: Role = Role.MEMBER


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    prefix: str
    created_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str = Field(description="Shown once; store it now, it cannot be retrieved later")


def _plan_response(plan: Plan) -> PlanResponse:
    return PlanResponse(**vars(plan))


def _workspace_response(
    workspace: Workspace,
    role: Role | None = None,
    topics_used: int | None = None,
    seats_used: int | None = None,
) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        plan=_plan_response(plan_for(workspace.plan)),
        role=role.value if role else None,
        topics_used=topics_used,
        seats_used=seats_used,
    )


def _current(dependencies: ApiDependencies, principal: Principal) -> Workspace:
    workspace = dependencies.tenancy.get_workspace(principal.workspace_id)
    if workspace is None:
        raise ApiError(404, "workspace_not_found", "workspace does not exist")
    return workspace


@router.get("/plans", response_model=list[PlanResponse])
def list_plans() -> list[PlanResponse]:
    return [_plan_response(plan) for plan in PLANS.values()]


@router.get("/workspace", response_model=WorkspaceResponse)
def current_workspace(
    principal: Principal = Depends(get_principal),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> WorkspaceResponse:
    workspace = _current(dependencies, principal)
    return _workspace_response(
        workspace,
        principal.role,
        dependencies.topic_store.count(principal.workspace_id),
        len(dependencies.tenancy.list_members(principal.workspace_id)),
    )


@router.get("/workspaces", response_model=list[WorkspaceResponse])
def my_workspaces(
    user: User = Depends(get_user_identity),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> list[WorkspaceResponse]:
    return [
        _workspace_response(workspace, role)
        for workspace, role in dependencies.tenancy.workspaces_for_user(user.id)
    ]


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
def create_workspace(
    body: WorkspaceCreateRequest,
    http_request: Request,
    user: User = Depends(get_user_identity),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> WorkspaceResponse:
    try:
        workspace = dependencies.tenancy.create_workspace(body.name, user.email, user.external_id)
    except ValueError as error:
        raise ApiError(400, "invalid_workspace", str(error)) from error
    record_audit(
        http_request,
        dependencies,
        "workspace.create",
        "workspace",
        workspace.id,
        {"name": workspace.name},
        workspace_id=workspace.id,
    )
    return _workspace_response(workspace, Role.OWNER, 0, 1)


@router.post(
    "/workspaces/{workspace_id}/plan",
    response_model=WorkspaceResponse,
    dependencies=[Depends(require_api_key)],
)
def change_plan(
    workspace_id: int,
    body: PlanChangeRequest,
    http_request: Request,
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> WorkspaceResponse:
    """Operator-only until billing is connected: the payment provider's webhook calls this."""
    try:
        workspace = dependencies.tenancy.set_plan(workspace_id, body.plan)
    except NotFoundError as error:
        raise ApiError(404, "workspace_not_found", str(error)) from error
    except ValueError as error:
        raise ApiError(400, "invalid_plan", str(error)) from error
    record_audit(
        http_request,
        dependencies,
        "workspace.plan_change",
        "workspace",
        workspace_id,
        {"plan": body.plan},
        workspace_id=workspace_id,
    )
    return _workspace_response(workspace)


# -- members ---------------------------------------------------------------------------------


@router.get("/workspace/members", response_model=list[MemberResponse])
def list_members(
    principal: Principal = Depends(get_principal),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> list[MemberResponse]:
    return [
        MemberResponse(user_id=m.user_id, email=m.email, role=m.role.value)
        for m in dependencies.tenancy.list_members(principal.workspace_id)
    ]


@router.post("/workspace/members", response_model=MemberResponse, status_code=201)
def add_member(
    body: MemberCreateRequest,
    http_request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> MemberResponse:
    workspace = _current(dependencies, principal)
    plan = plan_for(workspace.plan)
    if len(dependencies.tenancy.list_members(workspace.id)) >= plan.max_seats:
        raise ApiError(
            402,
            "plan_limit_reached",
            f"the {plan.name} plan allows {plan.max_seats} seat(s); upgrade to add more",
            {"limit": "seats", "plan": plan.name, "max": plan.max_seats},
        )
    if body.role is Role.OWNER and principal.role is not Role.OWNER:
        raise ApiError(403, "forbidden", "only an owner can add another owner")
    try:
        member = dependencies.tenancy.add_member(workspace.id, body.email, body.role)
    except ValueError as error:
        raise ApiError(400, "invalid_member", str(error)) from error
    except ConflictError as error:
        raise ApiError(409, "member_exists", str(error)) from error
    record_audit(
        http_request,
        dependencies,
        "member.add",
        "user",
        member.user_id,
        {"role": member.role.value},
        workspace_id=workspace.id,
    )
    return MemberResponse(user_id=member.user_id, email=member.email, role=member.role.value)


@router.delete("/workspace/members/{user_id}", status_code=204)
def remove_member(
    user_id: int,
    http_request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> Response:
    try:
        dependencies.tenancy.remove_member(principal.workspace_id, user_id)
    except NotFoundError as error:
        raise ApiError(404, "member_not_found", str(error)) from error
    except ConflictError as error:
        raise ApiError(409, "last_owner", str(error)) from error
    record_audit(
        http_request,
        dependencies,
        "member.remove",
        "user",
        user_id,
        workspace_id=principal.workspace_id,
    )
    return Response(status_code=204)


# -- API keys --------------------------------------------------------------------------------


@router.get("/workspace/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> list[ApiKeyResponse]:
    return [
        ApiKeyResponse(**{k: getattr(key, k) for k in ApiKeyResponse.model_fields})
        for key in dependencies.tenancy.list_api_keys(principal.workspace_id)
    ]


@router.post("/workspace/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
def create_api_key(
    body: ApiKeyCreateRequest,
    http_request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ApiKeyCreatedResponse:
    info, plaintext = dependencies.tenancy.create_api_key(principal.workspace_id, body.name)
    record_audit(
        http_request,
        dependencies,
        "api_key.create",
        "api_key",
        info.id,
        {"name": info.name, "prefix": info.prefix},
        workspace_id=principal.workspace_id,
    )
    return ApiKeyCreatedResponse(
        **{k: getattr(info, k) for k in ApiKeyResponse.model_fields}, key=plaintext
    )


@router.delete("/workspace/api-keys/{key_id}", status_code=204)
def revoke_api_key(
    key_id: int,
    http_request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> Response:
    try:
        dependencies.tenancy.revoke_api_key(principal.workspace_id, key_id)
    except NotFoundError as error:
        raise ApiError(404, "api_key_not_found", str(error)) from error
    record_audit(
        http_request,
        dependencies,
        "api_key.revoke",
        "api_key",
        key_id,
        workspace_id=principal.workspace_id,
    )
    return Response(status_code=204)
