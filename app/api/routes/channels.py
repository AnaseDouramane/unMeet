from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.audit import record_audit
from app.api.dependencies import ApiDependencies, get_dependencies
from app.api.errors import ApiError
from app.api.principal import require_manager
from app.billing.plans import plan_for
from app.delivery.schemas import validate_target
from app.tenancy.schemas import ConflictError, NotFoundError, Principal

router = APIRouter(prefix="/api/v1/workspace/channels", tags=["deliveries"])


class ChannelResponse(BaseModel):
    id: int
    kind: str
    target: str = Field(description="Email address, or the Slack webhook with its secret masked")
    frequency: str
    enabled: bool
    last_sent_at: datetime | None
    last_error: str | None


class ChannelCreateRequest(BaseModel):
    kind: Literal["email", "slack"]
    target: str = Field(min_length=3, max_length=2000)
    frequency: Literal["daily", "weekly"] = "daily"


def mask(kind: str, target: str) -> str:
    """Slack webhook URLs are secrets: show only where they point."""
    if kind == "slack":
        return target[:32] + "…" if len(target) > 32 else target
    return target


def _response(channel) -> ChannelResponse:
    return ChannelResponse(
        id=channel.id,
        kind=channel.kind,
        target=mask(channel.kind, channel.target),
        frequency=channel.frequency,
        enabled=channel.enabled,
        last_sent_at=channel.last_sent_at,
        last_error=channel.last_error,
    )


@router.get("", response_model=list[ChannelResponse])
def list_channels(
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> list[ChannelResponse]:
    return [_response(c) for c in dependencies.channels.list(principal.workspace_id)]


@router.post("", response_model=ChannelResponse, status_code=201)
def add_channel(
    body: ChannelCreateRequest,
    request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> ChannelResponse:
    workspace = dependencies.tenancy.get_workspace(principal.workspace_id)
    plan = plan_for(workspace.plan if workspace else "free")
    if body.kind == "slack" and not plan.webhooks:
        raise ApiError(
            402,
            "plan_limit_reached",
            f"Slack delivery is not included in the {plan.name} plan",
            {"limit": "webhooks", "plan": plan.name},
        )
    if body.frequency == "daily" and not plan.daily_digest:
        raise ApiError(
            402,
            "plan_limit_reached",
            f"daily digests are not included in the {plan.name} plan",
            {"limit": "daily_digest", "plan": plan.name},
        )
    try:
        target = validate_target(body.kind, body.target)
    except ValueError as error:
        raise ApiError(400, "invalid_channel", str(error)) from error
    try:
        channel = dependencies.channels.add(
            principal.workspace_id, body.kind, target, body.frequency
        )
    except ConflictError as error:
        raise ApiError(409, "channel_exists", str(error)) from error
    record_audit(
        request,
        dependencies,
        "channel.add",
        "channel",
        channel.id,
        {"kind": channel.kind, "frequency": channel.frequency},  # never the target (a secret)
        workspace_id=principal.workspace_id,
    )
    return _response(channel)


@router.delete("/{channel_id}", status_code=204)
def remove_channel(
    channel_id: int,
    request: Request,
    principal: Principal = Depends(require_manager),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> Response:
    try:
        dependencies.channels.remove(principal.workspace_id, channel_id)
    except NotFoundError as error:
        raise ApiError(404, "channel_not_found", str(error)) from error
    record_audit(
        request,
        dependencies,
        "channel.remove",
        "channel",
        channel_id,
        workspace_id=principal.workspace_id,
    )
    return Response(status_code=204)
