from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.auth import require_api_key
from app.api.dependencies import ApiDependencies, get_dependencies

router = APIRouter(prefix="/api/v1/audit", tags=["audit"], dependencies=[Depends(require_api_key)])


class AuditEventResponse(BaseModel):
    id: int
    created_at: datetime | None
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    request_id: str | None


class AuditListResponse(BaseModel):
    items: list[AuditEventResponse]
    limit: int
    offset: int


@router.get("", response_model=AuditListResponse)
def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    dependencies: ApiDependencies = Depends(get_dependencies),
) -> AuditListResponse:
    events = dependencies.audit_log.list(limit=limit, offset=offset)
    return AuditListResponse(
        items=[
            AuditEventResponse(
                id=e.id,
                created_at=e.created_at,
                actor=e.actor,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                details=dict(e.details),
                request_id=e.request_id,
            )
            for e in events
        ],
        limit=limit,
        offset=offset,
    )
